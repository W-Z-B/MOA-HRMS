from django.contrib import admin

from attendance.models import AttendanceRecord, ShiftPattern

admin.site.register(ShiftPattern)
admin.site.register(AttendanceRecord)
