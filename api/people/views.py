"""F02 to F04 endpoints: employees (campus-scoped), assignments, contracts, documents, and the rest of
the staff record (qualifications, previous employment, dependants, emergency contacts, bank accounts)."""

from datetime import datetime, time

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers as drf
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from audit.models import AuditLog
from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import SelfServicePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from notifications.models import Notification
from notifications.services import notify, users_with_role
from people import history, serializers
from people.models import (
    Assignment,
    BankAccount,
    Contract,
    Dependant,
    Document,
    EmergencyContact,
    Employee,
    PreviousEmployment,
    Qualification,
)
from people.services import terms_for

HR_WRITE = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)
STAFF_READ = HR_WRITE + (Role.PRINCIPAL, Role.FINANCE, Role.SUPERVISOR, Role.AUDITOR)
HISTORY_READ = HR_WRITE + (Role.PRINCIPAL, Role.AUDITOR)
PRIVATE_READ = HR_WRITE + (Role.AUDITOR,)
DEPENDANT_READ = HR_WRITE + (Role.FINANCE, Role.AUDITOR)
# Bank details are a financial record (sensitive under the Data Protection Act 2023).
BANK_READ = HR_WRITE + (Role.FINANCE, Role.AUDITOR)
BANK_PROPOSE = HR_WRITE + (Role.FINANCE,)
BANK_DECIDE = (Role.HR_MANAGER, Role.FINANCE, Role.ADMINISTRATOR)


def _search(qs, text: str):
    """Full-text search on names plus prefix matching on names and employee number.

    PostgreSQL full-text handles whole words in any order ("persaud asha"); the prefix clauses keep
    partial typing ("E00", "Pers") working, which the directory screen relies on.
    """
    prefix = (
        Q(first_name__istartswith=text) | Q(last_name__istartswith=text) | Q(employee_no__istartswith=text)
    )
    if connection.vendor != "postgresql":
        return qs.filter(prefix | Q(other_names__icontains=text))
    vector = SearchVector("first_name", "last_name", "other_names", "employee_no", config="simple")
    query = SearchQuery(text, config="simple", search_type="websearch")
    return qs.annotate(search=vector).filter(Q(search=query) | prefix)


