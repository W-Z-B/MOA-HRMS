"""F13 Payroll interface and F14 Statutory (Release 2). The HRMS produces data; it does not calculate pay."""

from django.db import models

from core.models import TimeStampedModel


class PayrollPeriod(TimeStampedModel):
    class State(models.TextChoices):
        OPEN = "open", "Open"
        LOCKED = "locked", "Locked"
        EXPORTED = "exported", "Exported"

    period = models.CharField(max_length=7, unique=True, help_text="YYYY-MM")
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN)
    locked_at = models.DateTimeField(null=True, blank=True)
    exported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period"]

    def __str__(self) -> str:
        return f"{self.period} ({self.state})"


class StatutoryRate(TimeStampedModel):
    """Effective-dated NIS and PAYE parameters. Values are entered by Finance from the official schedules."""

    class Kind(models.TextChoices):
        NIS_EMPLOYEE_PCT = "nis_employee_pct", "NIS employee contribution %"
        NIS_EMPLOYER_PCT = "nis_employer_pct", "NIS employer contribution %"
        NIS_CEILING_MONTHLY = "nis_ceiling_monthly", "NIS insurable earnings ceiling (monthly, GYD)"
        PAYE_THRESHOLD_MONTHLY = "paye_threshold_monthly", "PAYE tax-free threshold (monthly, GYD)"
        PAYE_RATE_PCT = "paye_rate_pct", "PAYE rate %"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    value = models.DecimalField(max_digits=14, decimal_places=4)
    effective_from = models.DateField()
    source_reference = models.CharField(max_length=200, blank=True, help_text="Circular or notice reference")

    class Meta:
        unique_together = [("kind", "effective_from")]
        ordering = ["kind", "-effective_from"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} = {self.value} from {self.effective_from:%d/%m/%Y}"
