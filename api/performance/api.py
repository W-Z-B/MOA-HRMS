"""H-M03 endpoints: review cycles, goals, and appraisals (self-assessment, manager assessment, sign-off).

Visibility follows the same reasoning as a confidential document (people.views.CONFIDENTIAL_READ): HR,
the Principal and the auditor; an appraisal and its goals are also open to the employee it is about and to
whoever rates it (their manager when it was opened) - not a new role, the owner/manager split every other
module already uses.
"""

from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core.serializers import ErrorSerializer, InScope, TimeStampedSerializer
from core.views import AuditedModelViewSet
from iam.permissions import RolePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from people.models import Employee
from people.services import manager_of
from people.views import CONFIDENTIAL_READ, HR_WRITE
from performance.models import Appraisal, AppraisalCycle, Goal
from performance.workflow import APPRAISAL, HR_SIGN, WorkflowError

CYCLE_READ = CONFIDENTIAL_READ
CYCLE_WRITE = HR_SIGN  # the HR Manager and administrators open and close cycles


def _refuse(code: str, detail: str, http_status: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"code": code, "detail": detail}, status=http_status)


class AppraisalCycleSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = AppraisalCycle
        fields = ("id", "name", "year", "starts", "ends", "is_open")


class AppraisalCycleViewSet(AuditedModelViewSet):
    queryset = AppraisalCycle.objects.all()
    serializer_class = AppraisalCycleSerializer
    read_roles = CYCLE_READ
    write_roles = CYCLE_WRITE


