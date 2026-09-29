from rest_framework import serializers

from core.serializers import TimeStampedSerializer
from leave.models import LeaveLedger, LeaveRequest, LeaveType
from leave.services import balance, working_days
from leave.workflow import LEAVE_REQUEST


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


class LeaveRequestSerializer(TimeStampedSerializer):
    days = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    state = serializers.CharField(read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    balance_after = serializers.SerializerMethodField()
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = LeaveRequest
        fields = (
            "id",
            "employee",
            "employee_name",
            "leave_type",
            "leave_type_code",
            "from_date",
            "to_date",
            "days",
            "reason",
            "state",
            "evidence",
            "decision_comment",
            "allowed_actions",
            "balance_after",
            "created_at",
            "updated_at",
        )
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + ("decision_comment",)

    def get_allowed_actions(self, obj):
        request = self.context.get("request")
        return LEAVE_REQUEST.allowed_actions(obj, request.user) if request else []

    def get_balance_after(self, obj):
        return balance(obj.employee, obj.leave_type) - (obj.days if obj.state != "approved" else 0)

    def validate(self, attrs):
        from_date, to_date = attrs.get("from_date"), attrs.get("to_date")
        if from_date and to_date:
            if to_date < from_date:
                raise serializers.ValidationError({"to_date": "End date must not be before the start date."})
            attrs["days"] = working_days(from_date, to_date)
            if attrs["days"] == 0:
                raise serializers.ValidationError({"from_date": "The period contains no working days."})
        leave_type = attrs.get("leave_type")
        if leave_type and leave_type.requires_evidence and not attrs.get("evidence"):
            raise serializers.ValidationError(
                {"evidence": f"{leave_type.name} requires supporting evidence."}
            )
        return attrs


class TransitionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["submit", "approve", "reject", "cancel"])
    comment = serializers.CharField(required=False, allow_blank=True, max_length=300)
