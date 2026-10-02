"""The access review falls due every three months (item 1.27): a reminder to the HR Manager and the
administrators, each Monday at 06:00 until it is signed off, once a quarter at most."""

import logging
from datetime import date

from django.utils import timezone
from procrastinate.contrib.django import app

from iam.models import AccessReview, Role
from notifications.models import Notification
from notifications.services import notify, users_with_role

log = logging.getLogger(__name__)
REVIEW_EVERY_DAYS = 92


def remind_access_review(today: date) -> int:
    last = AccessReview.objects.select_related("reviewed_by").first()
    if last is not None and (today - timezone.localdate(last.reviewed_at)).days < REVIEW_EVERY_DAYS:
        return 0
    when = (
        f"was last signed off on {timezone.localdate(last.reviewed_at):%d/%m/%Y}"
        if last
        else "has not been signed off yet"
    )
    recipients = set(users_with_role(Role.HR_MANAGER)) | set(users_with_role(Role.ADMINISTRATOR))
    quarter = (today.month - 1) // 3 + 1
    return len(
        notify(
            recipients,
            title="Access review due",
            body=(
                f"The list of who can see what {when}. Read it, take away access that is no longer needed, "
                "and sign it off."
            ),
            link="/admin/review",
            kind=Notification.Kind.ALERT,
            dedupe_key=f"access-review:{today.year}-Q{quarter}",
        )
    )


@app.periodic(cron="0 6 * * 1")
@app.task(name="iam.access_review_reminder", queue="iam")
def access_review_reminder(timestamp: int | None = None) -> int:
    sent = remind_access_review(timezone.localdate())
    log.info("iam.access_review_reminder sent %s notifications", sent)
    return sent
