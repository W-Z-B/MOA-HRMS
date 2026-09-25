"""F08 Performance management (Release 2). Scaffold: cycles and appraisals; forms and sign-off later."""

from django.db import models

from core.models import TimeStampedModel


class AppraisalCycle(TimeStampedModel):
    name = models.CharField(max_length=80)
    year = models.PositiveSmallIntegerField()
    starts = models.DateField()
    ends = models.DateField()
    is_open = models.BooleanField(default=False)

    class Meta:
        unique_together = [("name", "year")]
        ordering = ["-year"]

    def __str__(self) -> str:
        return f"{self.name} {self.year}"


class Appraisal(TimeStampedModel):
    class Kind(models.TextChoices):
        PROBATION = "probation", "Probation review"
        ANNUAL = "annual", "Annual appraisal"

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        SELF_ASSESSED = "self_assessed", "Self-assessment done"
        RATED = "rated", "Supervisor rated"
        SIGNED = "signed", "Signed off"

    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="appraisals")
    cycle = models.ForeignKey(AppraisalCycle, on_delete=models.PROTECT, related_name="appraisals")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ANNUAL)
    state = models.CharField(max_length=20, choices=State.choices, default=State.DRAFT)
    overall_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=60, blank=True)  # confirmed, increment, extend_probation, ...
    form_data = models.JSONField(default=dict, blank=True, help_text="Objectives, ratings and comments")

    class Meta:
        unique_together = [("employee", "cycle", "kind")]

    def __str__(self) -> str:
        return f"{self.employee} {self.cycle} ({self.state})"
