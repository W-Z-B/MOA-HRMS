"""H-M01 (Phase A): the payroll engine. Decision D1 (pay engine vs. interface to an external system) is
still open (ADR 0004, proposed); this build takes the engine option (ADR 0004's option B) for the parts
that can be built without GSA's sign-off on the conditions ADR 0004 sets for going live (three matched
pay periods, Finance's lock-step review). Statutory rates stay data, dated and versioned, as ADR 0004
requires, so a budget change is a new row, never a code change.
"""

from django.db import models

from core.models import TimeStampedModel


class StatutoryRate(TimeStampedModel):
    """Effective-dated NIS and PAYE parameters. Values are entered by Finance from the official schedules.

    PAYE's personal allowance is the greater of a flat monthly amount and one third of gross pay; the
    "one third" test itself is the tax law's mechanism, not a figure the annual budget adjusts, so it is
    computed in payroll.services rather than stored here. Everything the budget does change — the flat
    allowance, the two bands' rates and where the second one starts, NIS's rate and its ceiling — is a
    dated row here.
    """

    class Kind(models.TextChoices):
        NIS_EMPLOYEE_PCT = "nis_employee_pct", "NIS employee contribution %"
        NIS_EMPLOYER_PCT = "nis_employer_pct", "NIS employer contribution %"
        NIS_CEILING_MONTHLY = "nis_ceiling_monthly", "NIS insurable earnings ceiling (monthly, GYD)"
        PAYE_ALLOWANCE_MONTHLY = "paye_allowance_monthly", "PAYE personal allowance, flat (monthly, GYD)"
        PAYE_RATE_PCT = "paye_rate_pct", "PAYE rate, first band %"
        PAYE_BAND2_THRESHOLD_MONTHLY = (
            "paye_band2_threshold_monthly",
            "PAYE chargeable income where the second band starts (monthly, GYD)",
        )
        PAYE_RATE_BAND2_PCT = "paye_rate_band2_pct", "PAYE rate, second band %"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    value = models.DecimalField(max_digits=14, decimal_places=4)
    effective_from = models.DateField()
    source_reference = models.CharField(max_length=200, blank=True, help_text="Circular or notice reference")

    class Meta:
        unique_together = [("kind", "effective_from")]
        ordering = ["kind", "-effective_from"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} = {self.value} from {self.effective_from:%d/%m/%Y}"


class PayRun(TimeStampedModel):
    """One pay period's run, calculated then approved by someone other than who calculated it (ADR 0004),
    then disbursed, which is when payslips are issued. Corrections after disbursement are a new run."""

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        CALCULATED = "calculated", "Calculated"
        APPROVED = "approved", "Approved"
        DISBURSED = "disbursed", "Disbursed"

    period = models.CharField(max_length=7, unique=True, help_text="YYYY-MM")
    state = models.CharField(max_length=10, choices=State.choices, default=State.DRAFT)
    calculated_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    # Totals kept on the run so a list of runs reads without summing every payslip each time.
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_nis_employee = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_nis_employer = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_paye = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["-period"]

    def __str__(self) -> str:
        return f"{self.period} ({self.state})"


class Payslip(TimeStampedModel):
    """One employee's figures for one run: what the calculation found, kept even if a later rate change
    would work it out differently, so a disbursed payslip never silently changes."""

    pay_run = models.ForeignKey(PayRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="payslips")
    gross = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unpaid_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    unpaid_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    nis_employee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    nis_employer = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paye = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # What the calculation used, for review and for the payslip PDF: rate values, the allowance chosen,
    # the pay basis (salaried or hourly) and, if hourly, the hours it was worked out on.
    breakdown = models.JSONField(default=dict, blank=True)
    document = models.ForeignKey(
        "people.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        unique_together = [("pay_run", "employee")]
        ordering = ["employee"]

    def __str__(self) -> str:
        return f"{self.employee} payslip for {self.pay_run.period}"
