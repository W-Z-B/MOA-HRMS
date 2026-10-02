"""F06 endpoints: leave types, requests with workflow transitions, evidence, receipts, ledger, balances."""

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from audit.services import record, snapshot
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from leave import serializers
from leave.models import Entitlement, LeaveLedger, LeaveRequest, LeaveType
from leave.rules import assess
from leave.services import balances_for
from leave.workflow import LEAVE_REQUEST, WorkflowError
from people.models import Document, Employee

HR = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)
# States in which the employee may still attach or replace the evidence.
OPEN_STATES = (
    LeaveRequest.State.DRAFT,
    LeaveRequest.State.SUBMITTED,
    LeaveRequest.State.SUPERVISOR_APPROVED,
)


def _refuse(code: str, detail: str, http_status: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"code": code, "detail": detail}, status=http_status)


class LeaveTypeViewSet(AuditedModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = serializers.LeaveTypeSerializer
    write_roles = (Role.HR_MANAGER, Role.ADMINISTRATOR)


class EntitlementViewSet(AuditedModelViewSet):
    """Leave and sick-day entitlements written into a contract. HR maintains them."""

    queryset = Entitlement.objects.none()  # scoped per request in get_queryset; fails closed
    serializer_class = serializers.EntitlementSerializer
    read_roles = HR + (Role.PRINCIPAL, Role.FINANCE, Role.AUDITOR)
    write_roles = HR

    def get_queryset(self):
        qs = Entitlement.objects.select_related("leave_type", "contract__assignment__employee")
        qs = scope_queryset(self.request.user, qs, campus_field="contract__assignment__employee__campus")
        params = self.request.query_params
        if params.get("contract"):
            qs = qs.filter(contract_id=params["contract"])
        if params.get("employee"):
            qs = qs.filter(contract__assignment__employee_id=params["employee"])
        return qs

    def _check_scope(self, serializer):
        contract = serializer.validated_data.get("contract") or getattr(serializer.instance, "contract", None)
        if contract is not None and not campus_in_scope(
            self.request.user, contract.assignment.employee.campus_id
        ):
            self.permission_denied(self.request, message="That employee is not on a campus you work with.")

    def perform_create(self, serializer):
        self._check_scope(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._check_scope(serializer)
        super().perform_update(serializer)


class LeaveRequestViewSet(AuditedModelViewSet):
    """Employees see and create their own requests; managers those sent to them; HR their campuses."""

    queryset = LeaveRequest.objects.none()  # scoped per request in get_queryset; fails closed
    serializer_class = serializers.LeaveRequestSerializer
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get_queryset(self):
        user = self.request.user
        qs = LeaveRequest.objects.select_related("employee", "leave_type", "manager").prefetch_related(
            "decisions"
        )
        own_or_mine_to_decide = Q(employee__user=user) | Q(manager__user=user)
        if has_role(user, *HR, Role.PRINCIPAL, Role.AUDITOR):
            scoped = scope_queryset(user, LeaveRequest.objects.all(), campus_field="employee__campus")
            qs = qs.filter(Q(pk__in=scoped.values("pk")) | own_or_mine_to_decide)
        elif has_role(user, Role.SUPERVISOR):
            team = Q(employee__campus__in=scope_queryset(user, Employee.objects.all()).values("campus"))
            qs = qs.filter(own_or_mine_to_decide | team)
        else:
            qs = qs.filter(own_or_mine_to_decide)
        employee = self.request.query_params.get("employee")
        state = self.request.query_params.get("state")
        if employee:
            qs = qs.filter(employee_id=employee)
        if state:
            qs = qs.filter(state=state)
        return qs.distinct()

    def _is_owner(self, instance) -> bool:
        own = getattr(self.request.user, "employee", None)
        return own is not None and own.pk == instance.employee_id

    def _may_edit(self, instance) -> bool:
        return self._is_owner(instance) or has_role(self.request.user, *HR)

    def perform_create(self, serializer):
        user = self.request.user
        employee = serializer.validated_data.get("employee")
        own = getattr(user, "employee", None)
        if not has_role(user, *HR) and (own is None or employee != own):
            self.permission_denied(self.request, message="You may only create leave requests for yourself.")
        if employee != own and not campus_in_scope(user, employee.campus_id):
            self.permission_denied(self.request, message="That employee is not on a campus you work with.")
        super().perform_create(serializer)

    def perform_update(self, serializer):
        instance = serializer.instance
        if not self._may_edit(instance):
            self.permission_denied(self.request, message="Only the employee or HR may change this request.")
        if instance.state != LeaveRequest.State.DRAFT:
            self.permission_denied(
                self.request, message="Only a draft can be changed. Cancel this request and make a new one."
            )
        if serializer.validated_data.get("employee", instance.employee) != instance.employee:
            self.permission_denied(self.request, message="A request cannot be moved to another employee.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if not self._may_edit(instance) or instance.state != LeaveRequest.State.DRAFT:
            self.permission_denied(self.request, message="Only a draft can be deleted. Cancel it instead.")
        super().perform_destroy(instance)

    @action(detail=False, methods=["post"])
    def check(self, request):
        """Assess dates before anything is saved: days, balance left, evidence needed, what blocks it."""
        data = serializers.CheckSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        employee = getattr(request.user, "employee", None)
        if values.get("employee") and has_role(request.user, *HR):
            in_scope = scope_queryset(request.user, Employee.objects.all())
            employee = in_scope.filter(pk=values["employee"]).first()
        if employee is None:
            return _refuse("not_found", "No employee in scope.", status.HTTP_404_NOT_FOUND)
        exclude = LeaveRequest.objects.filter(pk=values.get("exclude"), employee=employee).first()
        result = assess(
            employee, values["leave_type"], values["from_date"], values["to_date"], exclude=exclude
        )
        return Response(result.as_dict())

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
        # The decisions were read before this one was made.
        getattr(instance, "_prefetched_objects_cache", {}).clear()
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["get", "post"])
    def evidence(self, request, pk=None):
        """POST attaches the employee's evidence. GET downloads it: the employee and HR only."""
        instance = self.get_object()
        if not self._may_edit(instance):
            return _refuse(
                "forbidden",
                "Evidence is seen by the employee and Human Resources only.",
                status.HTTP_403_FORBIDDEN,
            )
        if request.method == "GET":
            return self._download_evidence(request, instance)
        if instance.state not in OPEN_STATES:
            return _refuse("closed", "This request has been decided; evidence can no longer be added.")
        data = serializers.EvidenceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        leave_type = instance.leave_type
        medical = leave_type.evidence_is_medical
        with transaction.atomic():
            document = Document.objects.create(
                employee=instance.employee,
                doc_type="medical" if medical else "leave_evidence",
                title=(
                    f"{leave_type.evidence_name}: {leave_type.name.lower()} "
                    f"{instance.from_date:%d/%m/%Y} to {instance.to_date:%d/%m/%Y}"
                ),
                file=data.validated_data["file"],
                classification=(
                    Document.Classification.MEDICAL if medical else Document.Classification.CONFIDENTIAL
                ),
                created_by=request.user,
                updated_by=request.user,
            )
            record(request, "create", document, before=None, after=snapshot(document))
            before = {"evidence": instance.evidence_id}
            instance.evidence = document
            instance.updated_by = request.user
            instance.save(update_fields=["evidence", "updated_by", "updated_at"])
            record(request, "attach_evidence", instance, before=before, after={"evidence": document.id})
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def _download_evidence(self, request, instance):
        document = instance.evidence
        if document is None:
            return _refuse("not_found", "No evidence is attached.", status.HTTP_404_NOT_FOUND)
        record(request, "download", document, after={"title": document.title, "leave_request": instance.id})
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.download_name)

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        instance = self.get_object()
        if instance.receipt is None:
            return _refuse("not_issued", "A receipt is issued on final approval.", status.HTTP_404_NOT_FOUND)
        return Response(instance.receipt)


class LeaveLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LeaveLedger.objects.none()  # scoped per request in get_queryset; fails closed
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
