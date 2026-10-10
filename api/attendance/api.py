"""H-M02 endpoints: shift patterns, the daily record, self-service check-in/out, and HR's correction."""

from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from attendance import services
from attendance.models import AttendanceRecord, EmployeeShift, ShiftPattern
from attendance.serializers import (
    AttendanceRecordSerializer,
    CorrectionSerializer,
    EmployeeShiftSerializer,
    ShiftPatternSerializer,
)
from audit.services import record, snapshot
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.services import campus_in_scope, has_role, scope_queryset

HR = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)
HR_AND_SUPERVISOR = HR + (Role.SUPERVISOR,)
BROAD_READ = HR_AND_SUPERVISOR + (Role.PRINCIPAL, Role.FINANCE, Role.AUDITOR)


def _refuse(code: str, detail: str, http_status: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"code": code, "detail": detail}, status=http_status)


class ShiftPatternViewSet(AuditedModelViewSet):
    queryset = ShiftPattern.objects.all()
    serializer_class = ShiftPatternSerializer
    write_roles = HR


class EmployeeShiftViewSet(AuditedModelViewSet):
    queryset = EmployeeShift.objects.none()  # scoped per request in get_queryset; fails closed
    serializer_class = EmployeeShiftSerializer
    read_roles = BROAD_READ
    write_roles = HR

    def get_queryset(self):
        qs = EmployeeShift.objects.select_related("employee", "shift")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        employee = self.request.query_params.get("employee")
        return qs.filter(employee_id=employee) if employee else qs


class AttendanceRecordViewSet(AuditedModelViewSet):
    """Employees see their own days; HR, supervisors and other broad roles see their campuses' days."""

    queryset = AttendanceRecord.objects.none()  # scoped per request in get_queryset; fails closed
    serializer_class = AttendanceRecordSerializer

    def get_queryset(self):
        user = self.request.user
        qs = AttendanceRecord.objects.select_related("employee", "employee__campus", "leave_request")
        own = Q(employee__user=user)
        if has_role(user, *BROAD_READ):
            scoped = scope_queryset(user, AttendanceRecord.objects.all(), campus_field="employee__campus")
            qs = qs.filter(Q(pk__in=scoped.values("pk")) | own)
        else:
            qs = qs.filter(own)
        params = self.request.query_params
        if params.get("employee"):
            qs = qs.filter(employee_id=params["employee"])
        if params.get("date_from"):
            qs = qs.filter(date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(date__lte=params["date_to"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("exceptions") == "1":
            qs = qs.filter(status__in=AttendanceRecord.OPEN_STATUSES)
        return qs.distinct()

    # Records are only ever made or changed through check_in, check_out and correct, so the business rules
    # in attendance.services (and the audit entries each one writes) can never be bypassed by the generic
    # create/update/destroy actions a ModelViewSet otherwise offers.
    def create(self, request, *args, **kwargs):
        return _refuse("not_allowed", "Use check-in or check-out.", status.HTTP_405_METHOD_NOT_ALLOWED)

    def update(self, request, *args, **kwargs):
        detail = "Use the correct action to change a day."
        return _refuse("not_allowed", detail, status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        detail = "Attendance records are not deleted."
        return _refuse("not_allowed", detail, status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """Today's record for the caller, so the check-in screen knows what it may offer next."""
        employee = getattr(request.user, "employee", None)
        if employee is None:
            return _refuse("not_found", "Your account is not linked to an employee record.", 404)
        today = timezone.localdate()
        instance = AttendanceRecord.objects.filter(employee=employee, date=today).first()
        if instance is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(self.get_serializer(instance).data)

    @action(detail=False, methods=["post"])
    def check_in(self, request):
        employee = getattr(request.user, "employee", None)
        if employee is None:
            return _refuse("not_found", "Your account is not linked to an employee record.", 404)
        try:
            instance = services.check_in(employee)
        except services.AttendanceError as exc:
            return _refuse(exc.code, str(exc))
        record(request, "check_in", instance, after=snapshot(instance))
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def check_out(self, request):
        employee = getattr(request.user, "employee", None)
        if employee is None:
            return _refuse("not_found", "Your account is not linked to an employee record.", 404)
        try:
            instance = services.check_out(employee)
        except services.AttendanceError as exc:
            return _refuse(exc.code, str(exc))
        record(request, "check_out", instance, after=snapshot(instance))
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"], url_path="correct")
    def correct_(self, request, pk=None):
        """HR's correction or override for a missed or wrong day (item H-M02, the D3 fallback)."""
        if not has_role(request.user, *HR_AND_SUPERVISOR):
            return _refuse("forbidden", "Only Human Resources or a supervisor may correct a day.", 403)
        instance = self.get_object()
        if not campus_in_scope(request.user, instance.employee.campus_id):
            return _refuse("forbidden", "That employee is not on a campus you work with.", 403)
        data = CorrectionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        before = snapshot(instance)
        services.correct(
            instance,
            time_in=data.validated_data.get("time_in"),
            time_out=data.validated_data.get("time_out"),
            clear=data.validated_data.get("clear", False),
            note=data.validated_data["note"],
        )
        instance.updated_by = request.user
        instance.save(update_fields=["updated_by"])
        record(
            request,
            "correct",
            instance,
            before=before,
            after=snapshot(instance),
            reason=data.validated_data["note"],
        )
        return Response(self.get_serializer(instance).data)


router = DefaultRouter()
router.register("shifts", ShiftPatternViewSet)
router.register("employee-shifts", EmployeeShiftViewSet)
router.register("records", AttendanceRecordViewSet)
urlpatterns = router.urls

__all__ = ["urlpatterns", "viewsets"]
