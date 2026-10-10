"""The pay calculation engine (H-M01): one employee's gross, statutory deductions and net for a run.

Reproduces the GRA's own worked examples to the dollar (ADR 0004, item 4.07) — see payroll/tests.py.
"""

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from attendance.models import AttendanceRecord
from leave.services import working_days
from payroll.models import StatutoryRate
from people.models import Employee
from people.services import current_contract, hourly_rate

CENTS = Decimal("0.01")
ONE_THIRD = Decimal(1) / Decimal(3)


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def rate(kind: str, on: date) -> Decimal | None:
    """The value of a statutory parameter in force on a date, or None if Finance has not entered one."""
    row = StatutoryRate.objects.filter(kind=kind, effective_from__lte=on).order_by("-effective_from").first()
    return row.value if row else None


class RatesMissing(Exception):
    """Raised when a required statutory rate has no row in force on the pay date."""


def _required(kind: str, on: date) -> Decimal:
    value = rate(kind, on)
    if value is None:
        raise RatesMissing(f"No {StatutoryRate.Kind(kind).label.lower()} is in force on {on:%d/%m/%Y}.")
    return value


def period_bounds(period: str) -> tuple[date, date]:
    """The first and last calendar day of a "YYYY-MM" period."""
    year, month = (int(part) for part in period.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def nis_employee(gross: Decimal, on: date) -> Decimal:
    pct = _required(StatutoryRate.Kind.NIS_EMPLOYEE_PCT, on)
    ceiling = rate(StatutoryRate.Kind.NIS_CEILING_MONTHLY, on)
    insurable = min(gross, ceiling) if ceiling is not None else gross
    return _money(insurable * pct / 100)


def nis_employer(gross: Decimal, on: date) -> Decimal:
    pct = _required(StatutoryRate.Kind.NIS_EMPLOYER_PCT, on)
    ceiling = rate(StatutoryRate.Kind.NIS_CEILING_MONTHLY, on)
    insurable = min(gross, ceiling) if ceiling is not None else gross
    return _money(insurable * pct / 100)


def paye(gross: Decimal, nis_employee_contribution: Decimal, on: date) -> dict:
    """PAYE on a month's gross: the allowance (the greater of the flat amount or a third of gross), the
    employee's own NIS contribution, then the two bands. Other reliefs the 2026 notice allows (insurance
    premiums, a per-child amount, the first part of overtime or a second job) are not modelled: see the
    assumptions in this pull request's description.
    """
    allowance_flat = _required(StatutoryRate.Kind.PAYE_ALLOWANCE_MONTHLY, on)
    allowance = max(allowance_flat, gross * ONE_THIRD)
    chargeable = max(gross - allowance - nis_employee_contribution, Decimal(0))
    rate1 = _required(StatutoryRate.Kind.PAYE_RATE_PCT, on)
    band2_threshold = rate(StatutoryRate.Kind.PAYE_BAND2_THRESHOLD_MONTHLY, on)
    rate2 = rate(StatutoryRate.Kind.PAYE_RATE_BAND2_PCT, on)
    if band2_threshold is None or rate2 is None:
        band1_amount, band2_amount, tax2 = chargeable, Decimal(0), Decimal(0)
    else:
        band1_amount = min(chargeable, band2_threshold)
        band2_amount = max(chargeable - band2_threshold, Decimal(0))
        tax2 = band2_amount * rate2 / 100
    tax1 = band1_amount * rate1 / 100
    return {
        "allowance": _money(allowance),
        "chargeable": _money(chargeable),
        "tax": _money(tax1 + tax2),
    }


def unpaid_days_in(employee: Employee, start: date, end: date) -> Decimal:
    """Days in the period that are absent, or on leave the employee is not paid for (H-M02's attendance
    data, cross-referenced against the leave type). No attendance record for a day is not counted: the
    engine does not invent an absence the attendance module was never asked about."""
    records = AttendanceRecord.objects.filter(employee=employee, date__range=(start, end)).select_related(
        "leave_request__leave_type"
    )
    days = 0
    for record in records:
        if record.status == AttendanceRecord.Status.ABSENT:
            days += 1
        elif (
            record.status == AttendanceRecord.Status.ON_LEAVE
            and record.leave_request is not None
            and not record.leave_request.leave_type.is_paid
        ):
            days += 1
    return Decimal(days)


def hours_worked_in(employee: Employee, start: date, end: date) -> Decimal:
    total = AttendanceRecord.objects.filter(employee=employee, date__range=(start, end)).aggregate(
        total=Sum("hours")
    )["total"]
    return total or Decimal(0)


def compute_payslip(employee: Employee, period: str) -> dict | None:
    """One employee's figures for a period, or None if they have no contract to pay (left, or not yet
    assigned). Salaried staff are paid their grade's amount, less unpaid days worked out from attendance;
    staff with their own hourly rate on the contract are paid for the hours attendance recorded."""
    start, end = period_bounds(period)
    contract = current_contract(employee)
    if contract is None:
        return None
    on = end
    basis: dict = {}
    if contract.hourly_rate is not None:
        hours = hours_worked_in(employee, start, end)
        rate_per_hour = hourly_rate(contract) or Decimal(0)
        gross = _money(hours * rate_per_hour)
        basis = {"pay_basis": "hourly", "hours": str(hours), "hourly_rate": str(rate_per_hour)}
        unpaid_days = Decimal(0)
        unpaid_deduction = Decimal(0)
    else:
        assignment = employee.current_assignment
        if assignment is None:
            return None
        monthly = assignment.pay_grade.amount_on(on)
        period_working_days = Decimal(working_days(start, end)) or Decimal(1)
        daily_rate = monthly / period_working_days
        unpaid_days = unpaid_days_in(employee, start, end)
        unpaid_deduction = _money(daily_rate * unpaid_days)
        gross = _money(monthly - unpaid_deduction)
        basis = {
            "pay_basis": "salaried",
            "monthly_amount": str(monthly),
            "working_days": str(period_working_days),
            "daily_rate": str(_money(daily_rate)),
        }
    nis_emp = nis_employee(gross, on)
    nis_emp_er = nis_employer(gross, on)
    tax = paye(gross, nis_emp, on)
    net = _money(gross - nis_emp - tax["tax"])
    return {
        "gross": gross,
        "unpaid_days": unpaid_days,
        "unpaid_deduction": unpaid_deduction,
        "nis_employee": nis_emp,
        "nis_employer": nis_emp_er,
        "paye": tax["tax"],
        "net": net,
        "breakdown": {**basis, "allowance": str(tax["allowance"]), "chargeable": str(tax["chargeable"])},
    }


def payable_employees():
    """Active staff with a current assignment: who a pay run is calculated for."""
    return Employee.objects.filter(status=Employee.Status.ACTIVE).exclude(assignments__isnull=True).distinct()
