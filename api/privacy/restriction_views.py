"""Item 1.46: restrictions and objections. A person sees their own; HR places and lifts restrictions for the
staff on their campuses; the data protection officer sees every one and decides objections."""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.serializers import ErrorSerializer
from iam.models import Role
from iam.permissions import SelfServicePermission
from iam.services import has_role, scope_queryset
from people.models import Employee
from privacy import restrictions
from privacy.models import CorrectionRequest, Objection, Restriction
from privacy.views import CORRECTION_DECIDE

OFFICER = (Role.DATA_PROTECTION_OFFICER,)
RESTRICTION_WRITE = CORRECTION_DECIDE + OFFICER
OBJECTION_READ = OFFICER + (Role.HR_MANAGER, Role.ADMINISTRATOR)


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


def _refused(exc: restrictions.Refused) -> Response:
    code = status.HTTP_403_FORBIDDEN if exc.code == "own" else status.HTTP_409_CONFLICT
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


def _staff_for(request, employee_id: int) -> Employee:
    """A member of staff the caller may act for: anyone for the officer, those on their campuses for HR.
    Anyone else reads as not existing, so a refusal never says who works where."""
    staff = Employee.objects.all()
    if not has_role(request.user, *OFFICER):
        staff = scope_queryset(request.user, staff, "campus")
    employee = staff.filter(pk=employee_id).first()
    if employee is None:
        raise serializers.ValidationError(
            {"employee": [f'Invalid pk "{employee_id}" - object does not exist.']}
        )
    return employee


class RestrictionSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True)
    part_name = serializers.CharField(source="get_part_display", read_only=True)
    ground_name = serializers.CharField(source="get_ground_display", read_only=True)
    placed_by_name = serializers.SerializerMethodField()
    lifted_by_name = serializers.SerializerMethodField()
    in_force = serializers.SerializerMethodField()

    class Meta:
        model = Restriction
        fields = (
            "id",
            "employee",
            "employee_name",
            "employee_no",
            "part",
            "part_name",
            "ground",
            "ground_name",
            "note",
            "correction",
            "objection",
            "created_at",
            "placed_by_name",
            "in_force",
            "lifted_at",
            "lifted_by_name",
            "lifted_reason",
        )
        read_only_fields = fields

    def get_placed_by_name(self, restriction) -> str | None:
        return _name(restriction.created_by)

    def get_lifted_by_name(self, restriction) -> str | None:
        return _name(restriction.lifted_by)

    def get_in_force(self, restriction) -> bool:
        return restriction.lifted_at is None


class RestrictionPlaceSerializer(serializers.Serializer):
    employee = serializers.IntegerField()
    part = serializers.ChoiceField(choices=CorrectionRequest.Subject.choices)
    ground = serializers.ChoiceField(
        choices=[(g.value, g.label) for g in Restriction.Ground if g != Restriction.Ground.OBJECTION],
        help_text="An objection restricts its part by itself",
    )
    note = serializers.CharField(
        max_length=1000, error_messages={"blank": "Say why.", "required": "Say why."}
    )


class LiftSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=1000,
        error_messages={"blank": "Say why.", "required": "Say why."},
        help_text="The person is told",
    )


