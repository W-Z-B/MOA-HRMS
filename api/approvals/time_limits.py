"""Time limits on decisions (item 1.33): a reminder when a request has waited too long, then escalation.

Leave is the first workflow with them. A request waiting for its manager is chased after DECISION_DAYS working
days; after ESCALATE_AFTER_DAYS more it goes on to the head of the next unit up (with nobody above, to any
campus supervisor, and HR is told), and the person, the manager passed over and the new one are all told. A
request waiting for HR is chased with the campus HR officers, then put before the HR Manager.
"""

from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from approvals.delegation import delegates_of, users_of
from audit.services import record
from iam.models import Role
from notifications.services import notify, users_with_role


def waited(since: datetime, today: date) -> int:
    """Working days a request has waited, not counting the day it began waiting."""
    from leave.services import working_days

    start = timezone.localtime(since).date()
    return working_days(start + timedelta(days=1), today) if start < today else 0


def _with_manager(request) -> list:
    """Who decides it at the manager's step: the manager and their stand-ins, or the campus supervisors."""
    if request.manager_id is not None:
        return users_of([request.manager, *delegates_of(request.manager)])
    return list(
        users_with_role(Role.SUPERVISOR, campus=request.employee.campus).exclude(employee=request.employee)
    )


def _what(request) -> str:
    return (
        f"{request.leave_type.name}, {request.from_date:%d/%m/%Y} to {request.to_date:%d/%m/%Y}, "
        f"for {request.employee.full_name}"
    )


def _mark(request) -> str:
    return f"{request.id}:{request.waiting_since:%Y%m%d%H%M%S}"


def _remind_manager(request, days: int) -> int:
    return len(
        notify(
            _with_manager(request),
            title=f"Waiting {days} working days for your decision: leave for {request.employee.full_name}",
            body=f"{_what(request)}. If it is not decided soon it goes on up the line.",
            link=f"/leave/requests/{request.id}",
            kind="approval",
            dedupe_key=f"leave:remind:{_mark(request)}",
        )
    )


def _escalate(request, days: int) -> None:
    from people.services import manager_of

    passed_over = request.manager
    if passed_over is None:
        # Already with every campus supervisor: Human Resources can decide at this step too.
        notify(
            users_with_role(Role.HR_OFFICER, campus=request.employee.campus).exclude(
                employee=request.employee
            ),
            title=f"No supervisor has decided in {days} working days: leave for {request.employee.full_name}",
            body=f"{_what(request)}. Human Resources may approve or reject it.",
            link=f"/leave/requests/{request.id}",
            kind="alert",
            dedupe_key=f"leave:nobody:{_mark(request)}",
        )
        return
    above = manager_of(passed_over)
    if above is not None and above.pk == request.employee_id:
        above = None  # never sent to the person who asked
    with transaction.atomic():
        request.manager = above
        request.waiting_since = timezone.now()
        request.save(update_fields=["manager", "waiting_since", "updated_at"])
        record(
            None,
            "escalated",
            request,
            before={"manager": passed_over.pk},
            after={"manager": above.pk if above else None},
            reason=f"Not decided in {days} working days",
        )
    to = above.full_name if above else "the campus supervisors"
    notify(
        _with_manager(request),
        title=f"Leave request sent on to you: {request.employee.full_name}",
        body=f"{_what(request)}. {passed_over.full_name} had not decided in {days} working days.",
        link=f"/leave/requests/{request.id}",
        kind="approval",
        dedupe_key=f"leave:escalated:{_mark(request)}",
    )
    notify(
        users_of([request.employee]),
        title=f"Your leave request was sent on to {to}",
        body=f"{passed_over.full_name} had not decided it in {days} working days.",
        link=f"/leave/requests/{request.id}",
        dedupe_key=f"leave:escalated-owner:{_mark(request)}",
    )
    notify(
        users_of([passed_over]),
        title=f"A leave request was sent on to {to}",
        body=f"{_what(request)}. It had waited {days} working days for your decision.",
        link=f"/leave/requests/{request.id}",
        dedupe_key=f"leave:escalated-passed:{_mark(request)}",
    )


def _remind_hr(request, days: int, *, late: bool) -> int:
    if late:
        recipients = users_with_role(Role.HR_MANAGER)
        title = f"Waiting {days} working days for Human Resources: leave for {request.employee.full_name}"
    else:
        recipients = users_with_role(Role.HR_OFFICER, campus=request.employee.campus)
        title = f"Waiting {days} working days for your approval: leave for {request.employee.full_name}"
    return len(
        notify(
            recipients.exclude(employee=request.employee),
            title=title,
            body=f"{_what(request)}. The manager approved it.",
            link=f"/leave/requests/{request.id}",
            kind="alert" if late else "approval",
            dedupe_key=f"leave:hr:{'late' if late else 'remind'}:{_mark(request)}",
        )
    )


def chase(today: date | None = None) -> dict[str, int]:
    """The daily run: remind, then escalate, every leave request that has waited too long."""
    from leave.models import LeaveRequest

    today = today or timezone.localdate()
    limit, more = settings.DECISION_DAYS, settings.ESCALATE_AFTER_DAYS
    counts = {"reminded": 0, "escalated": 0, "hr_reminded": 0, "hr_escalated": 0}
    waiting = LeaveRequest.objects.filter(
        state__in=(LeaveRequest.State.SUBMITTED, LeaveRequest.State.SUPERVISOR_APPROVED),
        waiting_since__isnull=False,
    ).select_related(
        "employee", "employee__campus", "employee__user", "manager", "manager__user", "leave_type"
    )
    for request in waiting.order_by("waiting_since"):
        days = waited(request.waiting_since, today)
        if days < limit:
            continue
        late = days >= limit + more
        if request.state == LeaveRequest.State.SUBMITTED:
            if late:
                _escalate(request, days)
                counts["escalated"] += 1
            elif _remind_manager(request, days):
                counts["reminded"] += 1
        elif _remind_hr(request, days, late=late):
            counts["hr_escalated" if late else "hr_reminded"] += 1
    return counts
