from django.contrib import admin

from recruitment.models import Application, ApplicationCheckLog, Candidate, Hire, Interview, Vacancy


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ("title", "position", "state", "opens_on", "closes_on")
    list_filter = ("state",)


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "retention_date")
    search_fields = ("first_name", "last_name", "email")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "vacancy", "state", "reference")
    list_filter = ("state",)
    search_fields = ("reference", "candidate__first_name", "candidate__last_name")


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("application", "interviewer", "starts_at", "ends_at", "state")
    list_filter = ("state",)


@admin.register(Hire)
class HireAdmin(admin.ModelAdmin):
    list_display = ("candidate", "vacancy", "start_date", "employee")


@admin.register(ApplicationCheckLog)
class ApplicationCheckLogAdmin(admin.ModelAdmin):
    list_display = ("reference", "matched", "at", "source_ip")
    list_filter = ("matched",)
