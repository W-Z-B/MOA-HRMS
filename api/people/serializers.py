from rest_framework import serializers

from core.crypto import mask
from core.serializers import TimeStampedSerializer
from people.models import Assignment, Contract, Document, Employee

IDENTIFIERS = ("national_id", "nis_no", "tin")


class EmployeeSerializer(TimeStampedSerializer):
    """Identifiers are write-only; responses carry masked forms. Use the reveal action for full values."""

    national_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    nis_no = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    tin = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    national_id_masked = serializers.SerializerMethodField()
    nis_no_masked = serializers.SerializerMethodField()
    tin_masked = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    position_title = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Employee
        fields = (
            "id",
            "employee_no",
            "user",
            "first_name",
            "last_name",
            "other_names",
            "full_name",
            "date_of_birth",
            "gender",
            "national_id",
            "nis_no",
            "tin",
            "national_id_masked",
            "nis_no_masked",
            "tin_masked",
            "email",
            "phone",
            "address",
            "next_of_kin_name",
            "next_of_kin_phone",
            "campus",
            "campus_name",
            "status",
            "position_title",
            "created_at",
            "updated_at",
        )

    def get_national_id_masked(self, obj):
        return mask(obj.national_id)

    def get_nis_no_masked(self, obj):
        return mask(obj.nis_no)

    def get_tin_masked(self, obj):
        return mask(obj.tin)

    def get_position_title(self, obj):
        current = obj.current_assignment
        return current.position.title if current else None


class EmployeeRevealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ("id", "employee_no", "national_id", "nis_no", "tin")
        read_only_fields = fields


class AssignmentSerializer(TimeStampedSerializer):
    position_title = serializers.CharField(source="position.title", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Assignment
        fields = (
            "id",
            "employee",
            "position",
            "position_title",
            "appointment_type",
            "start_date",
            "end_date",
            "probation_end",
            "is_acting",
            "status",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date must not be before the start date."})
        return attrs


class ContractSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = Contract
        fields = (
            "id",
            "assignment",
            "contract_type",
            "term_months",
            "signed_on",
            "document",
            "created_at",
            "updated_at",
        )


class DocumentSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = Document
        fields = (
            "id",
            "employee",
            "doc_type",
            "title",
            "file",
            "version",
            "classification",
            "retention_date",
            "created_at",
            "updated_at",
        )
