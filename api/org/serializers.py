from rest_framework import serializers

from core.serializers import TimeStampedSerializer
from org.models import Campus, Grade, OrgUnit, Position, SalaryScale


class CampusSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = Campus
        fields = ("id", "code", "name", "address", "region", "created_at", "updated_at")


class OrgUnitSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = OrgUnit
        fields = ("id", "code", "name", "unit_type", "parent", "campus", "head", "created_at", "updated_at")


class SalaryScaleSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = SalaryScale
        fields = ("id", "code", "name", "created_at", "updated_at")


class GradeSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = Grade
        fields = ("id", "scale", "code", "step", "amount", "effective_from", "created_at", "updated_at")


class PositionSerializer(TimeStampedSerializer):
    is_vacant = serializers.BooleanField(read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Position
        fields = (
            "id",
            "number",
            "title",
            "grade",
            "org_unit",
            "org_unit_name",
            "status",
            "fte",
            "is_vacant",
            "created_at",
            "updated_at",
        )