@extend_schema(
    parameters=[
        OpenApiParameter("employee", int, description="Restrictions in one person's record"),
        OpenApiParameter("in_force", bool, description="Only those not yet lifted"),
    ]
)
class RestrictionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Parts of records held back from use while a person contests them, objects, or for a legal reason."""

    queryset = Restriction.objects.none()
    serializer_class = RestrictionSerializer
    permission_classes = [SelfServicePermission]
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        user = self.request.user
        qs = Restriction.objects.select_related("employee", "created_by", "lifted_by")
        own = qs.filter(employee__user=user)
        if has_role(user, *OFFICER):
            qs = qs.all()
        elif has_role(user, *CORRECTION_DECIDE):
            qs = (scope_queryset(user, qs, campus_field="employee__campus") | own).distinct()
        else:
            qs = own
        params = self.request.query_params
        if params.get("employee"):
            qs = qs.filter(employee_id=params["employee"])
        if params.get("in_force") in ("1", "true"):
            qs = qs.filter(lifted_at__isnull=True)
        return qs.order_by("-created_at", "-id")

    @extend_schema(
        request=RestrictionPlaceSerializer,
        responses={201: RestrictionSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        summary="Restrict part of a record: HR on their campuses, or the data protection officer",
    )
    def create(self, request, *args, **kwargs):
        if not has_role(request.user, *RESTRICTION_WRITE):
            self.permission_denied(
                request, message="Human Resources or the data protection officer restricts."
            )
        data = RestrictionPlaceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        employee = _staff_for(request, values.pop("employee"))
        restriction = restrictions.place(request, employee, **values)
        return Response(RestrictionSerializer(restriction).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=LiftSerializer,
        responses={200: RestrictionSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Lift a restriction, with the reason the person is told",
    )
    @action(detail=True, methods=["post"])
    def lift(self, request, pk=None):
        restriction = self.get_object()
        if not has_role(request.user, *RESTRICTION_WRITE) or restriction.employee.user_id == request.user.pk:
            self.permission_denied(
                request, message="Human Resources or the data protection officer lifts it."
            )
        data = LiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            restrictions.lift(request, restriction, data.validated_data["reason"])
        except restrictions.Refused as exc:
            return _refused(exc)
        return Response(RestrictionSerializer(restriction).data)


class ObjectionSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True)
    part_name = serializers.CharField(source="get_part_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    decided_by_name = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Objection
        fields = (
            "id",
            "employee",
            "employee_name",
            "employee_no",
            "part",
            "part_name",
            "grounds",
            "state",
            "state_name",
            "due_by",
            "overdue",
            "created_at",
            "decided_by_name",
            "decided_at",
            "reasons",
            "is_mine",
        )
        read_only_fields = fields

    def get_decided_by_name(self, objection) -> str | None:
        return _name(objection.decided_by)

    def get_overdue(self, objection) -> bool:
        return objection.state == Objection.State.OPEN and objection.due_by < timezone.localdate()

    def get_is_mine(self, objection) -> bool:
        return objection.employee.user_id == self.context["request"].user.pk


class ObjectionLodgeSerializer(serializers.Serializer):
    employee = serializers.IntegerField(required=False, help_text="Leave out to object for yourself")
    part = serializers.ChoiceField(choices=CorrectionRequest.Subject.choices)
    grounds = serializers.CharField(
        max_length=2000,
        error_messages={"blank": "Say why you object.", "required": "Say why you object."},
        help_text="Why, in your own situation",
    )


class ObjectionDecisionSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["upheld", "not_upheld"])
    reasons = serializers.CharField(
        max_length=2000,
        error_messages={"blank": "Give the reasons.", "required": "Give the reasons."},
        help_text="Not upheld only for compelling legitimate grounds, or a legal claim",
    )


@extend_schema(parameters=[OpenApiParameter("state", str, enum=[s.value for s in Objection.State])])
class ObjectionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """A person's own objections; all of them for the data protection officer, HR Manager and admins."""

    queryset = Objection.objects.none()
    serializer_class = ObjectionSerializer
    permission_classes = [SelfServicePermission]
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        user = self.request.user
        qs = Objection.objects.select_related("employee", "decided_by")
        if not has_role(user, *OBJECTION_READ):
            qs = qs.filter(employee__user=user)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        return qs.order_by("state", "due_by", "-created_at")

    @extend_schema(
        request=ObjectionLodgeSerializer,
        responses={201: ObjectionSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        summary="Object in writing to how part of a record is used; that part is restricted until decided",
    )
    def create(self, request, *args, **kwargs):
        data = ObjectionLodgeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        own = getattr(request.user, "employee", None)
        if "employee" in values:
            if not has_role(request.user, *CORRECTION_DECIDE):
                self.permission_denied(request, message="You may object only about your own record.")
            employee = _staff_for(request, values.pop("employee"))
        elif own is None:
            raise serializers.ValidationError({"employee": ["Your account is not linked to a staff record."]})
        else:
            employee = own
        objection = restrictions.lodge(request, employee, **values)
        fresh = Objection.objects.select_related("employee", "decided_by").get(pk=objection.pk)
        return Response(
            ObjectionSerializer(fresh, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=ObjectionDecisionSerializer,
        responses={200: ObjectionSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Decide an objection: upheld, or not upheld for compelling grounds or a legal claim",
    )
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        if not has_role(request.user, *OFFICER):
            self.permission_denied(request, message="The data protection officer decides objections.")
        objection = self.get_object()
        data = ObjectionDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            restrictions.decide(
                request,
                objection,
                upheld=data.validated_data["outcome"] == "upheld",
                reasons=data.validated_data["reasons"],
            )
        except restrictions.Refused as exc:
            return _refused(exc)
        return Response(ObjectionSerializer(objection, context=self.get_serializer_context()).data)
