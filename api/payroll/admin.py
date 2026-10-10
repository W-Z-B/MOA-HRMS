from django.contrib import admin

from payroll.models import PayRun, Payslip, StatutoryRate


@admin.register(PayRun)
class PayRunAdmin(admin.ModelAdmin):
    list_display = ("period", "state", "calculated_at", "approved_at", "disbursed_at", "total_net")


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("employee", "pay_run", "gross", "net")
    autocomplete_fields = ("employee",)


@admin.register(StatutoryRate)
class StatutoryRateAdmin(admin.ModelAdmin):
    list_display = ("kind", "value", "effective_from", "source_reference")
    list_filter = ("kind",)
