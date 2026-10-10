"""H-M02 nightly job: sweep yesterday's attendance for exceptions and tell HR what needs a look.

Mirrors the pattern in people.tasks: a plain function the task wraps, so it is tested without Procrastinate.
"""

import logging

from procrastinate.contrib.django import app

from attendance import services
from iam.models import Role
from notifications.services import notify, users_with_role

log = logging.getLogger(__name__)


def notify_exceptions(on) -> int:
    """One notification per campus to its HR officers and supervisors, naming what is unresolved for `on`."""
    from org.models import Campus

    sent = 0
    for campus in Campus.objects.all():
        open_ = services.open_exceptions_for_campus_scope().filter(employee__campus=campus, date=on)
        if not open_.exists():
            continue
        names = ", ".join(r.employee.full_name for r in open_[:5])
        more = open_.count() - 5
        recipients = list(users_with_role(Role.HR_OFFICER, campus=campus)) + list(
            users_with_role(Role.SUPERVISOR, campus=campus)
        )
        sent += len(
            notify(
                recipients,
                title=f"Attendance to look into for {on:%d/%m/%Y}",
                body=(
                    f"{open_.count()} record(s) need attention: {names}"
                    + (f" and {more} more." if more > 0 else ".")
                ),
                link="/attendance?tab=exceptions",
                kind="alert",
                dedupe_key=f"attendance:{campus.id}:{on.isoformat()}",
            )
        )
    return sent


@app.periodic(cron="30 5 * * *")  # 05:30, before the office day so corrections can be made before HR arrives
@app.task(name="attendance.nightly_sweep", queue="attendance")
def nightly_sweep(timestamp: int | None = None) -> dict:
    on = services.yesterday()
    counts = services.sweep(on)
    counts["notified"] = notify_exceptions(on)
    log.info("attendance.nightly_sweep for %s: %s", on, counts)
    return counts
