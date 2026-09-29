from django.contrib import admin

from leave.models import Entitlement, LeaveDecision, LeaveLedger, LeaveRequest, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "annual_entitlement_days",
        "accrues_monthly",
        "is_paid",
        "requires_evidence",
        "over_balance",
    )


@admin.register(LeaveLedger)
class LeaveLedgerAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "entry_date", "days", "reason")
    list_filter = ("leave_type", "reason")


class LeaveDecisionInline(admin.TabularInline):
    model = LeaveDecision
    extra = 0
    can_delete = False
    readonly_fields = ("step", "outcome", "actor", "actor_name", "comment", "decided_at")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "from_date", "to_date", "days", "state", "manager")
    list_filter = ("state", "leave_type")
    readonly_fields = ("receipt", "days_beyond")
    inlines = [LeaveDecisionInline]


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ("contract", "leave_type", "annual_days")
    list_filter = ("leave_type",)
