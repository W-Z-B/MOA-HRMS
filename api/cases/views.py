"""The case register (item 1.15): opened by HR; seen and acted on by the HR Manager and named officers."""

from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cases import services
from cases.models import Case, CaseEntry, CaseOfficer
from core.serializers import ErrorSerializer, InScope
from iam.models import Role
from iam.permissions import SelfServicePermission
from iam.services import campus_in_scope, has_role
from people.models import Employee

OPENERS = (Role.HR_OFFICER, Role.HR_MANAGER)


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


class OfficerSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    named_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CaseOfficer
        fields = ("id", "user", "name", "part", "named_by_name", "named_at")
        read_only_fields = fields

    def get_name(self, officer) -> str:
        return _name(officer.user)

    def get_named_by_name(self, officer) -> str | None:
        return _name(officer.named_by)


class EntrySerializer(serializers.ModelSerializer):
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    by = serializers.SerializerMethodField()

    class Meta:
        model = CaseEntry
        fields = ("id", "kind", "kind_name", "on", "text", "by", "created_at")
        read_only_fields = fields

    def get_by(self, entry) -> str | None:
        return _name(entry.created_by)


class FairStepsSerializer(serializers.Serializer):
    allegation = serializers.BooleanField(help_text="The allegation was put in writing")
    answered = serializers.BooleanField(help_text="The employee's response, or a hearing, is recorded")


class CaseSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True)
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    outcome_name = serializers.CharField(source="get_outcome_display", read_only=True)
    appeal_outcome_name = serializers.CharField(source="get_appeal_outcome_display", read_only=True)
    decided_by_name = serializers.SerializerMethodField()
    appeal_decided_by_name = serializers.SerializerMethodField()
    officers = OfficerSerializer(many=True, read_only=True)
    entries = EntrySerializer(many=True, read_only=True)
    fair_steps = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = (
            "id",
            "reference",
            "kind",
            "kind_name",
            "employee",
            "employee_name",
            "employee_no",
            "summary",
            "opened_on",
            "state",
            "state_name",
            "outcome",
            "outcome_name",
            "outcome_reasons",
            "decided_on",
            "decided_by_name",
            "lapses_on",
            "appeal_lodged_on",
            "appeal_grounds",
            "appeal_outcome",
            "appeal_outcome_name",
            "appeal_reasons",
            "appeal_decided_on",
            "appeal_decided_by_name",
            "closed_on",
            "officers",
            "entries",
            "fair_steps",
        )
        read_only_fields = fields

    def get_decided_by_name(self, case) -> str | None:
        return _name(case.decided_by)

    def get_appeal_decided_by_name(self, case) -> str | None:
        return _name(case.appeal_decided_by)

    @extend_schema_field(FairStepsSerializer)
    def get_fair_steps(self, case) -> dict:
        return services.fair_steps(case)


class CaseOpenSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Case.Kind.choices)
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    summary = serializers.CharField(help_text="The allegation, or the grievance")
    opened_on = serializers.DateField()


class CaseOfficerInputSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.filter(is_active=True))
    part = serializers.CharField(max_length=80)


class CaseEntryInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=CaseEntry.Kind.choices)
    on = serializers.DateField()
    text = serializers.CharField()


class CaseDecisionSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=Case.Outcome.choices)
    reasons = serializers.CharField(
        error_messages={"required": "Give the reasons.", "blank": "Give the reasons."}
    )
    decided_on = serializers.DateField()


class CaseAppealSerializer(serializers.Serializer):
    lodged_on = serializers.DateField()
    grounds = serializers.CharField(
        error_messages={"required": "Give the grounds.", "blank": "Give the grounds."}
    )


class CaseAppealDecisionSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=Case.AppealOutcome.choices)
    reasons = serializers.CharField(
        error_messages={"required": "Give the reasons.", "blank": "Give the reasons."}
    )
    decided_on = serializers.DateField()


def _refused(exc: services.Refused) -> Response:
    code = status.HTTP_409_CONFLICT if exc.code in services.CONFLICTS else status.HTTP_400_BAD_REQUEST
    if exc.code in ("not_named", "own"):
        code = status.HTTP_403_FORBIDDEN
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


@extend_schema(
    parameters=[
        OpenApiParameter("state", str, enum=[s.value for s in Case.State]),
        OpenApiParameter("kind", str, enum=[k.value for k in Case.Kind]),
    ]
)
class CaseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Every case for the HR Manager; for anyone else, those they are named on. Never a case about oneself."""

    queryset = Case.objects.none()
    serializer_class = CaseSerializer
    permission_classes = [SelfServicePermission]

    def get_queryset(self):
        qs = services.visible(self.request.user).prefetch_related(
            "officers__user", "officers__named_by", "entries__created_by"
        )
        params = self.request.query_params
        if params.get("state"):
            qs = qs.filter(state=params["state"])
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        return qs

    def _answer(self, case, code=status.HTTP_200_OK) -> Response:
        return Response(self.get_serializer(self.get_queryset().get(pk=case.pk)).data, status=code)

    def _acting(self, request):
        case = self.get_object()
        if not services.may_act(request.user, case):
            self.permission_denied(
                request, message="Only the HR Manager, or someone named on the case, acts on it."
            )
        return case

    def _run(self, call, *args, code=status.HTTP_200_OK, **kwargs) -> Response:
        try:
            case = call(*args, **kwargs)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(case, code)

    @extend_schema(
        request=CaseOpenSerializer,
        responses={201: CaseSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        summary="Open a case; whoever opens it is named on it",
    )
    def create(self, request):
        if not has_role(request.user, *OPENERS):
            self.permission_denied(request, message="Human Resources opens cases.")
        data = CaseOpenSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        if not campus_in_scope(request.user, data.validated_data["employee"].campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        return self._run(services.open_case, request, code=status.HTTP_201_CREATED, **data.validated_data)

    @extend_schema(
        request=CaseOfficerInputSerializer,
        responses={200: CaseSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
    )
    @action(detail=True, methods=["post"])
    def officers(self, request, pk=None):
        case = self._acting(request)
        data = CaseOfficerInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.name_officer(request, case, data.validated_data["user"], data.validated_data["part"])
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(case)

    @extend_schema(request=CaseEntryInputSerializer, responses={200: CaseSerializer, 400: ErrorSerializer})
    @action(detail=True, methods=["post"])
    def entries(self, request, pk=None):
        case = self._acting(request)
        data = CaseEntryInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.add_entry(request, case, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(case)

    @extend_schema(request=CaseDecisionSerializer, responses={200: CaseSerializer, 400: ErrorSerializer})
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        case = self._acting(request)
        data = CaseDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self._run(services.decide, request, case, **data.validated_data)

    @extend_schema(request=CaseAppealSerializer, responses={200: CaseSerializer, 400: ErrorSerializer})
    @action(detail=True, methods=["post"])
    def appeal(self, request, pk=None):
        case = self._acting(request)
        data = CaseAppealSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self._run(services.lodge_appeal, request, case, **data.validated_data)

    @extend_schema(
        request=CaseAppealDecisionSerializer, responses={200: CaseSerializer, 400: ErrorSerializer}
    )
    @action(detail=True, methods=["post"], url_path="appeal-decision")
    def appeal_decision(self, request, pk=None):
        case = self._acting(request)
        data = CaseAppealDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self._run(services.decide_appeal, request, case, **data.validated_data)

    @extend_schema(request=None, responses={200: CaseSerializer, 409: ErrorSerializer})
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        case = self._acting(request)
        return self._run(services.close, request, case)
