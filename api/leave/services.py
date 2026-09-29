"""Leave calculations: working days, balances (ledger sums), debits."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from core.models import PublicHoliday
from leave.models import LeaveLedger, LeaveType

WEEKEND = {5, 6}  # Saturday, Sunday


def working_days(start: date, end: date) -> int:
    """Calendar days between start and end inclusive, excluding weekends and public holidays."""
    holidays = set(PublicHoliday.objects.filter(date__range=(start, end)).values_list("date", flat=True))
    count, cursor = 0, start
    while cursor <= end:
        if cursor.weekday() not in WEEKEND and cursor not in holidays:
            count += 1
        cursor += timedelta(days=1)
    return count


def balance(employee, leave_type: LeaveType, as_of: date | None = None) -> Decimal:
    qs = LeaveLedger.objects.filter(employee=employee, leave_type=leave_type)
    if as_of is not None:
        qs = qs.filter(entry_date__lte=as_of)
    return qs.aggregate(total=Sum("days"))["total"] or Decimal("0")


def balances_for(employee) -> list[dict]:
    rows = (
        LeaveLedger.objects.filter(employee=employee)
        .values("leave_type_id", "leave_type__code", "leave_type__name")
        .annotate(days=Sum("days"))
        .order_by("leave_type__code")
    )
    return [
        {
            "leave_type": r["leave_type_id"],
            "code": r["leave_type__code"],
            "name": r["leave_type__name"],
            "balance": r["days"],
        }
        for r in rows
    ]


def debit_for_request(request_obj, *, actor=None) -> LeaveLedger:
    """Called on final approval. Records the taken days as a negative ledger row."""
    return LeaveLedger.objects.create(
        employee=request_obj.employee,
        leave_type=request_obj.leave_type,
        entry_date=request_obj.from_date,
        days=-abs(request_obj.days),
        reason=LeaveLedger.Reason.TAKEN,
        request=request_obj,
        created_by=actor,
        updated_by=actor,
    )


def accrue_month(employee, leave_type: LeaveType, entry_date: date, *, actor=None) -> LeaveLedger | None:
    """One month's accrual (entitlement / 12), idempotent per employee, type and month."""
    if not leave_type.accrues_monthly or leave_type.annual_entitlement_days == 0:
        return None
    exists = LeaveLedger.objects.filter(
        employee=employee,
        leave_type=leave_type,
        reason=LeaveLedger.Reason.ACCRUAL,
        entry_date__year=entry_date.year,
        entry_date__month=entry_date.month,
    ).exists()
    if exists:
        return None
    days = (leave_type.annual_entitlement_days / Decimal(12)).quantize(Decimal("0.01"))
    return LeaveLedger.objects.create(
        employee=employee,
        leave_type=leave_type,
        entry_date=entry_date,
        days=days,
        reason=LeaveLedger.Reason.ACCRUAL,
        created_by=actor,
        updated_by=actor,
    )
