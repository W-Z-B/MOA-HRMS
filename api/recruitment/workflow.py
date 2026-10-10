"""The application's workflow (H-W01), on the approvals engine (item 1.33) shared by every module.

A candidate holds no account, so none of the engine's OWNER/MANAGER/STAND_IN actors apply here (unlike
``leave.workflow``): every transition is taken by HR on the candidate's behalf, from what the candidate
told them (by email, by phone, at interview). ``decision_comment`` and the per-step notes on the model are
how that is kept.

Decided-and-closed states are DECLINED, REJECTED and WITHDRAWN (``Application.CLOSED_STATES`` minus
ACCEPTED): a candidate's data is not needed once a decision there is final, so the Data Protection Act 2023
retention date is set then, not on acceptance, when the person is on their way to becoming an employee.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from approvals.engine import Transition, WorkflowDefinition, WorkflowError
from iam.models import Role

__all__ = ["APPLICATION", "WorkflowError"]

HR = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)


def _set_retention(instance, request):
    from recruitment.models import Application

    if instance.state == Application.State.ACCEPTED:
        return
    days = settings.RECRUITMENT_RETENTION_DAYS
    instance.candidate.retention_date = timezone.localdate() + timedelta(days=days)
    instance.candidate.save(update_fields=["retention_date", "updated_at"])


def _create_hire(instance, request):
    from recruitment.models import Hire

    Hire.objects.create(
        application=instance,
        vacancy=instance.vacancy,
        candidate=instance.candidate,
        created_by=request.user,
        updated_by=request.user,
    )


def _notify_hr_of_response(instance, request):
    from notifications.services import notify, users_with_role

    verb = "accepted the offer for" if instance.state == "accepted" else "declined the offer for"
    notify(
        users_with_role(Role.HR_OFFICER).exclude(pk=request.user.pk),
        title=f"{instance.candidate.full_name} {verb} {instance.vacancy.title}",
        body=instance.decision_comment or "",
        link="/recruitment/applications",
        dedupe_key=f"application:{instance.id}:{instance.state}",
    )


APPLICATION = WorkflowDefinition(
    key="recruitment_application",
    transitions=(
        Transition("shortlist", ("submitted",), "shortlisted", HR),
        Transition(
            "schedule_interview", ("shortlisted",), "interview_scheduled", HR
        ),  # the interview row itself is created by the caller, in the same transaction
        Transition("mark_interviewed", ("interview_scheduled",), "interviewed", HR),
        Transition("offer", ("interviewed",), "offered", HR),
        Transition("accept", ("offered",), "accepted", HR, on_success=(_create_hire, _notify_hr_of_response)),
        Transition(
            "decline", ("offered",), "declined", HR, on_success=(_set_retention, _notify_hr_of_response)
        ),
        Transition(
            "reject",
            ("submitted", "shortlisted", "interviewed", "offered"),
            "rejected",
            HR,
            requires_comment=True,
            on_success=(_set_retention,),
        ),
        Transition(
            "withdraw",
            ("submitted", "shortlisted", "interview_scheduled", "interviewed", "offered"),
            "withdrawn",
            HR,
            requires_comment=True,
            on_success=(_set_retention,),
        ),
    ),
)
