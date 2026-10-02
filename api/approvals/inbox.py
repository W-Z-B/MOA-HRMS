"""Everything waiting for one person's decision, from every module, oldest first (item 1.33).

Each source asks only what that person may decide, by the same rules its own screen uses; the list links to
where it is decided. A request that has waited past its time limit is marked overdue.
"""

from datetime import datetime

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from approvals.delegation import delegator_ids
from approvals.time_limits import waited
from iam.models import Role
from iam.services import has_role, scope_queryset


def _item(kind: str, kind_name: str, title: str, since: datetime, link: str, *, for_whom: str = "") -> dict:
    days = waited(since, timezone.localdate())
    return {
        "kind": kind,
        "kind_name": kind_name,
        "title": title,
        "since": since,
        "waited_days": days,
        "overdue": days >= settings.DECISION_DAYS,
        "link": link,
        "for_whom": for_whom,
    }


def _leave(user, employee) -> list[dict]:
    from leave.models import LeaveRequest

    items = []
    qs = LeaveRequest.objects.select_related("employee", "leave_type", "manager").exclude(employee__user=user)

    def title(r):
        dates = f"{r.from_date:%d/%m/%Y} to {r.to_date:%d/%m/%Y}"
        return f"{r.employee.full_name}: {r.leave_type.name.lower()}, {dates}"

    stands_in_for = delegator_ids(employee)
    at_manager = Q(manager__user=user) | Q(manager_id__in=stands_in_for)
    if has_role(user, Role.SUPERVISOR):
        nobody = Q(
            manager__isnull=True, pk__in=scope_queryset(user, LeaveRequest.objects.all(), "employee__campus")
        )
        at_manager |= nobody
    for r in qs.filter(at_manager, state=LeaveRequest.State.SUBMITTED):
        standing_in = r.manager is not None and r.manager.user_id != user.pk and r.manager_id in stands_in_for
        items.append(
            _item(
                "leave",
                "Leave to decide",
                title(r),
                r.waiting_since or r.updated_at,
                f"/leave/requests/{r.id}",
                for_whom=f"standing in for {r.manager.full_name}" if standing_in else "",
            )
        )
    if has_role(user, Role.HR_OFFICER, Role.HR_MANAGER):
        hr_step = scope_queryset(
            user, qs.filter(state=LeaveRequest.State.SUPERVISOR_APPROVED), "employee__campus"
        )
        for r in hr_step:
            items.append(
                _item(
                    "leave_hr",
                    "Leave for HR approval",
                    title(r),
                    r.waiting_since or r.updated_at,
                    f"/leave/requests/{r.id}",
                )
            )
    return items


def _bank(user) -> list[dict]:
    from people.models import BankAccount
    from people.views import BANK_DECIDE

    if not has_role(user, *BANK_DECIDE):
        return []
    pending = scope_queryset(
        user, BankAccount.objects.filter(state=BankAccount.State.PENDING), "employee__campus"
    ).exclude(created_by=user)
    return [
        _item(
            "bank",
            "Bank details to approve",
            f"{account.employee.full_name}: new bank details, ending {account.account_number_last4}",
            account.created_at,
            f"/people/{account.employee_id}",
        )
        for account in pending.select_related("employee")
    ]


def _corrections(user) -> list[dict]:
    from privacy.models import CorrectionRequest
    from privacy.views import CORRECTION_DECIDE

    if not has_role(user, *CORRECTION_DECIDE):
        return []
    open_ = scope_queryset(
        user, CorrectionRequest.objects.filter(state=CorrectionRequest.State.OPEN), "employee__campus"
    ).exclude(employee__user=user)
    return [
        _item(
            "correction",
            "Correction to answer",
            f"{c.employee.full_name}: {c.get_subject_display().lower()}",
            c.created_at,
            "/admin/corrections",
        )
        for c in open_.select_related("employee")
    ]


