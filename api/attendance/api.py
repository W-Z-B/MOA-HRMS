"""F07 read-only endpoints for the scaffold. Entry, import and overtime approval arrive in Release 2."""

from rest_framework import viewsets
from rest_framework.routers import DefaultRouter

from attendance.models import AttendanceRecord, ShiftPattern
from core.serializers import TimeStampedSerializer
from iam.permissions import RolePermission


class ShiftPatternSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = ShiftPattern
        fields = ("id", "code", "name", "starts", "ends", "working_days")


class AttendanceRecordSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = AttendanceRecord
        fields = (
            "id",
            "employee",
            "date",
            "shift",
            "time_in",
            "time_out",
            "hours",
            "overtime_hours",
            "source",
        )


class ShiftPatternViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ShiftPattern.objects.all()
    serializer_class = ShiftPatternSerializer
    permission_classes = [RolePermission]


class AttendanceRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AttendanceRecord.objects.select_related("employee", "shift")
    serializer_class = AttendanceRecordSerializer
    permission_classes = [RolePermission]


router = DefaultRouter()
router.register("shifts", ShiftPatternViewSet)
router.register("records", AttendanceRecordViewSet)
urlpatterns = router.urls