class InScopeWrites:
    """Writes may name only an employee the user may see.

    Reading and editing an existing record are scoped by get_queryset, but a new record (or an edit that
    moves one) names its employee in the body; without this check a campus-scoped HR officer could file
    a record against an employee on another campus.
    """

    def target_employee(self, serializer):
        data = serializer.validated_data
        if "employee" in data:
            return data["employee"]
        return getattr(serializer.instance, "employee", None)

    def check_scope(self, serializer):
        employee = self.target_employee(serializer)
        if employee is not None and not campus_in_scope(self.request.user, employee.campus_id):
            self.permission_denied(self.request, message="That employee is not on a campus you work with.")

    def perform_create(self, serializer):
        self.check_scope(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self.check_scope(serializer)
        super().perform_update(serializer)


class EmployeeRecords(InScopeWrites, AuditedModelViewSet):
    """Records that belong to one employee: scoped by that employee's campus and filtered by ?employee=."""

    def get_queryset(self):
        qs = self.queryset.model.objects.select_related("employee")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        employee = self.request.query_params.get("employee")
        return qs.filter(employee_id=employee) if employee else qs


class EmployeeViewSet(AuditedModelViewSet):
    # Every request is scoped in get_queryset. The empty default fails closed and names the model for
    # the API schema; the viewsets below follow the same pattern.
    queryset = Employee.objects.none()
    serializer_class = serializers.EmployeeSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE
    # Changes to the personal record say why (item 1.08); the reason is kept on the audit row.
    reason_required_for = ("update", "partial_update")

    def get_queryset(self):
        qs = Employee.objects.select_related("campus").prefetch_related("assignments__position")
        qs = scope_queryset(self.request.user, qs)
        params = self.request.query_params
        if params.get("q"):
            qs = _search(qs, params["q"])
        if params.get("campus"):
            qs = qs.filter(campus_id=params["campus"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("has_account") in ("0", "1"):
            qs = qs.filter(user__isnull=params["has_account"] == "0")
        if params.get("org_unit"):
            qs = qs.filter(
                assignments__position__org_unit_id=params["org_unit"], assignments__status="active"
            )
        return qs.distinct()

    def _check_campus(self, serializer):
        campus = serializer.validated_data.get("campus")
        if campus is not None and not campus_in_scope(self.request.user, campus.id):
            self.permission_denied(self.request, message="You may only file staff on a campus you work with.")

    def perform_create(self, serializer):
        self._check_campus(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._check_campus(serializer)
        super().perform_update(serializer)

    @action(detail=True, methods=["post"], url_path="reveal")
    def reveal(self, request, pk=None):
        """Return the full identifiers. Restricted to HR roles and always audited."""
        if not has_role(request.user, *HR_WRITE):
            return Response(
                {"code": "forbidden", "detail": "Only HR roles may reveal identifiers."}, status=403
            )
        employee = self.get_object()
        record(request, "reveal", employee, after={"fields": ["national_id", "nis_no", "tin"]})
        return Response(serializers.EmployeeRevealSerializer(employee).data)

    @extend_schema(
        responses={200: serializers.HistoryEntrySerializer(many=True), 403: ErrorSerializer},
        summary="Every change to this person's file, newest first, with who, when and why",
    )
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        if not has_role(request.user, *HISTORY_READ):
            self.permission_denied(request, message="Your role cannot read the history of a file.")
        employee = self.get_object()
        rows = (
            AuditLog.objects.filter(
                Q(subject=employee.pk) | Q(entity="people.employee", entity_id=employee.pk)
            )
            .exclude(action__in=history.NOT_FILE_HISTORY)
            .select_related("actor")
            .order_by("-at", "-id")[:500]
        )
        record(request, "view_history", employee, after={"listed": len(rows)})
        return Response([history.entry(row) for row in rows])

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE, required=True, description="YYYY-MM-DD")],
        responses={200: serializers.RecordAsAtSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        summary="The personal record as it stood at the end of a day",
    )
    @action(detail=True, methods=["get"], url_path="as-at")
    def as_at(self, request, pk=None):
        if not has_role(request.user, *HISTORY_READ):
            self.permission_denied(request, message="Your role cannot read the history of a file.")
        day = parse_date(request.query_params.get("date") or "")
        if day is None:
            return Response({"code": "bad_request", "detail": "Give a date as YYYY-MM-DD."}, status=400)
        employee = self.get_object()
        end_of_day = timezone.make_aware(datetime.combine(day, time.max))
        if employee.created_at > end_of_day:
            return Response(
                {"code": "not_found", "detail": "This person was not on file yet on that day."}, status=404
            )
        first_change_after = (
            AuditLog.objects.filter(
                entity="people.employee", entity_id=employee.pk, action="update", at__gt=end_of_day
            )
            .order_by("at", "id")
            .first()
        )
        state = first_change_after.before if first_change_after else snapshot(employee)
        record(request, "view_history", employee, after={"as_at": day.isoformat()})
        return Response(
            {"date": day, "current": first_change_after is None, "record": history.visible(state)}
        )


class AssignmentViewSet(InScopeWrites, AuditedModelViewSet):
    queryset = Assignment.objects.none()
    serializer_class = serializers.AssignmentSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE

    def get_queryset(self):
        qs = Assignment.objects.select_related("employee", "position", "position__org_unit")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        employee = self.request.query_params.get("employee")
        return qs.filter(employee_id=employee) if employee else qs


class ContractViewSet(InScopeWrites, AuditedModelViewSet):
    queryset = Contract.objects.none()
    serializer_class = serializers.ContractSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE

    def target_employee(self, serializer):
        assignment = serializer.validated_data.get("assignment") or getattr(
            serializer.instance, "assignment", None
        )
        return assignment.employee if assignment else None

    def get_queryset(self):
        qs = Contract.objects.select_related("assignment__employee", "assignment__position__grade")
        qs = scope_queryset(self.request.user, qs, campus_field="assignment__employee__campus")
        employee = self.request.query_params.get("employee")
        return qs.filter(assignment__employee_id=employee) if employee else qs

    @action(detail=False, methods=["get"], permission_classes=[SelfServicePermission])
    def mine(self, request):
        """The caller's own appointment, contract terms, entitlements and manager."""
        employee = getattr(request.user, "employee", None)
        if employee is None:
            return Response(
                {"code": "not_found", "detail": "Your account is not linked to an employee record."},
                status=404,
            )
        return Response(terms_for(employee))


class DocumentViewSet(InScopeWrites, AuditedModelViewSet):
    queryset = Document.objects.none()
    serializer_class = serializers.DocumentSerializer
    parser_classes = (MultiPartParser, FormParser)
    read_roles = STAFF_READ
    write_roles = HR_WRITE

    def get_queryset(self):
        qs = Document.objects.select_related("employee")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        if not has_role(self.request.user, Role.HR_MANAGER, Role.ADMINISTRATOR):
            qs = qs.exclude(classification=Document.Classification.MEDICAL)
        employee = self.request.query_params.get("employee")
        return qs.filter(employee_id=employee) if employee else qs

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        """Stream the file to an authorised user. Files are never served from a public media URL."""
        document = self.get_object()  # applies campus scoping and the medical restriction
        record(request, "download", document, after={"title": document.title, "version": document.version})
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.download_name)


class QualificationViewSet(EmployeeRecords):
    queryset = Qualification.objects.none()
    serializer_class = serializers.QualificationSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE


class PreviousEmploymentViewSet(EmployeeRecords):
    queryset = PreviousEmployment.objects.none()
    serializer_class = serializers.PreviousEmploymentSerializer
    read_roles = PRIVATE_READ
    write_roles = HR_WRITE


class DependantViewSet(EmployeeRecords):
    queryset = Dependant.objects.none()
    serializer_class = serializers.DependantSerializer
    read_roles = DEPENDANT_READ
    write_roles = HR_WRITE


class EmergencyContactViewSet(EmployeeRecords):
    """Supervisors may read these: they are the ones who call when something happens at work."""

    queryset = EmergencyContact.objects.none()
    serializer_class = serializers.EmergencyContactSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE


def _name(user) -> str:
    return user.get_full_name() or user.get_username()


class BankAccountViewSet(EmployeeRecords):
    """Bank details: proposed by HR or Finance, in force only once a second person approves (item 1.07).

    Nothing is edited in place. A change is a new proposal; approving it replaces the account in use,
    and the employee is told, so that a change they did not ask for is noticed at once.
    """

    queryset = BankAccount.objects.none()
    serializer_class = serializers.BankAccountSerializer
    read_roles = BANK_READ
    write_roles = BANK_PROPOSE
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return super().get_queryset().select_related("created_by", "decided_by")

    def perform_create(self, serializer):
        employee = serializer.validated_data["employee"]
        if BankAccount.objects.filter(employee=employee, state=BankAccount.State.PENDING).exists():
            raise drf.ValidationError(
                {"employee": ["A change is already waiting for approval. Approve or reject it first."]}
            )
        try:
            with transaction.atomic():
                super().perform_create(serializer)
        except IntegrityError as exc:
            raise drf.ValidationError({"employee": ["A change is already waiting for approval."]}) from exc
        account = serializer.instance
        approvers = {
            user
            for code in BANK_DECIDE
            for user in users_with_role(code, campus=employee.campus)
            if user.pk != self.request.user.pk
        }
        notify(
            approvers,
            title=f"Bank details to approve: {employee.full_name}",
            body=f"{_name(self.request.user)} proposed new bank details. A second person must approve them.",
            link=f"/people/{employee.id}",
            kind=Notification.Kind.APPROVAL,
            dedupe_key=f"bank:{account.id}:pending",
        )

    def _decision(self, request) -> tuple[BankAccount | None, Response | None]:
        if not has_role(request.user, *BANK_DECIDE):
            self.permission_denied(
                request, message="Only the HR Manager, Finance or an administrator decide."
            )
        account = self.get_object()
        if account.state != BankAccount.State.PENDING:
            return None, Response(
                {"code": "decided", "detail": "This change has already been decided."}, status=409
            )
        if account.created_by_id == request.user.pk:
            return None, Response(
                {
                    "code": "same_person",
                    "detail": "A second person must decide: you proposed this change.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return account, None

    @extend_schema(
        request=serializers.BankDecisionSerializer,
        responses={200: serializers.BankAccountSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Approve proposed bank details (a second person)",
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        account, refusal = self._decision(request)
        if refusal:
            return refusal
        data = serializers.BankDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            before = snapshot(account)
            BankAccount.objects.filter(employee=account.employee, state=BankAccount.State.ACTIVE).update(
                state=BankAccount.State.SUPERSEDED, updated_by=request.user, updated_at=timezone.now()
            )
            account.state = BankAccount.State.ACTIVE
            account.effective_from = timezone.localdate()
            account.decided_by = request.user
            account.decided_at = timezone.now()
            account.decision_note = data.validated_data.get("note", "")
            account.updated_by = request.user
            account.save()
            record(request, "approve", account, before=before, after=snapshot(account))
        employee = account.employee
        notify(
            [employee.user],
            title="Your bank details were changed",
            body=(
                f"From {account.effective_from:%d/%m/%Y} your pay goes to {account.bank_name}, "
                f"account ending {account.account_number_last4}. If you did not ask for this change, "
                "tell Human Resources at once."
            ),
            link="/account",
            kind=Notification.Kind.ALERT,
            dedupe_key=f"bank:{account.id}:active",
        )
        return Response(self.get_serializer(account).data)

    @extend_schema(
        request=serializers.BankDecisionSerializer,
        responses={200: serializers.BankAccountSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        summary="Reject proposed bank details, with the reason",
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        account, refusal = self._decision(request)
        if refusal:
            return refusal
        data = serializers.BankDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        note = data.validated_data.get("note", "").strip()
        if not note:
            raise drf.ValidationError({"note": ["Say why the change is not approved."]})
        with transaction.atomic():
            before = snapshot(account)
            account.state = BankAccount.State.REJECTED
            account.decided_by = request.user
            account.decided_at = timezone.now()
            account.decision_note = note
            account.updated_by = request.user
            account.save()
            record(request, "reject", account, before=before, after=snapshot(account), reason=note)
        return Response(self.get_serializer(account).data)

    @extend_schema(
        request=None,
        responses={200: inline_serializer("BankReveal", fields={"account_number": drf.CharField()})},
        summary="The full account number (audited)",
    )
    @action(detail=True, methods=["post"])
    def reveal(self, request, pk=None):
        if not has_role(request.user, *BANK_DECIDE):
            self.permission_denied(
                request, message="Only the HR Manager, Finance or an administrator see it."
            )
        account = self.get_object()
        record(request, "reveal", account, after={"fields": ["account_number"]})
        return Response({"account_number": account.account_number})
