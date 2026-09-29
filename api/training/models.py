"""F09 Training and development (Release 2). Scaffold: training records with certification expiry."""

from django.db import models

from core.models import TimeStampedModel


class TrainingRecord(TimeStampedModel):
    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="training")
    course = models.CharField(max_length=160)
    provider = models.CharField(max_length=120, blank=True)
    starts = models.DateField()
    ends = models.DateField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    certification = models.CharField(max_length=160, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    bond_months = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-starts"]

    def __str__(self) -> str:
        return f"{self.employee} {self.course}"
