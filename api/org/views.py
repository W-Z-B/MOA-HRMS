"""F01 endpoints. Reads for any authenticated staff; writes for HR Manager and Administrator."""

from core.views import AuditedModelViewSet
from iam.models import Role
from org import serializers
from org.models import Campus, Grade, OrgUnit, Position, SalaryScale

WRITE = (Role.HR_MANAGER, Role.ADMINISTRATOR)


class CampusViewSet(AuditedModelViewSet):
    queryset = Campus.objects.all()
    serializer_class = serializers.CampusSerializer
    write_roles = WRITE


class OrgUnitViewSet(AuditedModelViewSet):
    queryset = OrgUnit.objects.select_related("campus", "parent")
    serializer_class = serializers.OrgUnitSerializer
    write_roles = WRITE
    filterset_fields = ("campus", "unit_type", "parent")

    def get_queryset(self):
        qs = super().get_queryset()
        campus = self.request.query_params.get("campus")
        return qs.filter(campus_id=campus) if campus else qs


class SalaryScaleViewSet(AuditedModelViewSet):
    queryset = SalaryScale.objects.all()
    serializer_class = serializers.SalaryScaleSerializer
    write_roles = (Role.FINANCE, Role.HR_MANAGER, Role.ADMINISTRATOR)


class GradeViewSet(AuditedModelViewSet):
    queryset = Grade.objects.select_related("scale")
    serializer_class = serializers.GradeSerializer
    write_roles = (Role.FINANCE, Role.HR_MANAGER, Role.ADMINISTRATOR)


class PositionViewSet(AuditedModelViewSet):
    queryset = Position.objects.select_related("grade", "org_unit", "org_unit__campus")
    serializer_class = serializers.PositionSerializer
    write_roles = WRITE

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("campus"):
            qs = qs.filter(org_unit__campus_id=params["campus"])
        if params.get("org_unit"):
            qs = qs.filter(org_unit_id=params["org_unit"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs
