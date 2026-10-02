"""Leave calculations: working days, entitlements, balances (ledger sums), grants and debits."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from core.models import PublicHoliday
from leave.models import Entitlement, LeaveLedger, LeaveRequest, LeaveType

WEEKEND = {5, 6}  # Saturday, Sunday
ZERO = Decimal("0")
CENT = Decimal("0.01")
# Submitted and not yet decided: the days are spoken for although the ledger does not show them.
PENDING_STATES = (LeaveRequest.State.SUBMITTED, LeaveRequest.State.SUPERVISOR_APPROVED)


def working_days(start: date, end: date) -> int:
    """Calendar days between start and end inclusive, excluding weekends and public holidays."""
    holidays = set(PublicHoliday.objects.filter(date__range=(start, end)).values_list("date", flat=True))
    count, cursor = 0, start
    while cursor <= end:
        if cursor.weekday() not in WEEKEND and cursor not in holidays:
            count += 1
        cursor += timedelta(days=1)
    return count


def next_working_day(after: date) -> date:
    """The day the employee is due back: the first working day after the leave ends."""
    cursor = after + timedelta(days=1)
    while working_days(cursor, cursor) == 0:
        cursor += timedelta(days=1)
    return cursor


def balance(employee, leave_type: LeaveType, as_of: date | None = None) -> Decimal:
    qs = LeaveLedger.objects.filter(employee=employee, leave_type=leave_type)
    if as_of is not None:
        qs = qs.filter(entry_date__lte=as_of)
    return qs.aggregate(total=Sum("days"))["total"] or ZERO


def is_eligible(employee, leave_type: LeaveType) -> bool:
    """Leave types may be limited to some appointment types; an empty list admits everyone."""
    if not leave_type.appointment_types:
        return True
    assignment = employee.current_assignment
    return assignment is not None and assignment.appointment_type in leave_type.appointment_types


def entitlement_days(employee, leave_type: LeaveType) -> Decimal:
    """Days a year: what the employee's contract says, otherwise the leave type's standard."""
    from people.services import current_contract

    contract = current_contract(employee)
    if contract is not None:
        own = Entitlement.objects.filter(contract=contract, leave_type=leave_type).first()
        if own is not None:
            return own.annual_days
    return leave_type.annual_entitlement_days


def entitlements_for(employee) -> list[dict]:
    rows = []
    for leave_type in LeaveType.objects.all():
        days = entitlement_days(employee, leave_type)
        if days > 0 and is_eligible(employee, leave_type):
            rows.append(
                {
                    "leave_type": leave_type.id,
                    "code": leave_type.code,
                    "name": leave_type.name,
                    "annual_days": days,
                    "from_contract": days != leave_type.annual_entitlement_days,
                }
            )
    return rows


def pending_days(employee, leave_type: LeaveType, *, exclude: LeaveRequest | None = None) -> Decimal:
    qs = LeaveRequest.objects.filter(employee=employee, leave_type=leave_type, state__in=PENDING_STATES)
    if exclude is not None and exclude.pk:
        qs = qs.exclude(pk=exclude.pk)
    return qs.aggregate(total=Sum("days"))["total"] or ZERO


def accruals_due(employee, leave_type: LeaveType, *, today: date, on: date) -> Decimal:
    """Monthly accruals still to be credited after today and by `on`, at most a year ahead."""
    if not leave_type.accrues_monthly or on <= today:
        return ZERO
    months = min((on.year - today.year) * 12 + on.month - today.month, 12)
    monthly = (entitlement_days(employee, leave_type) / Decimal(12)).quantize(CENT)
    return monthly * months


def available_on(
    employee,
    leave_type: LeaveType,
    on: date,
    *,
    exclude: LeaveRequest | None = None,
    today: date | None = None,
) -> Decimal:
    """Days the employee can still request for leave starting on `on`.

    The ledger, plus what will have accrued by then, less requests awaiting a decision.
    """
    total = balance(employee, leave_type) + accruals_due(
        employee, leave_type, today=today or date.today(), on=on
    )
    if leave_type.max_balance_days is not None:
        total = min(total, leave_type.max_balance_days)
    return total - pending_days(employee, leave_type, exclude=exclude)


def balances_for(employee) -> list[dict]:
    """One row per leave type the employee has an entitlement to or a history of."""
    sums = dict(
        LeaveLedger.objects.filter(employee=employee).values_list("leave_type_id").annotate(total=Sum("days"))
    )
    pending = dict(
        LeaveRequest.objects.filter(employee=employee, state__in=PENDING_STATES)
        .values_list("leave_type_id")
        .annotate(total=Sum("days"))
    )
    rows = []
    for leave_type in LeaveType.objects.all():
        entitlement = entitlement_days(employee, leave_type) if is_eligible(employee, leave_type) else ZERO
        if leave_type.id not in sums and entitlement == 0:
            continue
        held = sums.get(leave_type.id, ZERO)
        waiting = pending.get(leave_type.id, ZERO)
        rows.append(
            {
                "leave_type": leave_type.id,
                "code": leave_type.code,
                "name": leave_type.name,
                "balance": held,
                "entitlement": entitlement,
                "pending": waiting,
                "available": held - waiting,
                "limited": leave_type.over_balance != LeaveType.OverBalance.ALLOW,
            }
        )
    return rows


def debit_for_request(request_obj, *, actor=None) -> LeaveLedger:
    """Called on final approval. Records the taken days as a negative ledger row.

    Where the leave type accepts more than the balance with evidence, the ledger is debited only
    down to zero and the rest is kept on the request as days beyond the entitlement.
    """
    days = abs(request_obj.days)
    covered = days
    if request_obj.leave_type.over_balance == LeaveType.OverBalance.EVIDENCE:
        covered = min(days, max(balance(request_obj.employee, request_obj.leave_type), ZERO))
    beyond = days - covered
    if beyond != request_obj.days_beyond:
        request_obj.days_beyond = beyond
        request_obj.save(update_fields=["days_beyond"])
    return LeaveLedger.objects.create(
        employee=request_obj.employee,
        leave_type=request_obj.leave_type,
        entry_date=request_obj.from_date,
        days=-covered,
        reason=LeaveLedger.Reason.TAKEN,
        request=request_obj,
        note=f"{beyond} days beyond the entitlement, with evidence" if beyond else "",
        created_by=actor,
        updated_by=actor,
    )


def accrue_month(employee, leave_type: LeaveType, entry_date: date, *, actor=None) -> LeaveLedger | None:
    """One month's accrual (entitlement / 12), idempotent per employee, type and month."""
    entitlement = entitlement_days(employee, leave_type)
    if not leave_type.accrues_monthly or entitlement == 0:
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
    days = (entitlement / Decimal(12)).quantize(CENT)
    return LeaveLedger.objects.create(
        employee=employee,
        leave_type=leave_type,
        entry_date=entry_date,
        days=days,
        reason=LeaveLedger.Reason.ACCRUAL,
        created_by=actor,
        updated_by=actor,
    )


def grant_year(employee, leave_type: LeaveType, year: int, *, actor=None) -> list[LeaveLedger]:
    """The year's entitlement for leave that is granted whole, such as sick leave.

    Idempotent per employee, type and year: an accrual or an opening balance dated in the year
    counts as the grant. What is left of last year beyond the carry-over limit is forfeited first.
    Staff whose appointment began during the year receive the months that remain, start month included.
    """
    entitlement = entitlement_days(employee, leave_type)
    if leave_type.accrues_monthly or entitlement == 0 or not is_eligible(employee, leave_type):
        return []
    granted = (LeaveLedger.Reason.ACCRUAL, LeaveLedger.Reason.OPENING)
    if LeaveLedger.objects.filter(
        employee=employee, leave_type=leave_type, reason__in=granted, entry_date__year=year
    ).exists():
        return []
    first_day = date(year, 1, 1)
    row = {"employee": employee, "leave_type": leave_type, "created_by": actor, "updated_by": actor}
    rows = []
    left = balance(employee, leave_type, as_of=date(year - 1, 12, 31))
    if left > leave_type.carry_over_max_days:
        rows.append(
            LeaveLedger.objects.create(
                entry_date=first_day,
                days=leave_type.carry_over_max_days - left,
                reason=LeaveLedger.Reason.FORFEIT,
                note=f"Unused at the end of {year - 1}",
                **row,
            )
        )
    assignment = employee.current_assignment
    months = 12
    if assignment is not None and assignment.start_date.year == year:
        months = 13 - assignment.start_date.month
    rows.append(
        LeaveLedger.objects.create(
            entry_date=first_day if months == 12 else assignment.start_date,
            days=(entitlement * months / Decimal(12)).quantize(CENT),
            reason=LeaveLedger.Reason.ACCRUAL,
            note=f"Entitlement for {year}" + ("" if months == 12 else f", {months} months"),
            **row,
        )
    )
    return rows
