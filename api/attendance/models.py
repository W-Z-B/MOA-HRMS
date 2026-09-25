"""F07 Time and attendance (Release 2). Scaffold: core record and shift pattern; import and overtime later."""

from django.db import models

from core.models import TimeStampedModel


class ShiftPattern(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    starts = models.TimeField()
    ends = models.TimeField()
    working_days = models.JSONField(default=list, help_text="ISO weekday numbers, 1 = Monday")

    def __str__(self) -> str:
        return self.name


class AttendanceRecord(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual entry"
        IMPORT = "import", "Spreadsheet import"
        DEVICE = "device", "Biometric device"

    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="attendance")
    date = models.DateField()
    shift = models.ForeignKey(ShiftPattern, null=True, blank=True, on_delete=models.SET_NULL)
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)

    class Meta:
        unique_together = [("employee", "date")]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.employee} {self.date:%d/%m/%Y}"
