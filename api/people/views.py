"""F02 to F04 endpoints: employees (campus-scoped), assignments, contracts, documents."""

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import connection
from django.db.models import Q
from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from audit.services import record
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.services import has_role, scope_queryset
from people import serializers
from people.models import Assignment, Contract, Document, Employee

HR_WRITE = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)
STAFF_READ = HR_WRITE + (Role.PRINCIPAL, Role.FINANCE, Role.SUPERVISOR, Role.AUDITOR)


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


class EmployeeViewSet(AuditedModelViewSet):
    serializer_class = serializers.EmployeeSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE

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
        if params.get("org_unit"):
            qs = qs.filter(
                assignments__position__org_unit_id=params["org_unit"], assignments__status="active"
            )
        return qs.distinct()

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


class AssignmentViewSet(AuditedModelViewSet):
    serializer_class = serializers.AssignmentSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE

    def get_queryset(self):
        qs = Assignment.objects.select_related("employee", "position", "position__org_unit")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        employee = self.request.query_params.get("employee")
        return qs.filter(employee_id=employee) if employee else qs


class ContractViewSet(AuditedModelViewSet):
    serializer_class = serializers.ContractSerializer
    read_roles = STAFF_READ
    write_roles = HR_WRITE

    def get_queryset(self):
        qs = Contract.objects.select_related("assignment__employee")
        return scope_queryset(self.request.user, qs, campus_field="assignment__employee__campus")


class DocumentViewSet(AuditedModelViewSet):
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
        filename = document.file.name.rsplit("/", 1)[-1]
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=filename)