def _disposals(user) -> list[dict]:
    from privacy.models import DisposalRun
    from privacy.retention_views import KEEPERS

    if not has_role(user, *KEEPERS):
        return []
    runs = DisposalRun.objects.filter(state=DisposalRun.State.PROPOSED).exclude(created_by=user)
    return [
        _item(
            "disposal",
            "Disposal to approve",
            f"Records due under: {run.rule.name}",
            run.created_at,
            "/admin/retention",
        )
        for run in runs.select_related("rule")
    ]


def _hr_followups(user) -> list[dict]:
    from people.models import CareerEvent, ClearanceStep, Separation
    from people.views import HR_WRITE

    if not has_role(user, *HR_WRITE):
        return []
    items = []
    held = scope_queryset(
        user, CareerEvent.objects.filter(state=CareerEvent.State.BLOCKED), "employee__campus"
    )
    for event in held.select_related("employee"):
        items.append(
            _item(
                "career",
                "Career change held up",
                f"{event.employee.full_name}: {event.get_kind_display().lower()}. {event.problem}",
                event.updated_at,
                f"/people/{event.employee_id}",
            )
        )
    left = scope_queryset(user, Separation.objects.filter(state=Separation.State.LEFT), "employee__campus")
    open_steps = ClearanceStep.objects.filter(state=ClearanceStep.State.OPEN).exclude(code="account")
    for separation in left.filter(clearance__in=open_steps).distinct().select_related("employee"):
        items.append(
            _item(
                "clearance",
                "Clearance not finished",
                f"{separation.employee.full_name}: left on {separation.last_day:%d/%m/%Y}",
                separation.completed_at or separation.updated_at,
                f"/people/{separation.employee_id}",
            )
        )
    return items


def _incidents(user) -> list[dict]:
    """Reports to look into and notices the Act requires, for HR; safety actions, for whoever has one."""
    from incidents.duties import duties
    from incidents.models import Action, Incident, Notice
    from incidents.views import KEEPERS

    items = []
    today = timezone.localdate()
    if has_role(user, *KEEPERS):
        open_ = scope_queryset(user, Incident.objects.exclude(state=Incident.State.CLOSED), "campus")
        for incident in open_.prefetch_related("people__employee", "notices"):
            link = f"/incidents/{incident.pk}"
            if incident.state == Incident.State.REPORTED:
                what = f"{incident.reference}: {incident.get_kind_display().lower()} at {incident.place}"
                items.append(_item("incident", "Incident to look into", what, incident.created_at, link))
            for due in duties(incident, today):
                if not due.unsent:
                    continue
                what = (
                    f"{incident.reference}: {Notice.Duty(due.duty).label.lower()}, by {due.due_on:%d/%m/%Y}"
                )
                item = _item("safety_notice", "Notice to send", what, incident.created_at, link)
                item["overdue"] = due.overdue(today)
                items.append(item)
    given = Action.objects.filter(owner__user=user, done_on__isnull=True).select_related("incident")
    for action in given:
        what = f"{action.incident.reference}: {action.what}, by {action.due_on:%d/%m/%Y}"
        item = _item("safety_action", "Safety action", what, action.created_at, "/incidents")
        item["overdue"] = today > action.due_on
        items.append(item)
    return items


def _signatures(user) -> list[dict]:
    from signing.models import SignatureRequest

    waiting = SignatureRequest.objects.filter(state=SignatureRequest.State.WAITING, employee__user=user)
    return [
        _item(
            "signature", "To sign", f"{r.document.title}: {r.get_kind_display().lower()}", r.created_at, "/me"
        )
        for r in waiting.select_related("document")
    ]


def waiting_for(user) -> list[dict]:
    employee = getattr(user, "employee", None)
    items = [
        *_leave(user, employee),
        *_bank(user),
        *_corrections(user),
        *_disposals(user),
        *_hr_followups(user),
        *_incidents(user),
        *_signatures(user),
    ]
    return sorted(items, key=lambda item: item["since"])
