from django.contrib import admin

from leave.models import LeaveLedger, LeaveRequest, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "annual_entitlement_days",
        "accrues_monthly",
        "is_paid",
        "requires_evidence",
    )


@admin.register(LeaveLedger)
class LeaveLedgerAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "entry_date", "days", "reason")
    list_filter = ("leave_type", "reason")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "from_date", "to_date", "days", "state")
    list_filter = ("state", "leave_type")
