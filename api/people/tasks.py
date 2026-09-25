"""F03 scheduled alerts: contract expiry (90, 60, 30 days) and probation due (30 days). Daily at 06:00."""

import logging
from datetime import date, timedelta

from procrastinate.contrib.django import app

from iam.models import Role
from notifications.services import notify, users_with_role
from people.models import Assignment

log = logging.getLogger(__name__)
CONTRACT_HORIZONS = (90, 60, 30)
PROBATION_HORIZON = 30


def _recipients(assignment):
    campus = assignment.employee.campus
    return list(users_with_role(Role.HR_OFFICER, campus=campus)) + list(
        users_with_role(Role.SUPERVISOR, campus=campus)
    )


def alert_contract_expiry(today: date) -> int:
    """Notify HR and supervisors for assignments ending in 90, 60 or 30 days. Idempotent per horizon."""
    sent = 0
    for days in CONTRACT_HORIZONS:
        qs = Assignment.objects.filter(
            status=Assignment.Status.ACTIVE, end_date=today + timedelta(days=days)
        ).select_related("employee", "employee__campus", "position")
        for assignment in qs:
            sent += len(
                notify(
                    _recipients(assignment),
                    title=f"Contract ends in {days} days: {assignment.employee.full_name}",
                    body=(
                        f"{assignment.position.title} ({assignment.get_appointment_type_display()}) ends on "
                        f"{assignment.end_date:%d/%m/%Y}. Decide on renewal or separation."
                    ),
                    link=f"/people/{assignment.employee_id}",
                    kind="alert",
                    dedupe_key=f"contract:{assignment.id}:{days}",
                )
            )
    return sent


def alert_probation_due(today: date) -> int:
    """Notify HR and supervisors for probation periods ending in 30 days so the review is scheduled."""
    sent = 0
    qs = Assignment.objects.filter(
        status=Assignment.Status.ACTIVE, probation_end=today + timedelta(days=PROBATION_HORIZON)
    ).select_related("employee", "employee__campus", "position")
    for assignment in qs:
        sent += len(
            notify(
                _recipients(assignment),
                title=f"Probation review due: {assignment.employee.full_name}",
                body=f"Probation ends on {assignment.probation_end:%d/%m/%Y}. Complete the probation review.",
                link=f"/people/{assignment.employee_id}",
                kind="alert",
                dedupe_key=f"probation:{assignment.id}",
            )
        )
    return sent


@app.periodic(cron="0 6 * * *")
@app.task(name="people.contract_expiry_alerts", queue="people")
def contract_expiry_alerts(timestamp: int | None = None) -> int:
    sent = alert_contract_expiry(date.today())
    log.info("people.contract_expiry_alerts sent %s notifications", sent)
    return sent


@app.periodic(cron="0 6 * * *")
@app.task(name="people.probation_due_alerts", queue="people")
def probation_due_alerts(timestamp: int | None = None) -> int:
    sent = alert_probation_due(date.today())
    log.info("people.probation_due_alerts sent %s notifications", sent)
    return sent
