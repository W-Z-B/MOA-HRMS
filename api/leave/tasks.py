"""Scheduled leave jobs (Procrastinate, PostgreSQL-backed). Discovered automatically from tasks.py."""

import logging
from datetime import date

from procrastinate.contrib.django import app

from leave.models import LeaveType
from leave.services import accrue_month
from people.models import Employee

log = logging.getLogger(__name__)


@app.periodic(cron="0 2 1 * *")  # 02:00 on the first day of every month
@app.task(name="leave.accrue_leave", queue="leave")
def accrue_leave(timestamp: int | None = None) -> int:
    """Apply one month's accrual to every active employee for each accruing leave type."""
    today = date.today()
    entry_date = today.replace(day=1)
    created = 0
    types = list(LeaveType.objects.filter(accrues_monthly=True, annual_entitlement_days__gt=0))
    for employee in Employee.objects.filter(status=Employee.Status.ACTIVE).iterator():
        assignment = employee.current_assignment
        appointment = assignment.appointment_type if assignment else None
        for leave_type in types:
            if leave_type.appointment_types and appointment not in leave_type.appointment_types:
                continue
            if accrue_month(employee, leave_type, entry_date) is not None:
                created += 1
    log.info("leave.accrue_leave created %s ledger rows for %s", created, entry_date)
    return created
