"""The attendance exception engine (H-M02): what a day was scheduled to be, and what it turned out to be.

``evaluate`` is the one place that decides a day's status, so the self-service check-in/out, the HR
correction screen and the nightly sweep (``attendance.tasks``) all agree with each other.
"""

from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceRecord, EmployeeShift, ShiftPattern
from core.models import PublicHoliday


class AttendanceError(Exception):
    code = "attendance_error"

    def __init__(self, detail: str, code: str | None = None):
        super().__init__(detail)
        if code:
            self.code = code


@dataclass(frozen=True)
class Schedule:
    shift: ShiftPattern | None
    starts: time | None
    ends: time | None
    is_working_day: bool


def schedule_for(employee, on: date_cls) -> Schedule:
    """What the employee is expected to work on a day: their shift, or the School's default hours."""
    shift = (
        EmployeeShift.objects.filter(employee=employee, effective_from__lte=on)
        .order_by("-effective_from")
        .select_related("shift")
        .first()
    )
    if shift is not None:
        pattern = shift.shift
        return Schedule(pattern, pattern.starts, pattern.ends, on.isoweekday() in pattern.working_days)
    starts = time.fromisoformat(settings.ATTENDANCE_DEFAULT_START)
    ends = time.fromisoformat(settings.ATTENDANCE_DEFAULT_END)
    return Schedule(None, starts, ends, on.isoweekday() in settings.ATTENDANCE_DEFAULT_WORKING_DAYS)


def approved_leave_on(employee, on: date_cls):
    """The approved leave request covering this day, if any (so it is never counted as absent)."""
    from leave.models import LeaveRequest

    return (
        LeaveRequest.objects.filter(
            employee=employee, state=LeaveRequest.State.APPROVED, from_date__lte=on, to_date__gte=on
        )
        .order_by("-id")
        .first()
    )


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _hours_between(start: time, end: time) -> float:
    minutes = _minutes(end) - _minutes(start)
    if minutes < 0:  # an overnight shift; not expected at GSA today, kept rather than raising
        minutes += 24 * 60
    return round(minutes / 60, 2)


def evaluate(record: AttendanceRecord) -> AttendanceRecord:
    """Work out `status`, `hours` and the schedule columns from what is on the record so far.

    Approved leave and public holidays always win, whatever was checked in. Otherwise: no check-in on a
    working day is absent; a check-in after the grace period is late; a check-in with no check-out is a
    missing checkout until one is added. A record an HR correction has set stays as HR left it.
    """
    if record.status == AttendanceRecord.Status.CORRECTED:
        return record
    leave = approved_leave_on(record.employee, record.date)
    if leave is not None:
        record.leave_request = leave
        record.status = AttendanceRecord.Status.ON_LEAVE
        record.hours = 0
        return record
    record.leave_request = None
    if PublicHoliday.objects.filter(date=record.date).exists():
        record.status = AttendanceRecord.Status.HOLIDAY
        record.hours = 0
        return record
    schedule = schedule_for(record.employee, record.date)
    record.shift = schedule.shift
    record.scheduled_in = schedule.starts
    record.scheduled_out = schedule.ends
    if not schedule.is_working_day:
        record.status = AttendanceRecord.Status.NOT_SCHEDULED
        record.hours = 0
        return record
    if record.time_in is None:
        record.status = AttendanceRecord.Status.ABSENT
        record.hours = 0
        return record
    if record.time_out is None:
        record.status = AttendanceRecord.Status.MISSING_CHECKOUT
        record.hours = 0
        return record
    record.hours = _hours_between(record.time_in, record.time_out)
    late = schedule.starts is not None and _minutes(record.time_in) > _minutes(schedule.starts) + (
        settings.ATTENDANCE_GRACE_MINUTES
    )
    record.status = AttendanceRecord.Status.LATE if late else AttendanceRecord.Status.PRESENT
    return record


def _for_update(employee, on: date_cls) -> AttendanceRecord:
    record, _ = AttendanceRecord.objects.get_or_create(employee=employee, date=on)
    return record


@transaction.atomic
def check_in(employee, *, at: datetime | None = None, source=AttendanceRecord.Source.SELF_SERVICE):
    """The employee's own check-in. Refused if today already has one, so a phone cannot double-tap it in."""
    at = at or timezone.localtime()
    record = _for_update(employee, at.date())
    if record.time_in is not None:
        raise AttendanceError("You have already checked in today.", code="already_checked_in")
    record.time_in = at.time()
    record.source = source
    evaluate(record)
    record.save()
    return record


@transaction.atomic
def check_out(employee, *, at: datetime | None = None):
    """The employee's own check-out. Refused without a check-in first: there is always an in before an out."""
    at = at or timezone.localtime()
    record = AttendanceRecord.objects.filter(employee=employee, date=at.date()).first()
    if record is None or record.time_in is None:
        raise AttendanceError("You have not checked in today.", code="not_checked_in")
    if record.time_out is not None:
        raise AttendanceError("You have already checked out today.", code="already_checked_out")
    record.time_out = at.time()
    evaluate(record)
    record.save()
    return record


@transaction.atomic
def correct(record: AttendanceRecord, *, time_in=None, time_out=None, note: str = "", clear: bool = False):
    """HR's correction or override for a missed or wrong day (the D3 fallback for whatever check-in missed).

    `clear` removes a wrong check-in/out instead of replacing it (for example, a device fired by mistake).
    """

    def _next(given, clearing: bool, current):
        if given is not None:
            return given
        return None if clearing else current

    record.time_in = _next(time_in, clear, record.time_in)
    record.time_out = _next(time_out, clear, record.time_out)
    record.source = AttendanceRecord.Source.CORRECTION
    record.note = note[:300]
    record.resolved = True
    evaluate(record)
    # A correction is HR's final word for the day: evaluate() would otherwise mark a still-missing
    # check-out as an open exception again on the next sweep.
    if record.status in AttendanceRecord.OPEN_STATUSES:
        record.status = AttendanceRecord.Status.CORRECTED
    record.save()
    return record


def sweep(on: date_cls) -> dict:
    """The nightly job's work for one past day (attendance.tasks): create what is missing, flag what is
    still open, leave anything HR has already resolved alone. Returns counts for the log."""
    from people.models import Employee

    created = flagged = 0
    active = Employee.objects.filter(status=Employee.Status.ACTIVE)
    for employee in active:
        record, was_created = AttendanceRecord.objects.get_or_create(employee=employee, date=on)
        if was_created:
            created += 1
        elif record.resolved:
            continue
        before = record.status
        evaluate(record)
        record.save()
        if record.status in AttendanceRecord.OPEN_STATUSES and record.status != before:
            flagged += 1
    return {"created": created, "flagged": flagged}


def open_exceptions_for_campus_scope():
    """Unresolved exceptions, newest first, for the inbox and the HR correction screen."""
    return AttendanceRecord.objects.filter(
        status__in=AttendanceRecord.OPEN_STATUSES, resolved=False
    ).select_related("employee", "employee__campus")


def yesterday() -> date_cls:
    return timezone.localdate() - timedelta(days=1)
