from django.contrib import admin

from org.models import Campus, Grade, OrgUnit, Position, SalaryScale


@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "region")


@admin.register(OrgUnit)
class OrgUnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "unit_type", "campus", "parent")
    list_filter = ("campus", "unit_type")
    search_fields = ("code", "name")


@admin.register(SalaryScale)
class SalaryScaleAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("scale", "code", "step", "amount", "effective_from")
    list_filter = ("scale",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "grade", "org_unit", "status", "fte")
    list_filter = ("status", "org_unit__campus")
    search_fields = ("number", "title")
