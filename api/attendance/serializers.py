"""H-M02 serializers: shift patterns, the daily record, and the actions on it."""

from rest_framework import serializers

from attendance.models import AttendanceRecord, EmployeeShift, ShiftPattern
from core.serializers import InScope, TimeStampedSerializer
from people.models import Employee


class ShiftPatternSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = ShiftPattern
        fields = ("id", "code", "name", "starts", "ends", "working_days")


class EmployeeShiftSerializer(TimeStampedSerializer):
    employee = InScope(Employee)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    shift_name = serializers.CharField(source="shift.name", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = EmployeeShift
        fields = ("id", "employee", "employee_name", "shift", "shift_name", "effective_from")


class AttendanceRecordSerializer(TimeStampedSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    campus_name = serializers.CharField(source="employee.campus.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = AttendanceRecord
        fields = (
            "id",
            "employee",
            "employee_name",
            "campus_name",
            "date",
            "shift",
            "scheduled_in",
            "scheduled_out",
            "time_in",
            "time_out",
            "hours",
            "overtime_hours",
            "source",
            "source_display",
            "status",
            "status_display",
            "leave_request",
            "note",
            "resolved",
            "is_mine",
        )
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + (
            "scheduled_in",
            "scheduled_out",
            "hours",
            "overtime_hours",
            "status",
            "leave_request",
        )

    def get_is_mine(self, instance) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        own = getattr(user, "employee", None)
        return own is not None and own.pk == instance.employee_id


class CorrectionSerializer(serializers.Serializer):
    """What HR sends to fix a day (attendance.services.correct)."""

    time_in = serializers.TimeField(required=False, allow_null=True)
    time_out = serializers.TimeField(required=False, allow_null=True)
    clear = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(required=True, max_length=300)
