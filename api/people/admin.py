from django.contrib import admin

from people.models import Assignment, Contract, Document, Employee


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_no", "last_name", "first_name", "campus", "status")
    list_filter = ("campus", "status")
    search_fields = ("employee_no", "first_name", "last_name")
    exclude = ("national_id", "nis_no", "tin")  # identifiers are managed through the audited API only
    inlines = [AssignmentInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "position",
        "appointment_type",
        "start_date",
        "end_date",
        "is_acting",
        "status",
    )
    list_filter = ("appointment_type", "status", "is_acting")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("assignment", "contract_type", "term_months", "signed_on")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "employee", "doc_type", "classification", "version", "retention_date")
    list_filter = ("doc_type", "classification")
