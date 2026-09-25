"""F06 Leave management. Balances are never stored: they are the sum of ledger rows."""

from django.db import models

from core.models import TimeStampedModel


class LeaveType(TimeStampedModel):
    """Rules as data. HR edits these; no release is needed to change an entitlement."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    annual_entitlement_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    accrues_monthly = models.BooleanField(default=True, help_text="Accrue 1/12 of the entitlement each month")
    carry_over_max_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    max_balance_days = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_paid = models.BooleanField(default=True)
    requires_evidence = models.BooleanField(default=False)
    appointment_types = models.JSONField(default=list, blank=True, help_text="Empty list means all types")
    term_time_restricted = models.BooleanField(
        default=False, help_text="Academic staff cannot take during term"
    )

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class LeaveLedger(TimeStampedModel):
    class Reason(models.TextChoices):
        ACCRUAL = "accrual", "Accrual"
        TAKEN = "taken", "Taken"
        ADJUSTMENT = "adjustment", "Adjustment"
        CARRY_OVER = "carry_over", "Carry over"
        FORFEIT = "forfeit", "Forfeit"
        OPENING = "opening", "Opening balance (migration)"

    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="leave_ledger")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="ledger")
    entry_date = models.DateField()
    days = models.DecimalField(max_digits=6, decimal_places=2, help_text="Positive credit, negative debit")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    request = models.ForeignKey("leave.LeaveRequest", null=True, blank=True, on_delete=models.PROTECT)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["entry_date", "id"]
        indexes = [models.Index(fields=["employee", "leave_type", "entry_date"])]

    def __str__(self) -> str:
        return f"{self.employee} {self.leave_type.code} {self.days:+} on {self.entry_date:%d/%m/%Y}"


class LeaveRequest(TimeStampedModel):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        SUPERVISOR_APPROVED = "supervisor_approved", "Supervisor approved"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    from_date = models.DateField()
    to_date = models.DateField()
    days = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.CharField(max_length=300, blank=True)
    state = models.CharField(max_length=25, choices=State.choices, default=State.DRAFT)
    evidence = models.ForeignKey("people.Document", null=True, blank=True, on_delete=models.SET_NULL)
    decision_comment = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-from_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(to_date__gte=models.F("from_date")), name="leave_to_after_from"
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee} {self.leave_type.code} {self.from_date:%d/%m}-{self.to_date:%d/%m}"
