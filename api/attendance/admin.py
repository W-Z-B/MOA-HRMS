from django.contrib import admin

from attendance.models import AttendanceRecord, EmployeeShift, ShiftPattern


@admin.register(ShiftPattern)
class ShiftPatternAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "starts", "ends")


@admin.register(EmployeeShift)
class EmployeeShiftAdmin(admin.ModelAdmin):
    list_display = ("employee", "shift", "effective_from")
    autocomplete_fields = ("employee",)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "status", "source", "time_in", "time_out", "resolved")
    list_filter = ("status", "source", "resolved")
    autocomplete_fields = ("employee",)
