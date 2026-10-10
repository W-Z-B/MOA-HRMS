"""Joining the School (item H-W02): the mirror of leaving (``people.leaving``).

Onboarding starts from an accepted hire (``recruitment.Hire``) and ends when HR completes it: a staff
record and a first appointment are created straight away, equipment and documents are collected against
them, an account is opened, and the person becomes a full "active" member of staff only once every step
is done or marked not needed (``people.onboarding_workflow.ONBOARDING``, the approvals engine).
"""

from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import record, snapshot
from people.leaving import Refused
from people.models import Assignment, Employee, Onboarding, OnboardingStep

__all__ = [
    "Refused",
    "STEPS",
    "CONFLICTS",
    "start_onboarding",
    "close_step",
    "clear_step",
    "provision_account",
]

# The checklist, in order (item H-W02): what is collected or issued, and who confirms it. "documents" and
# "account" close themselves, through the workflow and through provision_account respectively, so HR
# cannot tick either "done" by hand (clear_step refuses that); either may still be marked "not needed" for
# an appointment that genuinely has none, such as a sessional worker with no sign-in account.
STEPS = [
    ("documents", "Required documents collected: signed contract, identification, certificates", "HR"),
    ("account", "Sign-in account opened and the invitation sent", "HR"),
    ("equipment", "Keys, equipment and an identity card issued", "HR, from the register of items"),
    (
        "induction",
        "Induction given: policies, conditions of service, health and safety",
        "The head of the unit",
    ),
]
STEP = OnboardingStep.State
CONFLICTS = frozenset(
    {
        "already_onboarded",
        "already_started",
        "employee_no_taken",
        "position_filled",
        "not_open",
        "cancelled",
        "account_exists",
        "account_step_closed",
    }
)


def _day(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def start_onboarding(
    request,
    *,
    hire,
    employee_no: str,
    date_of_birth: date,
    gender: str,
    appointment_type: str,
    start_date: date | None = None,
) -> Onboarding:
    """Open the staff record and first appointment an accepted hire becomes, and the checklist for it.

    The employee number and date of birth are asked for here because neither is collected anywhere before
    this point (a candidate, ``recruitment.Candidate``, is deliberately kept apart from a staff record);
    everything else a new ``Employee`` needs is read off the candidate and the vacancy's post.
    """
    if hire.employee_id is not None:
        raise Refused("already_onboarded", "This hire already has a staff record.")
    if Onboarding.objects.filter(hire=hire).exists():
        raise Refused("already_started", "Onboarding has already been started for this hire.")
    if Employee.objects.filter(employee_no=employee_no).exists():
        raise Refused("employee_no_taken", f"Employee number {employee_no} is already in use.")
    candidate = hire.candidate
    position = hire.vacancy.position
    with transaction.atomic():
        employee = Employee.objects.create(
            employee_no=employee_no,
            first_name=candidate.first_name,
            last_name=candidate.last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            email=candidate.email,
            phone=candidate.phone,
            address=candidate.address,
            campus=position.org_unit.campus,
            status=Employee.Status.ONBOARDING,
            created_by=request.user,
            updated_by=request.user,
        )
        record(request, "create", employee, after=snapshot(employee), reason="Created by onboarding")
        try:
            with transaction.atomic():
                assignment = Assignment.objects.create(
                    employee=employee,
                    position=position,
                    appointment_type=appointment_type,
                    start_date=start_date or hire.start_date or timezone.localdate(),
                    created_by=request.user,
                    updated_by=request.user,
                )
        except IntegrityError as exc:
            raise Refused("position_filled", "That post already has a substantive holder.") from exc
        record(request, "create", assignment, after=snapshot(assignment))
        hire.employee = employee
        hire.updated_by = request.user
        hire.save(update_fields=["employee", "updated_by", "updated_at"])
        onboarding = Onboarding.objects.create(
            hire=hire,
            employee=employee,
            started_on=timezone.localdate(),
            created_by=request.user,
            updated_by=request.user,
        )
        record(request, "onboarding_started", onboarding, after=snapshot(onboarding))
        OnboardingStep.objects.bulk_create(
            OnboardingStep(
                onboarding=onboarding,
                code=code,
                label=label,
                who=who,
                position=index,
                created_by=request.user,
                updated_by=request.user,
            )
            for index, (code, label, who) in enumerate(STEPS)
        )
    return onboarding


def close_step(request, step: OnboardingStep, state: str, note: str) -> None:
    before = snapshot(step)
    step.state = state
    step.note = note.strip()[:300]
    step.cleared_at = timezone.now()
    step.cleared_by = getattr(request, "user", None) if request is not None else None
    step.updated_by = step.cleared_by
    step.save(update_fields=["state", "note", "cleared_at", "cleared_by", "updated_by", "updated_at"])
    record(request, "onboarding_step", step, before=before, after=snapshot(step), reason=step.note)


def clear_step(request, step: OnboardingStep, *, done: bool, note: str) -> OnboardingStep:
    """Close one step, done or not needed. "documents" and "account" close themselves when done."""
    if step.state != STEP.OPEN:
        raise Refused("not_open", "That step is already closed.")
    if step.onboarding.state == Onboarding.State.CANCELLED:
        raise Refused("cancelled", "This onboarding was cancelled.")
    if done and step.code == "documents":
        raise Refused("documents_step", "This step closes once HR confirms the documents received.")
    if done and step.code == "account":
        raise Refused("account_step", "This step closes once the account is opened.")
    with transaction.atomic():
        close_step(request, step, STEP.DONE if done else STEP.NOT_NEEDED, note)
    return step


def provision_account(request, onboarding: Onboarding):
    """Open the new hire's account and send the invitation (``iam.accounts``); closes the "account" step."""
    from iam.accounts import open_account, send_invitation

    step = onboarding.steps.filter(code="account", state=STEP.OPEN).first()
    if step is None:
        raise Refused("account_step_closed", "That step is already closed.")
    employee = onboarding.employee
    if employee.user_id is not None:
        raise Refused("account_exists", "This person already has an account.")
    user = open_account(employee, granted_by=request.user)
    send_invitation(user)
    with transaction.atomic():
        close_step(request, step, STEP.DONE, "Account opened and the invitation sent")
    return employee
