"""Item 1.16: each morning, Human Resources is reminded of notices under the Act due that day, or late.

Deadlines under the Occupational Safety and Health Act run in calendar days, so this runs every day.
"""

import logging
from datetime import date

from django.utils import timezone
from procrastinate.contrib.django import app

from incidents.duties import duties
from incidents.models import Incident, Notice
from incidents.services import keepers
from notifications.services import notify

log = logging.getLogger(__name__)


def chase(today: date | None = None) -> dict[str, int]:
    today = today or timezone.localdate()
    reminders = 0
    open_ = (
        Incident.objects.exclude(state=Incident.State.CLOSED)
        .select_related("campus")
        .prefetch_related("people__employee", "notices")
    )
    for incident in open_:
        for due in duties(incident, today):
            if not due.unsent or due.due_on > today:
                continue
            when = "Late" if today > due.due_on else "Due today"
            about = due.person.pk if due.person else 0
            reminders += len(
                notify(
                    keepers(incident.campus),
                    title=f"{when}: notice under the safety and health Act, {incident.reference}",
                    body=(
                        f"Notice of {Notice.Duty(due.duty).label.lower()}, due {due.due_on:%d/%m/%Y}. "
                        "Record it under Incidents once it is sent."
                    ),
                    link=f"/incidents/{incident.pk}",
                    kind="alert",
                    dedupe_key=f"incident:{incident.pk}:{due.duty}:{about}:{today:%Y%m%d}",
                )
            )
    return {"reminders": reminders}


@app.periodic(cron="10 7 * * *")
@app.task(name="incidents.chase_notices", queue="incidents")
def chase_notices(timestamp: int | None = None) -> dict:
    counts = chase()
    log.info("incidents.chase_notices %s", counts)
    return counts
