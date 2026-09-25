"""F06 endpoints: leave types, requests with workflow transitions, ledger and balances."""

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import has_role, scope_queryset
from leave import serializers
from leave.models import LeaveLedger, LeaveRequest, LeaveType
from leave.services import balances_for
from leave.workflow import LEAVE_REQUEST, WorkflowError
from people.models import Employee

HR = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)


class LeaveTypeViewSet(AuditedModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = serializers.LeaveTypeSerializer
    write_roles = (Role.HR_MANAGER, Role.ADMINISTRATOR)


class LeaveRequestViewSet(AuditedModelViewSet):
    """Employees see and create their own requests; supervisors and HR see their scope."""

    serializer_class = serializers.LeaveRequestSerializer

    def get_queryset(self):
        user = self.request.user
        qs = LeaveRequest.objects.select_related("employee", "leave_type")
        if has_role(user, *HR, Role.PRINCIPAL, Role.AUDITOR):
            qs = scope_queryset(user, qs, campus_field="employee__campus")
        elif has_role(user, Role.SUPERVISOR):
            own = Q(employee__user=user)
            team = Q(employee__campus__in=scope_queryset(user, Employee.objects.all()).values("campus"))
            qs = qs.filter(own | team)
        else:
            qs = qs.filter(employee__user=user)
        employee = self.request.query_params.get("employee")
        state = self.request.query_params.get("state")
        if employee:
            qs = qs.filter(employee_id=employee)
        if state:
            qs = qs.filter(state=state)
        return qs.distinct()

    def perform_create(self, serializer):
        user = self.request.user
        employee = serializer.validated_data.get("employee")
        own = getattr(user, "employee", None)
        if not has_role(user, *HR) and (own is None or employee != own):
            self.permission_denied(self.request, message="You may only create leave requests for yourself.")
        super().perform_create(serializer)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        data = serializers.TransitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        instance = self.get_object()
        try:
            LEAVE_REQUEST.apply(
                instance,
                data.validated_data["action"],
                request=request,
                comment=data.validated_data.get("comment", ""),
            )
        except WorkflowError as exc:
            code = status.HTTP_403_FORBIDDEN if exc.code == "forbidden_actor" else status.HTTP_409_CONFLICT
            return Response({"code": exc.code, "detail": str(exc)}, status=code)
        return Response(self.get_serializer(instance).data)


class LeaveLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = serializers.LeaveLedgerSerializer
    permission_classes = [RolePermission]

    def get_queryset(self):
        user = self.request.user
        qs = LeaveLedger.objects.select_related("employee", "leave_type")
        if has_role(user, *HR, Role.PRINCIPAL, Role.FINANCE, Role.AUDITOR):
            qs = scope_queryset(user, qs, campus_field="employee__campus")
        else:
            qs = qs.filter(employee__user=user)
        employee = self.request.query_params.get("employee")
        return qs.filter(employee_id=employee) if employee else qs

    @action(detail=False, methods=["get"])
    def balances(self, request):
        employee_id = request.query_params.get("employee")
        own = getattr(request.user, "employee", None)
        if employee_id and has_role(request.user, *HR, Role.PRINCIPAL, Role.FINANCE, Role.SUPERVISOR):
            employee = scope_queryset(request.user, Employee.objects.all()).filter(pk=employee_id).first()
        else:
            employee = own
        if employee is None:
            return Response({"code": "not_found", "detail": "No employee in scope."}, status=404)
        return Response({"employee": employee.id, "balances": balances_for(employee)})
