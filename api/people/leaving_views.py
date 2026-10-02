"""Leaving (items 1.12 to 1.14): recorded by HR; read by HR, the Principal and the auditor.

The reason someone leaves can be sensitive (a dismissal, a death), so leaving is held to the readers of
confidential documents, on their campuses.
"""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.serializers import ErrorSerializer, InScope
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from people import leaving
from people.models import Employee, Separation
from people.views import CONFIDENTIAL_READ, HR_WRITE


class LeavingNoticeSerializer(serializers.Serializer):
    needed = serializers.BooleanField()
    why = serializers.CharField(required=False, help_text="Why no notice is needed")
    given_by = serializers.ChoiceField(choices=["employee", "school"], required=False)
    given_on = serializers.DateField(required=False)
    rule = serializers.CharField(required=False)
    full_notice_ends = serializers.DateField(
        required=False, help_text="The earliest last day with full notice"
    )
    short_by_days = serializers.IntegerField(required=False)


class SettlementLineSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=["leave", "notice", "severance"])
    label = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class SettlementSerializer(serializers.Serializer):
    last_day = serializers.DateField(required=False)
    grade = serializers.CharField(required=False)
    monthly = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    weekly = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    daily = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    service_from = serializers.DateField(required=False)
    completed_years = serializers.IntegerField(required=False)
    lines = SettlementLineSerializer(many=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.ListField(child=serializers.CharField())


def _may(serializer, *roles) -> bool:
    request = serializer.context.get("request")
    return request is not None and has_role(request.user, *roles)


class SeparationSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    reason_name = serializers.CharField(source="get_reason_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    notice = serializers.SerializerMethodField()
    settlement = serializers.SerializerMethodField(help_text="For the roles that see pay; otherwise null")
    recorded_by = serializers.SerializerMethodField()
    letter_template = serializers.SerializerMethodField(
        help_text="The template of the certificate of service"
    )
    letter_answers = serializers.SerializerMethodField(help_text="For HR, who write the letters")

    class Meta:
        model = Separation
        fields = (
            "id",
            "employee",
            "employee_name",
            "reason",
            "reason_name",
            "state",
            "state_name",
            "notice_given_on",
            "last_day",
            "note",
            "completed_at",
            "withdrawn_reason",
            "notice",
            "settlement",
            "recorded_by",
            "created_at",
            "letter_template",
            "letter_answers",
        )
        read_only_fields = fields

    @extend_schema_field(LeavingNoticeSerializer)
    def get_notice(self, separation) -> dict:
        return leaving.notice(
            separation.employee, separation.reason, separation.notice_given_on, separation.last_day
        )

    @extend_schema_field(SettlementSerializer(allow_null=True))
    def get_settlement(self, separation) -> dict | None:
        if not _may(self, *Role.SEES_PAY) or separation.state == Separation.State.WITHDRAWN:
            return None
        return separation.settlement or leaving.settlement(separation)

    def get_recorded_by(self, separation) -> str | None:
        user = separation.created_by
        return (user.get_full_name() or user.get_username()) if user else None

    def get_letter_template(self, separation) -> str:
        return "certificate_of_service"

    def get_letter_answers(self, separation) -> dict[str, str] | None:
        return leaving.letter_answers(separation) if _may(self, *HR_WRITE) else None


class RecordLeavingSerializer(serializers.Serializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    reason = serializers.ChoiceField(choices=Separation.Reason.choices)
    notice_given_on = serializers.DateField(required=False, allow_null=True)
    last_day = serializers.DateField()
    note = serializers.CharField(
        max_length=300,
        error_messages={"required": "Say why.", "blank": "Say why."},
        help_text="Kept on record",
    )


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=300, error_messages={"required": "Say why.", "blank": "Say why."}
    )


class LeavingPreviewSerializer(serializers.Serializer):
    notice = LeavingNoticeSerializer()
    settlement = SettlementSerializer(allow_null=True)


def _refused(exc: leaving.Refused) -> Response:
    code = status.HTTP_409_CONFLICT if exc.code in leaving.CONFLICTS else status.HTTP_400_BAD_REQUEST
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


@extend_schema(
    parameters=[
        OpenApiParameter("employee", int, description="One member of staff"),
        OpenApiParameter("state", str, enum=["leaving", "left", "withdrawn"]),
    ]
)
class SeparationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Separation.objects.none()
    serializer_class = SeparationSerializer
    permission_classes = [RolePermission]
    read_roles = CONFIDENTIAL_READ
    write_roles = HR_WRITE

    def get_queryset(self):
        qs = Separation.objects.select_related("employee", "employee__campus", "created_by")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        params = self.request.query_params
        if params.get("employee"):
            qs = qs.filter(employee_id=params["employee"])
        if params.get("state"):
            qs = qs.filter(state=params["state"])
        return qs

    def _written(self, request):
        data = RecordLeavingSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        if not campus_in_scope(request.user, data.validated_data["employee"].campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        return data.validated_data

    @extend_schema(
        request=RecordLeavingSerializer,
        responses={201: SeparationSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Record that someone is leaving; on the night after the last day they have left",
    )
    def create(self, request):
        try:
            separation = leaving.record_leaving(request, **self._written(request))
        except leaving.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(separation).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=RecordLeavingSerializer,
        responses={200: LeavingPreviewSerializer},
        summary="The notice the law asks for, and the figures owed, before leaving is recorded",
    )
    @action(detail=False, methods=["post"])
    def preview(self, request):
        data = self._written(request)
        draft = Separation(
            employee=data["employee"],
            reason=data["reason"],
            notice_given_on=data.get("notice_given_on"),
            last_day=data["last_day"],
            created_at=timezone.now(),
        )
        sees_pay = has_role(request.user, *Role.SEES_PAY)
        return Response(
            {
                "notice": leaving.notice(draft.employee, draft.reason, draft.notice_given_on, draft.last_day),
                "settlement": leaving.settlement(draft) if sees_pay else None,
            }
        )

    @extend_schema(
        request=WithdrawSerializer,
        responses={200: SeparationSerializer, 400: ErrorSerializer},
        summary="Withdraw a leaving that has not happened, such as a resignation taken back",
    )
    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        separation = self.get_object()
        if not campus_in_scope(request.user, separation.employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        data = WithdrawSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            leaving.withdraw(request, separation, data.validated_data["reason"])
        except leaving.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(separation).data)
