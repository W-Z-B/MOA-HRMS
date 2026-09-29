"""Generic request workflow: states, transitions, actor rules and side effects.

Definitions are plain data so they can later be loaded from the database (workflow_definition
table in the design). The leave request definition lives at the bottom of this module.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from django.db import transaction

from audit.services import record
from iam.models import Role
from iam.services import has_role


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
    actors: tuple[str, ...]  # role codes, or "owner" for the employee who owns the request
    requires_comment: bool = False
    on_success: tuple[Callable, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    transitions: tuple[Transition, ...]

    def _can_act(self, instance, user, transition: Transition) -> bool:
        for actor in transition.actors:
            if actor == "owner":
                employee = getattr(user, "employee", None)
                if employee is not None and employee.pk == instance.employee_id:
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
        with transaction.atomic():
            before = {"state": instance.state}
            instance.state = transition.target
            if comment:
                instance.decision_comment = comment
            instance.updated_by = user
            instance.save()
            for hook in transition.on_success:
                hook(instance, request)
            record(request, f"transition:{action}", instance, before=before, after={"state": instance.state})
        return instance


def _debit_ledger(instance, request):
    from leave.services import debit_for_request

    debit_for_request(instance, actor=request.user)


def _summary(instance) -> str:
    return (
        f"{instance.leave_type.name}, {instance.from_date:%d/%m/%Y} to {instance.to_date:%d/%m/%Y} "
        f"({instance.days} working days)."
    )


def _notify_supervisors(instance, request):
    from notifications.services import notify, users_with_role

    notify(
        users_with_role(Role.SUPERVISOR, campus=instance.employee.campus),
        title=f"Leave request from {instance.employee.full_name}",
        body=_summary(instance) + " Please approve or reject.",
        link=f"/leave/requests/{instance.id}",
        kind="approval",
        dedupe_key=f"leave:{instance.id}:supervisor",
    )


def _notify_hr(instance, request):
    from notifications.services import notify, users_with_role

    notify(
        users_with_role(Role.HR_OFFICER, campus=instance.employee.campus),
        title=f"Leave request from {instance.employee.full_name} awaits HR approval",
        body=_summary(instance) + " Supervisor approved.",
        link=f"/leave/requests/{instance.id}",
        kind="approval",
        dedupe_key=f"leave:{instance.id}:hr",
    )


def _notify_owner(instance, request):
    from notifications.services import notify

    comment = f" Comment: {instance.decision_comment}" if instance.decision_comment else ""
    notify(
        [instance.employee.user],
        title=f"Your leave request was {instance.get_state_display().lower()}",
        body=_summary(instance) + comment,
        link=f"/leave/requests/{instance.id}",
        dedupe_key=f"leave:{instance.id}:{instance.state}",
    )


LEAVE_REQUEST = WorkflowDefinition(
    key="leave_request",
    transitions=(
        Transition(
            "submit",
            ("draft",),
            "submitted",
            ("owner", Role.HR_OFFICER, Role.HR_MANAGER),
            on_success=(_notify_supervisors,),
        ),
        Transition(
            "approve", ("submitted",), "supervisor_approved", (Role.SUPERVISOR,), on_success=(_notify_hr,)
        ),
        Transition(
            "approve",
            ("supervisor_approved",),
            "approved",
            (Role.HR_OFFICER, Role.HR_MANAGER),
            on_success=(_debit_ledger, _notify_owner),
        ),
        Transition(
            "reject",
            ("submitted", "supervisor_approved"),
            "rejected",
            (Role.SUPERVISOR, Role.HR_OFFICER, Role.HR_MANAGER),
            requires_comment=True,
            on_success=(_notify_owner,),
        ),
        Transition(
            "cancel", ("draft", "submitted", "supervisor_approved"), "cancelled", ("owner", Role.HR_OFFICER)
        ),
    ),
)
