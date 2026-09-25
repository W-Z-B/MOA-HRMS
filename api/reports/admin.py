from django.contrib import admin

from reports.models import ReportDefinition


@admin.register(ReportDefinition)
class ReportDefinitionAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "is_ministry_pack")
