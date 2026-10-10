"""The onboarding record's workflow (H-W02), on the approvals engine (item 1.33) shared by every module.

Unlike ``leave.workflow``, there is no manager step here: HR runs the checklist directly with the new
hire. The new hire (the record's ``OWNER``) submits the documents asked for; HR may submit on their
behalf too (a scanned contract HR holds, for someone without their own means to upload yet), confirms
them, and completes the record once every other step is done or not needed, or cancels it if the hire
falls through.
"""

from approvals.engine import OWNER, Transition, WorkflowDefinition, WorkflowError
from iam.models import Role

__all__ = ["ONBOARDING", "WorkflowError"]

HR = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)


def _check_has_document(instance, request):
    if not instance.employee.documents.exists():
        raise WorkflowError("Upload at least one document first.", code="no_documents")


def _notify_hr_of_documents(instance, request):
    from notifications.services import notify, users_with_role

    notify(
        users_with_role(Role.HR_OFFICER, campus=instance.employee.campus),
        title=f"{instance.employee.full_name} submitted their onboarding documents",
        body="Check the documents filed and confirm them.",
        link="/onboarding",
        kind="approval",
        dedupe_key=f"onboarding:{instance.id}:documents",
    )


def _close_documents_step(instance, request):
    from people.models import OnboardingStep
    from people.onboarding import close_step

    step = instance.steps.filter(code="documents", state=OnboardingStep.State.OPEN).first()
    if step is not None:
        close_step(request, step, OnboardingStep.State.DONE, instance.decision_comment or "Confirmed by HR")


def _require_other_steps_done(instance, request):
    """Every step must be done or not needed first. "documents" is closed either by ``confirm_documents``
    (which returns the record to "in_progress" before this guard ever runs) or, for an appointment that
    genuinely needs none, by HR marking it not needed directly (``people.onboarding.clear_step``)."""
    from people.models import OnboardingStep

    if instance.steps.filter(state=OnboardingStep.State.OPEN).exists():
        raise WorkflowError("Every step must be done or not needed first.", code="steps_open")


def _activate_employee(instance, request):
    from django.utils import timezone

    from people.models import Employee

    employee = instance.employee
    employee.status = Employee.Status.ACTIVE
    employee.updated_by = request.user
    employee.save(update_fields=["status", "updated_by", "updated_at"])
    instance.completed_at = timezone.now()
    instance.save(update_fields=["completed_at"])


def _notify_new_hire_active(instance, request):
    from notifications.services import notify

    if instance.employee.user_id:
        notify(
            [instance.employee.user],
            title="Your onboarding is complete",
            body="Welcome to the Guyana School of Agriculture. Your staff record is now active.",
            link="/me",
            dedupe_key=f"onboarding:{instance.id}:completed",
        )


def _end_appointment_on_cancel(instance, request):
    from django.utils import timezone

    from people.models import Assignment, Employee

    employee = instance.employee
    today = timezone.localdate()
    for assignment in employee.assignments.filter(status=Assignment.Status.ACTIVE):
        # The appointment may start in the future (a new hire who has not started yet): never end it
        # before it begins, the same rule people.leaving.complete applies on the way out.
        assignment.end_date = max(today, assignment.start_date)
        assignment.status = Assignment.Status.ENDED
        assignment.updated_by = request.user
        assignment.save(update_fields=["end_date", "status", "updated_by", "updated_at"])
    employee.status = Employee.Status.SEPARATED
    employee.updated_by = request.user
    employee.save(update_fields=["status", "updated_by", "updated_at"])


ONBOARDING = WorkflowDefinition(
    key="onboarding",
    waiting_states=("documents_submitted",),
    transitions=(
        Transition(
            "submit_documents",
            ("in_progress",),
            "documents_submitted",
            (OWNER, *HR),
            guards=(_check_has_document,),
            on_success=(_notify_hr_of_documents,),
        ),
        Transition(
            "confirm_documents",
            ("documents_submitted",),
            "in_progress",
            HR,
            independent=True,
            on_success=(_close_documents_step,),
        ),
        Transition(
            "send_back",
            ("documents_submitted",),
            "in_progress",
            HR,
            requires_comment=True,
            independent=True,
        ),
        Transition(
            "complete",
            ("in_progress",),
            "completed",
            HR,
            independent=True,
            guards=(_require_other_steps_done,),
            on_success=(_activate_employee, _notify_new_hire_active),
        ),
        Transition(
            "cancel",
            ("in_progress", "documents_submitted"),
            "cancelled",
            HR,
            requires_comment=True,
            independent=True,
            on_success=(_end_appointment_on_cancel,),
        ),
    ),
)
