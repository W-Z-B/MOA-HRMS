"""F17 Reporting. Saved report definitions; the queries live in reports/queries.py."""

from django.db import models

from core.models import TimeStampedModel


class ReportDefinition(TimeStampedModel):
    key = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    roles = models.JSONField(
        default=list, help_text="Role codes allowed to run the report; empty = any staff"
    )
    is_ministry_pack = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
