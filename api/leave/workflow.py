"""Generic request workflow: states, transitions, actor rules, guards and side effects.

Definitions are plain data so they can later be loaded from the database (workflow_definition
table in the design). The leave request definition lives at the bottom of this module.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction

from audit.services import record
from iam.models import Role
from iam.services import has_role

OWNER = "owner"  # the employee the request belongs to
MANAGER = "manager"  # the person the request was sent to on submission
STAND_IN = "stand_in"  # a campus supervisor, only while the request has no manager to go to


class WorkflowError(Exception):
    code = "invalid_transition"

    def __init__(self, detail: str, code: str | None = None):
        super().__init__(detail)
        if code:
            self.code = code


@dataclass(frozen=True)
class Transition:
    action: str
    sources: tuple[str, ...]
    target: str
    actors: tuple[str, ...]  # role codes, or OWNER, MANAGER, STAND_IN
    requires_comment: bool = False
    independent: bool = False  # a decision on the request: never taken by the employee it belongs to
    guards: tuple[Callable, ...] = field(default_factory=tuple)  # run first; raise WorkflowError to refuse
    on_success: tuple[Callable, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    transitions: tuple[Transition, ...]

    def _can_act(self, instance, user, transition: Transition) -> bool:
        employee = getattr(user, "employee", None)
        is_owner = employee is not None and employee.pk == instance.employee_id
        if transition.independent and is_owner:
            return False
        manager_id = getattr(instance, "manager_id", None)
        for actor in transition.actors:
            if actor == OWNER:
                if is_owner:
                    return True
            elif actor == MANAGER:
                if employee is not None and manager_id is not None and employee.pk == manager_id:
                    return True
            elif actor == STAND_IN:
                if manager_id is None and has_role(user, Role.SUPERVISOR):
                    return True
            elif has_role(user, actor):
                return True
        return False

    def allowed_actions(self, instance, user) -> list[str]:
        return [
            t.action
            for t in self.transitions
            if instance.state in t.sources and self._can_act(instance, user, t)
        ]

    def apply(self, instance, action: str, *, request, comment: str = ""):
        """Move `instance` through `action` as request.user, run side effects, audit. Atomic."""
        user = request.user
        matches = [t for t in self.transitions if t.action == action and instance.state in t.sources]
        if not matches:
            raise WorkflowError(f"'{action}' is not allowed from state '{instance.state}'.")
        transition = matches[0]
        if not self._can_act(instance, user, transition):
            raise WorkflowError("You are not permitted to perform this action.", code="forbidden_actor")
        if transition.requires_comment and not comment.strip():
            raise WorkflowError("A comment is required for this action.", code="comment_required")
        for guard in transition.guards:
            guard(instance, request)
        with transaction.atomic():
            before = {"state": instance.state}
            instance.previous_state = instance.state
            instance.state = transition.target
            if comment:
                instance.decision_comment = comment
            instance.updated_by = user
            instance.save()
            for hook in transition.on_success:
                hook(instance, request)
            record(request, f"transition:{action}", instance, before=before, after={"state": instance.state})
        return instance


# Leave request: guards and side effects.


def _check_rules(instance, request):
    """Balance, overlap, eligibility and evidence, checked again at the moment of submission."""
    from leave.rules import assess, in_days

    result = assess(
        instance.employee, instance.leave_type, instance.from_date, instance.to_date, exclude=instance
    )
    if result.problems:
        raise WorkflowError(result.problems[0].detail, code=result.problems[0].code)
    if result.evidence_required and instance.evidence_id is None:
        why = (
            f"{in_days(result.beyond)} of this request are beyond your balance"
            if result.beyond
            else f"{instance.leave_type.name.lower()} always needs one"
        )
        raise WorkflowError(
            f"Attach your {result.evidence_name.lower()} before submitting: {why}.", code="evidence_required"
        )


def _send_to_manager(instance, request):
    from people.services import manager_of

    instance.manager = manager_of(instance.employee)
    instance.save(update_fields=["manager"])


def _debit_ledger(instance, request):
    from leave.services import debit_for_request

    debit_for_request(instance, actor=request.user)


def _issue_receipt(instance, request):
    from leave.receipts import issue

    issue(instance)


def _record_decision(instance, request):
    from leave.models import LeaveDecision, LeaveRequest

    user = request.user
    employee = getattr(user, "employee", None)
    if instance.manager_id is None:
        is_manager = has_role(user, Role.SUPERVISOR) and not has_role(user, *HR)
    else:
        is_manager = employee is not None and employee.pk == instance.manager_id
    at_first_step = instance.previous_state == LeaveRequest.State.SUBMITTED
    rejected = instance.state == LeaveRequest.State.REJECTED
    LeaveDecision.objects.create(
        request=instance,
        step=LeaveDecision.Step.MANAGER if at_first_step and is_manager else LeaveDecision.Step.HR,
        outcome=LeaveDecision.Outcome.REJECTED if rejected else LeaveDecision.Outcome.APPROVED,
        actor=user,
        actor_name=employee.full_name if employee else user.get_full_name() or user.get_username(),
        comment=instance.decision_comment if rejected else "",
    )


def _summary(instance) -> str:
    from leave.rules import in_days

    return (
        f"{instance.leave_type.name}, {instance.from_date:%d/%m/%Y} to {instance.to_date:%d/%m/%Y} "
        f"({in_days(instance.days)})."
    )


def _evidence_note(instance) -> str:
    return f" {instance.leave_type.evidence_name} attached." if instance.evidence_id else ""


def _last_decider(instance, fallback: str) -> str:
    decision = instance.decisions.order_by("-decided_at", "-id").first()
    return decision.actor_name if decision else fallback


def _notify_manager(instance, request):
    from notifications.services import notify, users_with_role

    if instance.manager_id:
        recipients = [instance.manager.user]
    else:
        recipients = users_with_role(Role.SUPERVISOR, campus=instance.employee.campus).exclude(
            employee=instance.employee
        )
    notify(
        recipients,
        title=f"Leave request from {instance.employee.full_name}",
        body=_summary(instance) + _evidence_note(instance) + " Please approve or reject.",
        link=f"/leave/requests/{instance.id}",
        kind="approval",
        dedupe_key=f"leave:{instance.id}:supervisor",
    )


def _notify_hr(instance, request):
    from notifications.services import notify, users_with_role

    notify(
        users_with_role(Role.HR_OFFICER, campus=instance.employee.campus).exclude(employee=instance.employee),
        title=f"Leave request from {instance.employee.full_name} awaits HR approval",
        body=(
            _summary(instance)
            + _evidence_note(instance)
            + f" Approved by {_last_decider(instance, 'the manager')}."
        ),
        link=f"/leave/requests/{instance.id}",
        kind="approval",
        dedupe_key=f"leave:{instance.id}:hr",
    )


def _notify_owner_of_progress(instance, request):
    from notifications.services import notify

    notify(
        [instance.employee.user],
        title="Your manager approved your leave request",
        body=(
            _summary(instance)
            + f" Approved by {_last_decider(instance, 'your manager')}."
            + " It is now with Human Resources for final approval."
        ),
        link=f"/leave/requests/{instance.id}",
        dedupe_key=f"leave:{instance.id}:{instance.state}",
    )


def _notify_owner_of_approval(instance, request):
    from leave.receipts import remaining_line
    from leave.rules import in_days
    from notifications.services import notify

    receipt = instance.receipt
    beyond = ""
    if instance.days_beyond:
        beyond = (
            f" {in_days(instance.days_beyond)} beyond your entitlement, supported by your "
            f"{instance.leave_type.evidence_name.lower()}."
        )
    notify(
        [instance.employee.user],
        title="Your leave request was approved",
        body=(
            _summary(instance)
            + beyond
            + f" Return to work on {date.fromisoformat(receipt['return_date']):%d/%m/%Y}."
            + f" Remaining: {remaining_line(receipt)}."
            + f" Receipt {receipt['number']}."
        ),
        link=f"/leave/requests/{instance.id}",
        dedupe_key=f"leave:{instance.id}:{instance.state}",
    )


def _notify_owner_of_rejection(instance, request):
    from notifications.services import notify

    comment = f" Comment: {instance.decision_comment}" if instance.decision_comment else ""
    notify(
        [instance.employee.user],
        title="Your leave request was rejected",
        body=_summary(instance) + comment + " No days were taken from your balance.",
        link=f"/leave/requests/{instance.id}",
        dedupe_key=f"leave:{instance.id}:{instance.state}",
    )


HR = (Role.HR_OFFICER, Role.HR_MANAGER)

LEAVE_REQUEST = WorkflowDefinition(
    key="leave_request",
    transitions=(
        Transition(
            "submit",
            ("draft",),
            "submitted",
            (OWNER, *HR),
            guards=(_check_rules,),
            on_success=(_send_to_manager, _notify_manager),
        ),
        Transition(
            "approve",
            ("submitted",),
            "supervisor_approved",
            (MANAGER, STAND_IN),
            independent=True,
            on_success=(_record_decision, _notify_hr, _notify_owner_of_progress),
        ),
        Transition(
            "approve",
            ("supervisor_approved",),
            "approved",
            HR,
            independent=True,
            on_success=(_record_decision, _debit_ledger, _issue_receipt, _notify_owner_of_approval),
        ),
        Transition(
            "reject",
            ("submitted",),
            "rejected",
            (MANAGER, STAND_IN, *HR),
            requires_comment=True,
            independent=True,
            on_success=(_record_decision, _notify_owner_of_rejection),
        ),
        Transition(
            "reject",
            ("supervisor_approved",),
            "rejected",
            HR,
            requires_comment=True,
            independent=True,
            on_success=(_record_decision, _notify_owner_of_rejection),
        ),
        Transition(
            "cancel", ("draft", "submitted", "supervisor_approved"), "cancelled", (OWNER, Role.HR_OFFICER)
        ),
    ),
)
