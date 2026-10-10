"""H-W02 scheduled alert: onboarding still open a week after it started. Daily at 06:00, after the alerts
in ``people.tasks``."""

import logging
from datetime import date, timedelta

from procrastinate.contrib.django import app

from iam.models import Role
from notifications.services import notify, users_with_role
from people.models import Onboarding, OnboardingStep

log = logging.getLogger(__name__)
OVERDUE_DAYS = 7


def alert_overdue_onboarding(today: date) -> int:
    """Notify HR of onboarding still open a week (or more) after it started, once a day while it stays so.

    Unlike the contract and probation alerts (``people.tasks``), which each fire once at a fixed horizon,
    an overdue onboarding stays overdue every day until it is finished, so the dedupe key carries today's
    date: a daily reminder, not a single one that is never seen again.
    """
    sent = 0
    stale = Onboarding.objects.filter(
        state__in=(Onboarding.State.IN_PROGRESS, Onboarding.State.DOCUMENTS_SUBMITTED),
        started_on__lte=today - timedelta(days=OVERDUE_DAYS),
    ).select_related("employee", "employee__campus")
    for record in stale:
        open_steps = list(
            record.steps.filter(state=OnboardingStep.State.OPEN).values_list("label", flat=True)
        )
        if not open_steps:
            continue
        labels = ", ".join(open_steps[:3]) + (" and more" if len(open_steps) > 3 else "")
        sent += len(
            notify(
                users_with_role(Role.HR_OFFICER, campus=record.employee.campus),
                title=f"Onboarding overdue: {record.employee.full_name}",
                body=f"Started {record.started_on:%d/%m/%Y}. Still open: {labels}.",
                link="/onboarding",
                kind="alert",
                dedupe_key=f"onboarding:{record.pk}:{today.isoformat()}",
            )
        )
    return sent


@app.periodic(cron="15 6 * * *")  # 06:15, after the contract and probation alerts in people.tasks
@app.task(name="people.onboarding_overdue_alerts", queue="people")
def onboarding_overdue_alerts(timestamp: int | None = None) -> int:
    sent = alert_overdue_onboarding(date.today())
    log.info("people.onboarding_overdue_alerts sent %s notifications", sent)
    return sent
