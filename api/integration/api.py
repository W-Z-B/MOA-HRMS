"""Integration API consumed by the sibling systems. The HRMS is the system of record for staff and org units.

No sensitive identifiers (NIS, TIN, national ID) are ever exposed here.
"""

from django.urls import path
from django.utils.dateparse import parse_datetime
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from audit.models import AuditLog
from integration.auth import ServiceKeyAuthentication, scope
from org.models import Campus, OrgUnit
from people.models import Employee
from training.models import TrainingRecord


class Pager(PageNumberPagination):
    page_size = 200
    max_page_size = 500
    page_size_query_param = "page_size"


def _audit(request, action: str, detail: dict) -> None:
    AuditLog.objects.create(
        action=f"integration:{action}",
        entity="integration.serviceclient",
        entity_id=request.auth.pk,
        after={"client": request.auth.name, **detail},
        source_ip=request.META.get("REMOTE_ADDR") or None,
    )


def _staff_row(employee: Employee) -> dict:
    current = employee.current_assignment
    unit = current.position.org_unit if current else None
    return {
        "employee_no": employee.employee_no,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "other_names": employee.other_names,
        "full_name": employee.full_name,
        "email": employee.email,
        "campus_code": employee.campus.code,
        "status": employee.status,
        "position_title": current.position.title if current else None,
        "appointment_type": current.appointment_type if current else None,
        "unit_code": unit.code if unit else None,
        "unit_name": unit.name if unit else None,
        "updated_at": employee.updated_at.isoformat(),
    }


@api_view(["GET"])
@authentication_classes([ServiceKeyAuthentication])
@permission_classes([scope("staff:read")])
def staff(request):
    """Staff directory for sibling systems. Filters: campus (code), status, updated_since (ISO datetime)."""
    qs = (
        Employee.objects.select_related("campus")
        .prefetch_related("assignments__position__org_unit")
        .order_by("employee_no")
    )
    params = request.query_params
    if params.get("campus"):
        qs = qs.filter(campus__code=params["campus"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("updated_since"):
        since = parse_datetime(params["updated_since"])
        if since is None:
            return Response(
                {"code": "bad_request", "detail": "updated_since must be an ISO datetime."}, status=400
            )
        qs = qs.filter(updated_at__gte=since)
    pager = Pager()
    page = pager.paginate_queryset(qs, request)
    _audit(request, "staff.read", {"count": len(page)})
    return pager.get_paginated_response([_staff_row(e) for e in page])


@api_view(["GET"])
@authentication_classes([ServiceKeyAuthentication])
@permission_classes([scope("org:read")])
def org(request):
    """Campuses and organisational units, so sibling systems share the same codes."""
    campuses = [{"code": c.code, "name": c.name, "region": c.region} for c in Campus.objects.all()]
    units = [
        {
            "code": u.code,
            "name": u.name,
            "unit_type": u.unit_type,
            "campus_code": u.campus.code,
            "parent_code": u.parent.code if u.parent else None,
            "head_employee_no": u.head.employee_no if u.head else None,
        }
        for u in OrgUnit.objects.select_related("campus", "parent", "head")
    ]
    _audit(request, "org.read", {"campuses": len(campuses), "units": len(units)})
    return Response({"campuses": campuses, "units": units})


class TrainingCompletionSerializer(serializers.Serializer):
    external_ref = serializers.CharField(max_length=120)
    employee_no = serializers.CharField(max_length=20)
    course = serializers.CharField(max_length=160)
    provider = serializers.CharField(max_length=120, required=False, default="GSA LMS")
    starts = serializers.DateField()
    ends = serializers.DateField(required=False, allow_null=True)
    certification = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    expiry_date = serializers.DateField(required=False, allow_null=True)


@api_view(["POST"])
@authentication_classes([ServiceKeyAuthentication])
@permission_classes([scope("training:write")])
def training_completions(request):
    """Record a staff training completion reported by the LMS. Idempotent on external_ref."""
    data = TrainingCompletionSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    values = dict(data.validated_data)
    employee = Employee.objects.filter(employee_no=values.pop("employee_no")).first()
    if employee is None:
        return Response({"code": "unknown_employee", "detail": "No employee with that number."}, status=404)
    external_ref = values.pop("external_ref")
    record, created = TrainingRecord.objects.update_or_create(
        external_ref=external_ref, defaults={"employee": employee, **values}
    )
    _audit(request, "training.write", {"external_ref": external_ref, "created": created})
    return Response(
        {"id": record.id, "external_ref": external_ref, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


urlpatterns = [
    path("staff/", staff, name="integration-staff"),
    path("org/", org, name="integration-org"),
    path("training-completions/", training_completions, name="integration-training"),
]
