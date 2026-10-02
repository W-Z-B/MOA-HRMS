from datetime import date

from rest_framework import serializers

from core.crypto import mask
from core.serializers import InScope, TimeStampedSerializer
from core.uploads import DOCUMENT, validate_upload
from iam.models import Role
from iam.services import has_role
from org.models import Campus, Position
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
from people.services import current_contract, hourly_rate, manager_of

IDENTIFIERS = ("national_id", "nis_no", "tin")


def _held(employee):
    """The person's own post today. A list reads it from the appointments fetched with the page, so a page
    of fifty staff costs no query per person; a single record falls back to asking."""
    if not hasattr(employee, "_held"):
        if "assignments" in getattr(employee, "_prefetched_objects_cache", {}):
            own = [
                a
                for a in employee.assignments.all()
                if a.status == Assignment.Status.ACTIVE and not a.is_acting
            ]
            employee._held = max(own, key=lambda a: a.start_date, default=None)
        else:
            employee._held = employee.current_assignment
    return employee._held


class EmployeeSerializer(TimeStampedSerializer):
    """Identifiers are write-only; responses carry masked forms. Use the reveal action for full values."""

    national_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    nis_no = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    tin = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    national_id_masked = serializers.SerializerMethodField()
    nis_no_masked = serializers.SerializerMethodField()
    tin_masked = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    campus = InScope(Campus, campus_field="id")
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    position_title = serializers.SerializerMethodField()
    unit_name = serializers.SerializerMethodField(help_text="The unit of the person's own post")
    appointment_type = serializers.SerializerMethodField(
        help_text="Permanent, contract, temporary and so on, in words, for the person's own post"
    )
    started = serializers.SerializerMethodField(help_text="When the person started in their own post")
    change_reason = serializers.CharField(
        write_only=True,
        required=False,
        max_length=300,
        help_text="Why the record is changed; required on update",
    )
    restricted = serializers.SerializerMethodField(
        help_text="Parts of the record held back from use at the person's request (item 1.46), in words"
    )

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
            "campus",
            "campus_name",
            "status",
            "position_title",
            "unit_name",
            "appointment_type",
            "started",
            "change_reason",
            "restricted",
            "created_at",
            "updated_at",
        )
        # The account a record belongs to decides who acts as that person in self-service, so it is set
        # only by opening an account (iam.accounts), never by editing the record.
        read_only_fields = (*TimeStampedSerializer.Meta.read_only_fields, "user")

    def validate(self, attrs):
        attrs.pop("change_reason", None)  # read by the view and kept on the audit row, not on the employee
        return attrs

    def get_national_id_masked(self, obj) -> str | None:
        return mask(obj.national_id)

    def get_nis_no_masked(self, obj) -> str | None:
        return mask(obj.nis_no)

    def get_tin_masked(self, obj) -> str | None:
        return mask(obj.tin)

    def get_position_title(self, obj) -> str | None:
        held = _held(obj)
        return held.position.title if held else None

    def get_unit_name(self, obj) -> str | None:
        held = _held(obj)
        return held.position.org_unit.name if held else None

    def get_appointment_type(self, obj) -> str | None:
        held = _held(obj)
        return held.get_appointment_type_display() if held else None

    def get_started(self, obj) -> date | None:
        held = _held(obj)
        return held.start_date if held else None

    def get_restricted(self, obj) -> list[str]:
        held = getattr(obj, "held_back", None)
        if held is None:
            held = obj.restrictions.filter(lifted_at__isnull=True)
        return sorted({f"{r.get_part_display()}: {r.get_ground_display().lower()}" for r in held})


class EmployeeFileSerializer(EmployeeSerializer):
    """One staff file (item 2.30): the facts shown above its tabs, which a list does not need."""

    manager_name = serializers.SerializerMethodField(help_text="Who decides the person's leave first")
    contract_type = serializers.SerializerMethodField(
        help_text="Fixed term, open ended or sessional, in words"
    )
    ends = serializers.SerializerMethodField(
        help_text="When the person's own post ends; empty when open ended"
    )
    probation_end = serializers.SerializerMethodField(help_text="Empty once confirmed in the post")

    class Meta(EmployeeSerializer.Meta):
        fields = (*EmployeeSerializer.Meta.fields, "manager_name", "contract_type", "ends", "probation_end")

    def get_manager_name(self, obj) -> str | None:
        manager = manager_of(obj)
        return manager.full_name if manager else None

    def get_contract_type(self, obj) -> str | None:
        contract = current_contract(obj)
        return contract.get_contract_type_display() if contract else None

    def get_ends(self, obj) -> date | None:
        held = _held(obj)
        return held.end_date if held else None

    def get_probation_end(self, obj) -> date | None:
        held = _held(obj)
        return held.probation_end if held and not held.confirmed_on else None


class EmployeeRevealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ("id", "employee_no", "national_id", "nis_no", "tin")
        read_only_fields = fields


class AssignmentSerializer(TimeStampedSerializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    position = InScope(Position, campus_field="org_unit__campus")
    position_title = serializers.CharField(source="position.title", read_only=True)
    pay_grade_name = serializers.SerializerMethodField(
        help_text="The grade and step paid on: never the amount"
    )

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
            "pay_grade_name",
            "confirmed_on",
            "created_at",
            "updated_at",
        )
        # Steps and confirmation change only through career events (people/careers.py).
        read_only_fields = (*TimeStampedSerializer.Meta.read_only_fields, "confirmed_on")

    def get_pay_grade_name(self, assignment) -> str:
        from org.serializers import grade_name

        return grade_name(assignment.pay_grade)

    def validate(self, attrs):
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date must not be before the start date."})
        return attrs


class ContractSerializer(TimeStampedSerializer):
    """Pay is shown to HR, Finance, the Principal and auditors. Other readers see the rest of the terms."""

    PAY_FIELDS = ("hourly_rate", "hourly_rate_effective")
    PAY_ROLES = tuple(Role.SEES_PAY)

    assignment = InScope(Assignment, campus_field="employee__campus")
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

    def get_hourly_rate_effective(self, obj) -> str | None:
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


# What a document's type needs at the least: a contract shows pay, an identity document the national ID
# number, a medical paper someone's health. Filed lower, it would show to roles that may not read it.
LEAST_CLASSIFICATION = {
    "contract": ("A contract", Document.Classification.CONFIDENTIAL),
    "id_copy": ("A copy of an identity document", Document.Classification.CONFIDENTIAL),
    "medical": ("A medical document", Document.Classification.MEDICAL),
}
_RESTRICTION = [c.value for c in Document.Classification]  # internal, confidential, medical: each narrower


class DocumentSerializer(TimeStampedSerializer):
    """The file is write-only; reads get an authenticated download URL instead of a storage path."""

    employee = InScope(Employee, help_text="An employee on a campus you work with")
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

    def get_filename(self, obj) -> str | None:
        return obj.download_name or None

    def validate_file(self, value):
        return validate_upload(value, DOCUMENT)

    def validate(self, attrs):
        doc_type = attrs.get("doc_type", getattr(self.instance, "doc_type", ""))
        if doc_type not in LEAST_CLASSIFICATION:
            return attrs
        what, least = LEAST_CLASSIFICATION[doc_type]
        if "classification" not in attrs and self.instance is None:
            attrs["classification"] = least  # not chosen: filed as its type needs
        given = attrs.get("classification", getattr(self.instance, "classification", least))
        if _RESTRICTION.index(given) < _RESTRICTION.index(least):
            needed = "Medical" if least == Document.Classification.MEDICAL else "Confidential or Medical"
            raise serializers.ValidationError({"classification": [f"{what} is filed as {needed}."]})
        return attrs

    def get_download_url(self, obj) -> str:
        return f"/api/v1/documents/{obj.id}/download/"


