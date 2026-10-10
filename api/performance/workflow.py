"""The appraisal's workflow (H-M03), on the approvals engine (item 1.33) shared by every module.

Shaped like ``leave.workflow``: the employee (``OWNER``) submits their self-assessment; their manager (or,
when none is on record, HR) rates it; HR signs it off, or sends it back for another look.
"""

from django.utils import timezone

from approvals.engine import MANAGER, OWNER, Transition, WorkflowDefinition, WorkflowError
from iam.models import Role

__all__ = ["APPRAISAL", "WorkflowError"]

HR_SIGN = (Role.HR_MANAGER, Role.ADMINISTRATOR)


def _check_self_assessment(instance, request):
    if not instance.self_assessment.strip():
        raise WorkflowError("Write your self-assessment first.", code="no_self_assessment")


def _stamp_self_assessed(instance, request):
    instance.self_assessed_at = timezone.now()
    instance.save(update_fields=["self_assessed_at"])


def _check_manager_assessment(instance, request):
    if not instance.manager_assessment.strip():
        raise WorkflowError("Write the manager's assessment first.", code="no_manager_assessment")
    if instance.overall_rating is None:
        raise WorkflowError("Give an overall rating.", code="no_rating")


def _stamp_rated(instance, request):
    instance.rated_at = timezone.now()
    instance.save(update_fields=["rated_at"])


def _stamp_signed(instance, request):
    instance.signed_at = timezone.now()
    instance.save(update_fields=["signed_at"])


def _notify_manager_of_self_assessment(instance, request):
    from notifications.services import notify, users_with_role

    title = f"{instance.employee.full_name} completed their self-assessment"
    body = f"{instance.cycle.name} {instance.cycle.year}: rate it when ready."
    if instance.manager is not None and instance.manager.user_id:
        notify(
            [instance.manager.user],
            title=title,
            body=body,
            link="/appraisals?tab=team",
            kind="approval",
            dedupe_key=f"appraisal:{instance.id}:self_assessed",
        )
    else:
        notify(
            users_with_role(Role.HR_OFFICER, campus=instance.employee.campus),
            title=f"{title}, with no manager on record",
            body=body,
            link="/appraisals?tab=team",
            kind="approval",
            dedupe_key=f"appraisal:{instance.id}:self_assessed",
        )


def _notify_employee_of_rating(instance, request):
    from notifications.services import notify

    if instance.employee.user_id:
        notify(
            [instance.employee.user],
            title="Your appraisal has been rated",
            body=f"{instance.cycle.name} {instance.cycle.year}: see your manager's assessment.",
            link="/appraisals",
            dedupe_key=f"appraisal:{instance.id}:rated",
        )


APPRAISAL = WorkflowDefinition(
    key="appraisal",
    waiting_states=("self_assessed", "rated"),
    transitions=(
        Transition(
            "submit_self_assessment",
            ("draft",),
            "self_assessed",
            (OWNER,),
            guards=(_check_self_assessment,),
            on_success=(_stamp_self_assessed, _notify_manager_of_self_assessment),
        ),
        Transition(
            "rate",
            ("self_assessed",),
            "rated",
            (MANAGER, *HR_SIGN),
            independent=True,
            guards=(_check_manager_assessment,),
            on_success=(_stamp_rated, _notify_employee_of_rating),
        ),
        Transition("sign_off", ("rated",), "signed", HR_SIGN, independent=True, on_success=(_stamp_signed,)),
        Transition(
            "reopen",
            ("rated", "signed"),
            "self_assessed",
            HR_SIGN,
            requires_comment=True,
            independent=True,
        ),
    ),
)
