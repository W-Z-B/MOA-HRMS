from pathlib import PurePath

from rest_framework import serializers

from core.serializers import TimeStampedSerializer
from iam.models import Role
from iam.services import has_role
from leave.models import Entitlement, LeaveDecision, LeaveLedger, LeaveRequest, LeaveType
from leave.rules import assess
from leave.services import ZERO, balance
from leave.workflow import LEAVE_REQUEST

HR = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)
DECIDED = (LeaveRequest.State.APPROVED, LeaveRequest.State.REJECTED, LeaveRequest.State.CANCELLED)
# A photograph from a phone or a scanned page. Nothing that can carry a macro or run.
EVIDENCE_TYPES = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
EVIDENCE_MAX_BYTES = 10 * 1024 * 1024


class LeaveTypeSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = LeaveType
        fields = (
            "id",
            "code",
            "name",
            "annual_entitlement_days",
            "accrues_monthly",
            "carry_over_max_days",
            "max_balance_days",
            "is_paid",
            "requires_evidence",
            "over_balance",
            "evidence_name",
            "evidence_is_medical",
            "appointment_types",
            "term_time_restricted",
            "created_at",
            "updated_at",
        )


class LeaveLedgerSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = LeaveLedger
        fields = (
            "id",
            "employee",
            "leave_type",
            "entry_date",
            "days",
            "reason",
            "request",
            "note",
            "created_at",
        )


class EntitlementSerializer(TimeStampedSerializer):
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Entitlement
        fields = (
            "id",
            "contract",
            "leave_type",
            "leave_type_code",
            "leave_type_name",
            "annual_days",
            "created_at",
            "updated_at",
        )


class LeaveDecisionSerializer(serializers.ModelSerializer):
    step_name = serializers.CharField(source="get_step_display", read_only=True)

    class Meta:
        model = LeaveDecision
        fields = ("step", "step_name", "outcome", "actor_name", "comment", "decided_at")
        read_only_fields = fields


class LeaveRequestSerializer(TimeStampedSerializer):
    days = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    state = serializers.CharField(read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    balance_after = serializers.SerializerMethodField()
    evidence_required = serializers.SerializerMethodField()
    has_evidence = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    evidence_name = serializers.CharField(source="leave_type.evidence_name", read_only=True)
    manager_name = serializers.CharField(source="manager.full_name", read_only=True, default=None)
    decisions = LeaveDecisionSerializer(many=True, read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = LeaveRequest
        fields = (
            "id",
            "employee",
            "employee_name",
            "is_mine",
            "leave_type",
            "leave_type_code",
            "leave_type_name",
            "from_date",
            "to_date",
            "days",
            "days_beyond",
            "reason",
            "state",
            "evidence",
            "evidence_name",
            "evidence_required",
            "has_evidence",
            "manager_name",
            "decision_comment",
            "decisions",
            "allowed_actions",
            "balance_after",
            "receipt",
            "created_at",
            "updated_at",
        )
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + (
            "decision_comment",
            "days_beyond",
            "receipt",
        )

    def _assessment(self, obj):
        """Only a request still to be decided is assessed; afterwards the stored figures stand."""
        if not hasattr(obj, "_assessed"):
            obj._assessed = assess(obj.employee, obj.leave_type, obj.from_date, obj.to_date, exclude=obj)
        return obj._assessed

    def get_allowed_actions(self, obj):
        request = self.context.get("request")
        return LEAVE_REQUEST.allowed_actions(obj, request.user) if request else []

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request) and obj.employee.user_id == request.user.id

    def get_balance_after(self, obj):
        if obj.state == LeaveRequest.State.APPROVED:
            return max(balance(obj.employee, obj.leave_type), ZERO)
        return self._assessment(obj).remaining

    def get_evidence_required(self, obj) -> bool:
        if obj.state in DECIDED:
            return False
        return self._assessment(obj).evidence_required

    def get_has_evidence(self, obj) -> bool:
        return obj.evidence_id is not None

    def validate(self, attrs):
        instance = self.instance
        employee = attrs.get("employee", getattr(instance, "employee", None))
        leave_type = attrs.get("leave_type", getattr(instance, "leave_type", None))
        from_date = attrs.get("from_date", getattr(instance, "from_date", None))
        to_date = attrs.get("to_date", getattr(instance, "to_date", None))
        if to_date < from_date:
            raise serializers.ValidationError({"to_date": "End date must not be before the start date."})
        result = assess(employee, leave_type, from_date, to_date, exclude=instance)
        if result.problems:
            raise serializers.ValidationError({p.field: p.detail for p in result.problems})
        attrs["days"] = result.days
        evidence = attrs.get("evidence")
        if evidence is not None:
            request = self.context.get("request")
            if request is not None and not has_role(request.user, *HR):
                raise serializers.ValidationError(
                    {"evidence": "Attach the file to the request instead of naming a document."}
                )
            if evidence.employee_id != employee.id:
                raise serializers.ValidationError({"evidence": "That document belongs to someone else."})
        return attrs


class CheckSerializer(serializers.Serializer):
    """The request form asks this before saving, so the employee sees the outcome as they type."""

    employee = serializers.IntegerField(required=False)
    leave_type = serializers.PrimaryKeyRelatedField(queryset=LeaveType.objects.all())
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    exclude = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if attrs["to_date"] < attrs["from_date"]:
            raise serializers.ValidationError({"to_date": "End date must not be before the start date."})
        return attrs


class EvidenceSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        suffix = PurePath(value.name).suffix.lower()
        if suffix not in EVIDENCE_TYPES:
            raise serializers.ValidationError("Send a photograph (JPG, PNG, HEIC) or a PDF.")
        if value.size > EVIDENCE_MAX_BYTES:
            raise serializers.ValidationError("The file is larger than 10 MB.")
        return value


class TransitionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["submit", "approve", "reject", "cancel"])
    comment = serializers.CharField(required=False, allow_blank=True, max_length=300)
