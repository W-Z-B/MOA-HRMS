"""H-M03 scheduled alerts: appraisals not yet signed off, as their cycle's end date approaches or passes.
Daily at 06:20 and 06:25, after people's own alerts (people/tasks.py)."""

import logging
from datetime import date, timedelta

from procrastinate.contrib.django import app

from iam.models import Role
from notifications.services import notify, users_with_role
from performance.models import Appraisal, AppraisalCycle

log = logging.getLogger(__name__)
CYCLE_HORIZONS = (30, 14, 7)
OPEN_STATES = (Appraisal.State.DRAFT, Appraisal.State.SELF_ASSESSED, Appraisal.State.RATED)


def _recipients(appraisal: Appraisal) -> list:
    people = []
    if appraisal.employee.user_id:
        people.append(appraisal.employee.user)
    if appraisal.manager is not None and appraisal.manager.user_id:
        people.append(appraisal.manager.user)
    return people


def alert_cycle_ending(today: date) -> int:
    """Notify the employee and their manager for cycles ending in 30, 14 or 7 days. Idempotent per horizon."""
    sent = 0
    for days in CYCLE_HORIZONS:
        cycles = AppraisalCycle.objects.filter(ends=today + timedelta(days=days), is_open=True)
        qs = Appraisal.objects.filter(cycle__in=cycles, state__in=OPEN_STATES).select_related(
            "employee", "employee__campus", "manager", "cycle"
        )
        for appraisal in qs:
            sent += len(
                notify(
                    _recipients(appraisal),
                    title=f"{appraisal.cycle.name} {appraisal.cycle.year} ends in {days} days",
                    body=(
                        f"{appraisal.employee.full_name}'s appraisal is still "
                        f"{appraisal.get_state_display().lower()}."
                    ),
                    link="/appraisals",
                    kind="alert",
                    dedupe_key=f"appraisal:{appraisal.id}:{days}",
                )
            )
    return sent


def alert_overdue(today: date) -> int:
    """Notify HR, once a day, of appraisals still open after their cycle has ended."""
    sent = 0
    overdue = Appraisal.objects.filter(cycle__ends__lt=today, state__in=OPEN_STATES).select_related(
        "employee", "employee__campus", "manager", "cycle"
    )
    for appraisal in overdue:
        sent += len(
            notify(
                users_with_role(Role.HR_OFFICER, campus=appraisal.employee.campus),
                title=f"Appraisal overdue: {appraisal.employee.full_name}",
                body=(
                    f"{appraisal.cycle.name} {appraisal.cycle.year} ended {appraisal.cycle.ends:%d/%m/%Y}; "
                    f"still {appraisal.get_state_display().lower()}."
                ),
                link="/appraisals",
                kind="alert",
                dedupe_key=f"appraisal:{appraisal.id}:overdue:{today.isoformat()}",
            )
        )
    return sent


@app.periodic(cron="20 6 * * *")
@app.task(name="performance.cycle_ending_alerts", queue="performance")
def cycle_ending_alerts(timestamp: int | None = None) -> int:
    sent = alert_cycle_ending(date.today())
    log.info("performance.cycle_ending_alerts sent %s notifications", sent)
    return sent


@app.periodic(cron="25 6 * * *")
@app.task(name="performance.overdue_alerts", queue="performance")
def overdue_alerts(timestamp: int | None = None) -> int:
    sent = alert_overdue(date.today())
    log.info("performance.overdue_alerts sent %s notifications", sent)
    return sent
