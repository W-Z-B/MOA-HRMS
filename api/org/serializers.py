from rest_framework import serializers

from core.serializers import TimeStampedSerializer
from iam.models import Role
from iam.services import campus_limit, has_role
from org.models import Campus, Grade, OrgUnit, Position, SalaryScale

# Who may see which member of staff holds a post: the roles that read the staff directory.
DIRECTORY_ROLES = (
    Role.HR_OFFICER,
    Role.HR_MANAGER,
    Role.ADMINISTRATOR,
    Role.PRINCIPAL,
    Role.FINANCE,
    Role.SUPERVISOR,
    Role.AUDITOR,
)


def _may(serializer, roles) -> bool:
    request = serializer.context.get("request")
    return request is not None and has_role(request.user, *roles)


def _names(serializer, campus_id) -> bool:
    """Whether to name who holds a post or heads a unit: as the directory would, so to its roles,
    and only on the campuses the directory shows the reader."""
    if not _may(serializer, DIRECTORY_ROLES):
        return False
    context = serializer.context
    if "campus_limit" not in context:
        context["campus_limit"] = campus_limit(context["request"].user)
    limit = context["campus_limit"]
    return limit is None or campus_id in limit


class CampusSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = Campus
        fields = ("id", "code", "name", "address", "region", "created_at", "updated_at")


class OrgUnitSerializer(TimeStampedSerializer):
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    head_name = serializers.SerializerMethodField()
    unit_type_name = serializers.CharField(source="get_unit_type_display", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = OrgUnit
        fields = (
            "id",
            "code",
            "name",
            "unit_type",
            "unit_type_name",
            "parent",
            "parent_name",
            "campus",
            "campus_name",
            "head",
            "head_name",
            "created_at",
            "updated_at",
        )

    def get_head_name(self, unit) -> str | None:
        return unit.head.full_name if unit.head_id and _names(self, unit.campus_id) else None

    def validate(self, attrs):
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        campus = attrs.get("campus", getattr(self.instance, "campus", None))
        if parent is not None and campus is not None and parent.campus_id != campus.id:
            raise serializers.ValidationError({"parent": ["A unit sits under a unit on the same campus."]})
        head = attrs.get("head", getattr(self.instance, "head", None))
        if head is not None and campus is not None and head.campus_id != campus.id:
            raise serializers.ValidationError({"head": ["The head of a unit works on its campus."]})
        node = parent
        while node is not None:
            if self.instance is not None and node.pk == self.instance.pk:
                raise serializers.ValidationError({"parent": ["A unit cannot sit under itself."]})
            node = node.parent
        return attrs


class SalaryScaleSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = SalaryScale
        fields = ("id", "code", "name", "created_at", "updated_at")


class GradeSerializer(TimeStampedSerializer):
    scale_code = serializers.CharField(source="scale.code", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Grade
        fields = (
            "id",
            "scale",
            "scale_code",
            "code",
            "step",
            "amount",
            "effective_from",
            "created_at",
            "updated_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not _may(self, tuple(Role.SEES_PAY)):
            data["amount"] = None  # the scale's grades are known; what they pay is for the roles that see pay
        return data


class PositionSerializer(TimeStampedSerializer):
    is_vacant = serializers.BooleanField(read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    campus_name = serializers.CharField(source="org_unit.campus.name", read_only=True)
    grade_name = serializers.SerializerMethodField()
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    holder = serializers.SerializerMethodField(
        help_text="The substantive holder, for roles that read the directory on the post's campus"
    )

    class Meta(TimeStampedSerializer.Meta):
        model = Position
        fields = (
            "id",
            "number",
            "title",
            "grade",
            "org_unit",
            "org_unit_name",
            "campus_name",
            "grade_name",
            "status",
            "status_name",
            "fte",
            "is_vacant",
            "holder",
            "created_at",
            "updated_at",
        )

    def get_grade_name(self, position) -> str:
        return f"{position.grade.scale.code} {position.grade.code}, step {position.grade.step}"

    def get_holder(self, position) -> str | None:
        if not _names(self, position.org_unit.campus_id):
            return None
        holding = (
            position.assignments.filter(is_acting=False, status="active").select_related("employee").first()
        )
        return holding.employee.full_name if holding else None
