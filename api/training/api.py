from rest_framework import serializers, viewsets
from rest_framework.routers import DefaultRouter

from core.serializers import TimeStampedSerializer
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import RolePermission
from org.models import Position
from training.models import TrainingRecord, TrainingRequirement

# Who keeps the required-training list: those who keep the establishment it is drawn against.
REQUIREMENT_WRITE = (Role.HR_MANAGER, Role.ADMINISTRATOR)


class TrainingRecordSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = TrainingRecord
        fields = (
            "id",
            "employee",
            "course",
            "provider",
            "starts",
            "ends",
            "cost",
            "certification",
            "expiry_date",
            "bond_months",
        )


class TrainingRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TrainingRecord.objects.select_related("employee")
    serializer_class = TrainingRecordSerializer
    permission_classes = [RolePermission]


class TrainingRequirementSerializer(TimeStampedSerializer):
    org_unit_code = serializers.CharField(source="org_unit.code", read_only=True, default=None)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True, default=None)
    campus_code = serializers.CharField(source="campus.code", read_only=True, default=None)
    campus_name = serializers.CharField(source="campus.name", read_only=True, default=None)
    applies_to = serializers.CharField(source="describe", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = TrainingRequirement
        fields = (
            "id",
            "course_code",
            "title",
            "post_title",
            "org_unit",
            "org_unit_code",
            "org_unit_name",
            "campus",
            "campus_code",
            "campus_name",
            "applies_to",
            "due_days",
            "renewal_months",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        )

    def validate_post_title(self, value: str) -> str:
        value = value.strip()
        if value and not Position.objects.filter(title__iexact=value).exists():
            raise serializers.ValidationError("No post has this title. Use a title from the establishment.")
        return value

    def validate_renewal_months(self, value):
        if value == 0:
            raise serializers.ValidationError("Leave it empty for training taken once.")
        return value

    def validate(self, attrs):
        unit = attrs.get("org_unit", getattr(self.instance, "org_unit", None))
        campus = attrs.get("campus", getattr(self.instance, "campus", None))
        if unit is not None and campus is not None and unit.campus_id != campus.pk:
            raise serializers.ValidationError({"campus": "The unit is on another campus."})
        return attrs


class TrainingRequirementViewSet(AuditedModelViewSet):
    """Required training by post, unit and campus (item 5.24). Read by anyone signed in, kept by the HR
    Manager and administrators; retired by switching it off, never deleted."""

    queryset = TrainingRequirement.objects.select_related("org_unit", "campus")
    serializer_class = TrainingRequirementSerializer
    write_roles = REQUIREMENT_WRITE
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs


router = DefaultRouter()
router.register("records", TrainingRecordViewSet)
router.register("requirements", TrainingRequirementViewSet)
urlpatterns = router.urls