class QualificationSerializer(TimeStampedSerializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    document = InScope(Document, campus_field="employee__campus", required=False, allow_null=True)
    level_name = serializers.CharField(source="get_level_display", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Qualification
        fields = (
            "id",
            "employee",
            "level",
            "level_name",
            "title",
            "institution",
            "country",
            "year_awarded",
            "verified_on",
            "document",
            "created_at",
            "updated_at",
        )

    def validate_year_awarded(self, value):
        if value is not None and not 1940 <= value <= date.today().year:
            raise serializers.ValidationError(f"Enter a year between 1940 and {date.today().year}.")
        return value

    def validate(self, attrs):
        document, employee = attrs.get("document"), attrs.get("employee")
        if document is not None and employee is not None and document.employee_id != employee.id:
            raise serializers.ValidationError({"document": "That document is on another employee's file."})
        return attrs


class PreviousEmploymentSerializer(TimeStampedSerializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")

    class Meta(TimeStampedSerializer.Meta):
        model = PreviousEmployment
        fields = (
            "id",
            "employee",
            "employer",
            "position",
            "start_date",
            "end_date",
            "reason_for_leaving",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date must not be before the start date."})
        if start and start > date.today():
            raise serializers.ValidationError(
                {"start_date": "Employment before GSA cannot start in the future."}
            )
        return attrs


class DependantSerializer(TimeStampedSerializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    relationship_name = serializers.CharField(source="get_relationship_display", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Dependant
        fields = ("id", "employee", "name", "relationship", "relationship_name", "date_of_birth")

    def validate_date_of_birth(self, value):
        if value is not None and value > date.today():
            raise serializers.ValidationError("A date of birth cannot be in the future.")
        return value


class EmergencyContactSerializer(TimeStampedSerializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")

    class Meta(TimeStampedSerializer.Meta):
        model = EmergencyContact
        fields = ("id", "employee", "name", "relationship", "phone", "alternate_phone", "priority")

    def validate_phone(self, value):
        if sum(ch.isdigit() for ch in value) < 7:
            raise serializers.ValidationError("Enter a phone number with at least 7 digits.")
        return value.strip()


class BankAccountSerializer(TimeStampedSerializer):
    """The number is write-only; reads show its last four digits. Changes are proposals until approved."""

    employee = InScope(Employee, help_text="An employee on a campus you work with")
    account_number = serializers.CharField(write_only=True, max_length=40)
    account_number_masked = serializers.SerializerMethodField()
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    requested_by = serializers.IntegerField(source="created_by_id", read_only=True, allow_null=True)
    requested_by_name = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = BankAccount
        fields = (
            "id",
            "employee",
            "bank_name",
            "branch",
            "account_name",
            "account_number",
            "account_number_masked",
            "state",
            "state_name",
            "effective_from",
            "requested_by",
            "requested_by_name",
            "decided_by_name",
            "decided_at",
            "decision_note",
            "created_at",
        )
        read_only_fields = (
            "state",
            "effective_from",
            "decided_at",
            "decision_note",
            "created_at",
        )

    def validate_account_number(self, value):
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 5 or len(digits) > 30 or any(ch not in "0123456789 -" for ch in value):
            raise serializers.ValidationError(
                "Enter the account number as digits (spaces and dashes are fine)."
            )
        return digits

    def create(self, validated_data):
        validated_data["account_number_last4"] = validated_data["account_number"][-4:]
        return super().create(validated_data)

    def get_account_number_masked(self, obj) -> str:
        return f"••••{obj.account_number_last4}"

    @staticmethod
    def _name(user) -> str | None:
        return (user.get_full_name() or user.get_username()) if user else None

    def get_requested_by_name(self, obj) -> str | None:
        return self._name(obj.created_by)

    def get_decided_by_name(self, obj) -> str | None:
        return self._name(obj.decided_by)


class BankDecisionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)


class FieldChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    before = serializers.JSONField(allow_null=True, help_text="'(hidden)' for encrypted values")
    after = serializers.JSONField(allow_null=True)


class HistoryEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    at = serializers.DateTimeField()
    actor = serializers.CharField()
    action = serializers.CharField()
    action_name = serializers.CharField()
    record = serializers.CharField(help_text="Which part of the file: Personal details, Appointment, ...")
    record_id = serializers.IntegerField(allow_null=True)
    changes = FieldChangeSerializer(many=True)
    reason = serializers.CharField()
    source_ip = serializers.IPAddressField(allow_null=True)


class RecordAsAtSerializer(serializers.Serializer):
    date = serializers.DateField()
    current = serializers.BooleanField(help_text="True when nothing has changed since that day")
    record = serializers.DictField(help_text="The personal record; encrypted values show as '(hidden)'")
