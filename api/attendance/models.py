"""H-M02 (Phase A): the attendance engine.

Decision D3 (how attendance is captured: phone, kiosk or crew register) is still open; this build assumes
self-service web/phone check-in and check-out, consistent with the project's PWA-first direction, with an
HR correction for a missed or wrong day (see ``services.py``). The record does not assume who or what made
it: ``Source`` already has room for a future kiosk or biometric device, or a batch import for a crew
register, to create the same kind of row, so that decision can be revisited without a schema change.

One row per employee per working day is the single source of truth: it carries what was scheduled, what
actually happened, and the status the exception engine (``services.evaluate``) worked out from it, cross
referenced against approved leave so an approved leave day is never flagged as absent.
"""

from django.db import models

from core.models import TimeStampedModel


class ShiftPattern(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    starts = models.TimeField()
    ends = models.TimeField()
    working_days = models.JSONField(default=list, help_text="ISO weekday numbers, 1 = Monday")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class EmployeeShift(TimeStampedModel):
    """Which shift pattern applies to an employee, from a date (effective-dated, like org.Grade).

    No row for an employee means the School's default hours (settings.ATTENDANCE_DEFAULT_START/END,
    Monday to Friday) apply, so a shift need only be recorded where it differs from the default.
    """

    employee = models.ForeignKey("people.Employee", on_delete=models.CASCADE, related_name="shift_history")
    shift = models.ForeignKey(ShiftPattern, on_delete=models.PROTECT, related_name="employees")
    effective_from = models.DateField()

    class Meta:
        ordering = ["employee", "-effective_from"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "effective_from"], name="one_shift_change_per_day")
        ]

    def __str__(self) -> str:
        return f"{self.employee} on {self.shift.name} from {self.effective_from:%d/%m/%Y}"


class AttendanceRecord(TimeStampedModel):
    """One employee, one day: scheduled against actual, and the status the exception engine found."""

    class Source(models.TextChoices):
        SELF_SERVICE = "self", "Self-service check-in"
        CORRECTION = "manual", "HR correction"
        IMPORT = "import", "Spreadsheet or crew register import"
        DEVICE = "device", "Kiosk or biometric device"
        SYSTEM = "system", "Marked automatically (no check-in recorded)"

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        ABSENT = "absent", "Absent"
        ON_LEAVE = "on_leave", "On approved leave"
        HOLIDAY = "holiday", "Public holiday"
        NOT_SCHEDULED = "not_scheduled", "Not a working day"
        MISSING_CHECKOUT = "missing_checkout", "Checked in, not checked out"
        CORRECTED = "corrected", "Corrected by Human Resources"

    OPEN_STATUSES = (Status.LATE, Status.ABSENT, Status.MISSING_CHECKOUT)

    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="attendance")
    date = models.DateField()
    shift = models.ForeignKey(ShiftPattern, null=True, blank=True, on_delete=models.SET_NULL)
    scheduled_in = models.TimeField(null=True, blank=True)
    scheduled_out = models.TimeField(null=True, blank=True)
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SELF_SERVICE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    leave_request = models.ForeignKey(
        "leave.LeaveRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_days",
        help_text="The approved leave request covering this day, if any",
    )
    note = models.CharField(max_length=300, blank=True, help_text="Why it reads as it does, or HR's note")
    resolved = models.BooleanField(default=False, help_text="HR has looked at this exception")

    class Meta:
        unique_together = [("employee", "date")]
        ordering = ["-date"]
        indexes = [models.Index(fields=["date", "status"])]

    def __str__(self) -> str:
        return f"{self.employee} {self.date:%d/%m/%Y} ({self.get_status_display()})"