class GoalSerializer(TimeStampedSerializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    status_name = serializers.CharField(source="get_status_display", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Goal
        fields = (
            "id",
            "employee",
            "cycle",
            "title",
            "description",
            "weight",
            "status",
            "status_name",
            "position",
        )


def _may_see(user, employee_id: int, manager_id: int | None) -> bool:
    if has_role(user, *CONFIDENTIAL_READ):
        return True
    own = getattr(user, "employee", None)
    if own is None:
        return False
    return own.pk == employee_id or (manager_id is not None and own.pk == manager_id)


class GoalViewSet(AuditedModelViewSet):
    """HR or the employee's manager set the goals; the employee, their manager and HR read them."""

    queryset = Goal.objects.none()
    serializer_class = GoalSerializer
    permission_classes = [RolePermission]

    def get_queryset(self):

        qs = Goal.objects.select_related("employee", "employee__campus", "cycle")
        user = self.request.user
        if has_role(user, *CONFIDENTIAL_READ):
            qs = scope_queryset(user, qs, campus_field="employee__campus")
        else:
            own = getattr(user, "employee", None)
            if own is None:
                return qs.none()
            # Goals carry no manager of their own; anyone ever recorded as this employee's manager on an
            # appraisal (performance.Appraisal.manager, fixed when each was opened) may also see them.
            managed = Appraisal.objects.filter(manager=own).values_list("employee_id", flat=True)
            qs = qs.filter(Q(employee=own) | Q(employee_id__in=managed))
        params = self.request.query_params
        if params.get("employee"):
            qs = qs.filter(employee_id=params["employee"])
        if params.get("cycle"):
            qs = qs.filter(cycle_id=params["cycle"])
        return qs

    def _check_write(self, employee):
        user = self.request.user
        if has_role(user, *HR_WRITE):
            if not campus_in_scope(user, employee.campus_id):
                self.permission_denied(
                    self.request, message="That employee is not on a campus you work with."
                )
            return
        own = getattr(user, "employee", None)
        current_manager = manager_of(employee)
        if own is None or current_manager is None or current_manager.pk != own.pk:
            self.permission_denied(
                self.request, message="Only Human Resources or this employee's manager sets goals."
            )

    def perform_create(self, serializer):
        self._check_write(serializer.validated_data["employee"])
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._check_write(serializer.instance.employee)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._check_write(instance.employee)
        super().perform_destroy(instance)


class StartAppraisalSerializer(serializers.Serializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    cycle = serializers.PrimaryKeyRelatedField(queryset=AppraisalCycle.objects.all())
    kind = serializers.ChoiceField(choices=Appraisal.Kind.choices, default=Appraisal.Kind.ANNUAL)


class SelfAssessmentSerializer(serializers.Serializer):
    self_assessment = serializers.CharField()


class ManagerAssessmentSerializer(serializers.Serializer):
    manager_assessment = serializers.CharField()
    overall_rating = serializers.IntegerField(min_value=1, max_value=5)
    outcome = serializers.CharField(max_length=60, required=False, allow_blank=True)


class AppraisalTransitionSerializer(serializers.Serializer):
    action = serializers.CharField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class AppraisalSerializer(TimeStampedSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    manager_name = serializers.CharField(source="manager.full_name", read_only=True, default=None)
    cycle_name = serializers.SerializerMethodField()
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    is_mine = serializers.SerializerMethodField()
    is_rated_by_me = serializers.SerializerMethodField()
    goals = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Appraisal
        fields = (
            "id",
            "employee",
            "employee_name",
            "manager",
            "manager_name",
            "cycle",
            "cycle_name",
            "kind",
            "kind_name",
            "state",
            "state_name",
            "decision_comment",
            "self_assessment",
            "self_assessed_at",
            "manager_assessment",
            "overall_rating",
            "rated_at",
            "signed_at",
            "outcome",
            "is_mine",
            "is_rated_by_me",
            "goals",
            "allowed_actions",
            "created_at",
        )
        read_only_fields = tuple(f for f in fields if f not in ("employee", "cycle", "kind"))

    def get_cycle_name(self, instance) -> str:
        return f"{instance.cycle.name} {instance.cycle.year}"

    def get_is_mine(self, instance) -> bool:
        request = self.context.get("request")
        employee = getattr(request.user, "employee", None) if request else None
        return employee is not None and employee.pk == instance.employee_id

    def get_is_rated_by_me(self, instance) -> bool:
        request = self.context.get("request")
        employee = getattr(request.user, "employee", None) if request else None
        return employee is not None and instance.manager_id == employee.pk

    def get_goals(self, instance) -> list[dict]:
        goals = Goal.objects.filter(employee_id=instance.employee_id, cycle_id=instance.cycle_id)
        return GoalSerializer(goals, many=True, context=self.context).data

    def get_allowed_actions(self, instance) -> list[str]:
        request = self.context.get("request")
        if request is None:
            return []
        return APPRAISAL.allowed_actions(instance, request.user)


@extend_schema(parameters=[OpenApiParameter("employee", int, description="One member of staff")])
class AppraisalViewSet(viewsets.ReadOnlyModelViewSet):
    """Opened by HR from a cycle; moved on by the employee, their manager and HR through dedicated
    actions, never by a plain PATCH, so the content and the state can never go out of step."""

    queryset = Appraisal.objects.none()
    serializer_class = AppraisalSerializer
    permission_classes = [RolePermission]

    def get_queryset(self):
        qs = Appraisal.objects.select_related("employee", "employee__campus", "manager", "cycle")
        user = self.request.user
        if has_role(user, *CONFIDENTIAL_READ):
            qs = scope_queryset(user, qs, campus_field="employee__campus")
            employee = self.request.query_params.get("employee")
            return qs.filter(employee_id=employee) if employee else qs
        own = getattr(user, "employee", None)
        if own is None:
            return qs.none()

        return qs.filter(Q(employee=own) | Q(manager=own))

    @extend_schema(
        request=StartAppraisalSerializer,
        responses={201: AppraisalSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Open an appraisal for an employee within a cycle: the manager is fixed now",
    )
    @action(detail=False, methods=["post"])
    def start(self, request):
        if not has_role(request.user, *HR_WRITE):
            self.permission_denied(request, message="Only Human Resources opens an appraisal.")
        data = StartAppraisalSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        employee = data.validated_data["employee"]
        if not campus_in_scope(request.user, employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        if Appraisal.objects.filter(
            employee=employee, cycle=data.validated_data["cycle"], kind=data.validated_data["kind"]
        ).exists():
            return _refuse("already_open", "An appraisal of that kind is already open for this cycle.")
        with transaction.atomic():
            instance = Appraisal.objects.create(
                employee=employee,
                manager=manager_of(employee),
                cycle=data.validated_data["cycle"],
                kind=data.validated_data["kind"],
                created_by=request.user,
                updated_by=request.user,
            )
            record(request, "create", instance, after=snapshot(instance))
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def _own(self, instance) -> bool:
        employee = getattr(self.request.user, "employee", None)
        return employee is not None and employee.pk == instance.employee_id

    def _rates(self, instance) -> bool:
        employee = getattr(self.request.user, "employee", None)
        return (employee is not None and instance.manager_id == employee.pk) or has_role(
            self.request.user, *HR_SIGN
        )

    @extend_schema(
        request=SelfAssessmentSerializer,
        responses={
            200: AppraisalSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Write or change the self-assessment, while it is still a draft",
    )
    @action(detail=True, methods=["patch"], url_path="self-assessment")
    def self_assessment(self, request, pk=None):
        instance = self.get_object()
        if not self._own(instance):
            return _refuse(
                "forbidden", "Only the employee writes their own self-assessment.", status.HTTP_403_FORBIDDEN
            )
        if instance.state != Appraisal.State.DRAFT:
            return _refuse("not_draft", "The self-assessment is submitted; it can no longer be changed here.")
        data = SelfAssessmentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        before = snapshot(instance)
        instance.self_assessment = data.validated_data["self_assessment"]
        instance.updated_by = request.user
        instance.save(update_fields=["self_assessment", "updated_by", "updated_at"])
        record(request, "update", instance, before=before, after=snapshot(instance))
        return Response(self.get_serializer(instance).data)

    @extend_schema(
        request=ManagerAssessmentSerializer,
        responses={
            200: AppraisalSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Write or change the manager's assessment and rating, before it is rated",
    )
    @action(detail=True, methods=["patch"], url_path="manager-assessment")
    def manager_assessment(self, request, pk=None):
        instance = self.get_object()
        if not self._rates(instance):
            return _refuse(
                "forbidden",
                "Only this employee's manager, or Human Resources, rates it.",
                status.HTTP_403_FORBIDDEN,
            )
        if instance.state != Appraisal.State.SELF_ASSESSED:
            return _refuse("not_self_assessed", "The self-assessment is not yet in.")
        data = ManagerAssessmentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        before = snapshot(instance)
        instance.manager_assessment = data.validated_data["manager_assessment"]
        instance.overall_rating = data.validated_data["overall_rating"]
        instance.outcome = data.validated_data.get("outcome", instance.outcome)
        instance.updated_by = request.user
        instance.save(
            update_fields=["manager_assessment", "overall_rating", "outcome", "updated_by", "updated_at"]
        )
        record(request, "update", instance, before=before, after=snapshot(instance))
        return Response(self.get_serializer(instance).data)

    @extend_schema(
        request=AppraisalTransitionSerializer,
        responses={
            200: AppraisalSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Move the appraisal on: submit_self_assessment, rate, sign_off or reopen",
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        instance = self.get_object()
        body = AppraisalTransitionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            APPRAISAL.apply(
                instance,
                body.validated_data["action"],
                request=request,
                comment=body.validated_data["comment"],
            )
        except WorkflowError as exc:
            code = status.HTTP_403_FORBIDDEN if exc.code == "forbidden_actor" else status.HTTP_409_CONFLICT
            return Response({"code": exc.code, "detail": str(exc)}, status=code)
        return Response(self.get_serializer(instance).data)


router = DefaultRouter()
router.register("cycles", AppraisalCycleViewSet)
router.register("goals", GoalViewSet)
router.register("appraisals", AppraisalViewSet)
urlpatterns = router.urls

__all__ = ["urlpatterns"]
