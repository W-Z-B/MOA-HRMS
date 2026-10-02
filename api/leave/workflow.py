"""The leave request's workflow: its guards, side effects and definition, on the approvals engine (item 1.33).

The engine (approvals.engine) is shared by every module; this module holds what is particular to leave.
"""

from datetime import date

from approvals.engine import MANAGER, OWNER, STAND_IN, Transition, WorkflowDefinition, WorkflowError
from iam.models import Role
from iam.services import has_role

__all__ = ["LEAVE_REQUEST", "WorkflowError"]


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
    from approvals.delegation import acts_for
    from leave.models import LeaveDecision, LeaveRequest

    user = request.user
    employee = getattr(user, "employee", None)
    standing_in = False
    if instance.manager_id is None:
        is_manager = has_role(user, Role.SUPERVISOR) and not has_role(user, *HR)
    else:
        own = employee is not None and employee.pk == instance.manager_id
        standing_in = not own and acts_for(employee, instance.manager_id)
        is_manager = own or standing_in
    at_first_step = instance.previous_state == LeaveRequest.State.SUBMITTED
    rejected = instance.state == LeaveRequest.State.REJECTED
    name = employee.full_name if employee else user.get_full_name() or user.get_username()
    if standing_in and at_first_step:
        name = f"{name}, standing in for {instance.manager.full_name}"
    LeaveDecision.objects.create(
        request=instance,
        step=LeaveDecision.Step.MANAGER if at_first_step and is_manager else LeaveDecision.Step.HR,
        outcome=LeaveDecision.Outcome.REJECTED if rejected else LeaveDecision.Outcome.APPROVED,
        actor=user,
        actor_name=name[:160],
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
        # The manager, and whoever stands in for them while they are away (item 1.33).
        from approvals.delegation import delegates_of, users_of

        recipients = users_of([instance.manager, *delegates_of(instance.manager)])
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
    waiting_states=("submitted", "supervisor_approved"),
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
