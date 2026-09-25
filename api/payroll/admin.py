from django.contrib import admin

from payroll.models import PayrollPeriod, StatutoryRate


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ("period", "state", "locked_at", "exported_at")


@admin.register(StatutoryRate)
class StatutoryRateAdmin(admin.ModelAdmin):
    list_display = ("kind", "value", "effective_from", "source_reference")
    list_filter = ("kind",)
