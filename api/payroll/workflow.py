"""The pay run's workflow (H-M01), on the approvals engine (item 1.33) shared by every module.

ADR 0004, point 3: the person who prepares a pay run cannot approve it. The engine's built-in
`independent` flag protects a request's own employee from deciding it (leave.workflow's use); a pay run
belongs to no one employee, so the same rule is written here as a guard instead.
"""

from django.utils import timezone

from approvals.engine import Transition, WorkflowDefinition, WorkflowError
from iam.models import Role

__all__ = ["PAY_RUN", "WorkflowError"]

FINANCE = (Role.FINANCE, Role.ADMINISTRATOR)


def _calculate(instance, request):
    from payroll.models import Payslip
    from payroll.services import compute_payslip, payable_employees

    instance.payslips.all().delete()  # a recalculation replaces what is there, never adds to it
    totals = {"gross": 0, "nis_employee": 0, "nis_employer": 0, "paye": 0, "net": 0}
    for employee in payable_employees():
        figures = compute_payslip(employee, instance.period)
        if figures is None:
            continue
        Payslip.objects.create(pay_run=instance, employee=employee, **figures)
        for key in totals:
            totals[key] += figures[key]
    instance.total_gross = totals["gross"]
    instance.total_nis_employee = totals["nis_employee"]
    instance.total_nis_employer = totals["nis_employer"]
    instance.total_paye = totals["paye"]
    instance.total_net = totals["net"]
    instance.calculated_at = timezone.now()
    instance.save(
        update_fields=[
            "total_gross",
            "total_nis_employee",
            "total_nis_employer",
            "total_paye",
            "total_net",
            "calculated_at",
        ]
    )


def _not_the_preparer(instance, request):
    """Refuses an approval from whoever last calculated the run (ADR 0004, point 3)."""
    if instance.updated_by_id == request.user.pk:
        raise WorkflowError(
            "Someone other than whoever calculated this run must approve it.", code="same_preparer"
        )


def _record_approved_at(instance, request):
    instance.approved_at = timezone.now()
    instance.save(update_fields=["approved_at"])


def _disburse(instance, request):
    from payroll.payslip import issue_payslips

    instance.disbursed_at = timezone.now()
    instance.save(update_fields=["disbursed_at"])
    issue_payslips(instance, request)


def _notify_finance(instance, request):
    from notifications.services import notify, users_with_role

    recipients = list(users_with_role(Role.FINANCE)) + list(users_with_role(Role.HR_MANAGER))
    others = [u for u in recipients if u.pk != request.user.pk]
    notify(
        others,
        title=f"Pay run {instance.period} is calculated and ready to approve",
        body=f"Net pay {instance.total_net}. Someone other than whoever calculated it must approve it.",
        link="/payroll?tab=runs",
        kind="approval",
        dedupe_key=f"payrun:{instance.id}:calculated",
    )


PAY_RUN = WorkflowDefinition(
    key="pay_run",
    waiting_states=("calculated",),
    transitions=(
        Transition("calculate", ("draft",), "calculated", FINANCE, on_success=(_calculate, _notify_finance)),
        Transition(
            "recalculate",
            ("calculated",),
            "calculated",
            FINANCE,
            on_success=(_calculate, _notify_finance),
        ),
        Transition(
            "approve",
            ("calculated",),
            "approved",
            FINANCE,
            guards=(_not_the_preparer,),
            on_success=(_record_approved_at,),
        ),
        Transition("reopen", ("calculated", "approved"), "draft", FINANCE),
        Transition("disburse", ("approved",), "disbursed", FINANCE, on_success=(_disburse,)),
    ),
)
