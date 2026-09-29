from rest_framework import serializers

from core.crypto import mask
from core.serializers import TimeStampedSerializer
from iam.models import Role
from iam.services import has_role
from people.models import Assignment, Contract, Document, Employee
from people.services import hourly_rate

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
    """Pay is shown to HR, Finance, the Principal and auditors. Other readers see the rest of the terms."""

    PAY_FIELDS = ("hourly_rate", "hourly_rate_effective")
    PAY_ROLES = (
        Role.HR_OFFICER,
        Role.HR_MANAGER,
        Role.ADMINISTRATOR,
        Role.FINANCE,
        Role.PRINCIPAL,
        Role.AUDITOR,
    )

    employee = serializers.IntegerField(source="assignment.employee_id", read_only=True)
    hourly_rate_effective = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Contract
        fields = (
            "id",
            "assignment",
            "employee",
            "contract_type",
            "term_months",
            "signed_on",
            "document",
            "hours_per_week",
            "hourly_rate",
            "hourly_rate_effective",
            "notice_period_days",
            "other_terms",
            "created_at",
            "updated_at",
        )

    def get_hourly_rate_effective(self, obj):
        rate = hourly_rate(obj)
        return None if rate is None else str(rate)

    def validate(self, attrs):
        for name in ("hours_per_week", "hourly_rate"):
            if attrs.get(name) is not None and attrs[name] <= 0:
                raise serializers.ValidationError({name: "Enter a figure above zero, or leave it empty."})
        if attrs.get("hours_per_week") is not None and attrs["hours_per_week"] > 84:
            raise serializers.ValidationError({"hours_per_week": "That is more than 12 hours every day."})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not has_role(request.user, *self.PAY_ROLES):
            for name in self.PAY_FIELDS:
                data[name] = None
        return data


class DocumentSerializer(TimeStampedSerializer):
    """The file is write-only; reads get an authenticated download URL instead of a storage path."""

    file = serializers.FileField(write_only=True)
    filename = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Document
        fields = (
            "id",
            "employee",
            "doc_type",
            "title",
            "file",
            "filename",
            "download_url",
            "version",
            "classification",
            "retention_date",
            "created_at",
            "updated_at",
        )

    def get_filename(self, obj):
        return obj.file.name.rsplit("/", 1)[-1] if obj.file else None

    def get_download_url(self, obj):
        return f"/api/v1/documents/{obj.id}/download/"
