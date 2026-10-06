from django.contrib import admin

from training.models import TrainingRecord, TrainingRequirement

admin.site.register(TrainingRecord)


@admin.register(TrainingRequirement)
class TrainingRequirementAdmin(admin.ModelAdmin):
    list_display = ("title", "course_code", "post_title", "org_unit", "campus", "due_days", "renewal_months")
    list_filter = ("is_active", "campus")
    search_fields = ("title", "course_code", "post_title")
