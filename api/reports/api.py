"""GET /api/v1/reports/ lists definitions; GET /api/v1/reports/{key}/ runs one (JSON for now)."""

from django.urls import path
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from iam.permissions import RolePermission
from iam.services import has_role
from reports.models import ReportDefinition
from reports.queries import REPORTS


@api_view(["GET"])
@permission_classes([RolePermission])
def list_reports(request):
    rows = [
        {"key": d.key, "name": d.name, "description": d.description, "ministry_pack": d.is_ministry_pack}
        for d in ReportDefinition.objects.all()
        if not d.roles or has_role(request.user, *d.roles)
    ]
    return Response(rows)


@api_view(["GET"])
@permission_classes([RolePermission])
def run_report(request, key: str):
    definition = ReportDefinition.objects.filter(key=key).first()
    if definition is None or key not in REPORTS:
        return Response({"code": "not_found", "detail": "Unknown report."}, status=status.HTTP_404_NOT_FOUND)
    if definition.roles and not has_role(request.user, *definition.roles):
        return Response({"code": "forbidden", "detail": "Your role cannot run this report."}, status=403)
    fmt = request.query_params.get("output", "json")  # "format" is reserved by DRF renderers
    if fmt != "json":
        return Response(
            {
                "code": "not_implemented",
                "detail": "PDF and Excel output arrive with the report pack (Sprint 6).",
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
    campus = request.query_params.get("campus")
    kwargs = {"campus_id": int(campus)} if campus and key == "establishment-vs-actual" else {}
    return Response({"key": key, "name": definition.name, "rows": REPORTS[key](**kwargs)})


urlpatterns = [
    path("", list_reports, name="report-list"),
    path("<slug:key>/", run_report, name="report-run"),
]
