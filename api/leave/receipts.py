"""The receipt an employee receives on final approval: the leave granted and what is left.

It is written once and kept on the request, so it still shows the balances as they stood on the
day of approval after later leave has changed them.
"""

from decimal import Decimal

from django.utils import timezone

from leave.rules import in_days
from leave.services import ZERO, balances_for, next_working_day


def number(instance) -> str:
    return f"LR-{instance.from_date:%Y}-{instance.pk:06d}"


def issue(instance) -> dict:
    """Build the receipt from the request as approved and store it. Call after the ledger debit."""
    employee = instance.employee
    assignment = employee.current_assignment
    receipt = {
        "number": number(instance),
        "issued_at": timezone.now().isoformat(),
        "employee_no": employee.employee_no,
        "employee_name": employee.full_name,
        "position": assignment.position.title if assignment else "",
        "campus": employee.campus.name,
        "leave_type": instance.leave_type.name,
        "leave_type_code": instance.leave_type.code,
        "paid": instance.leave_type.is_paid,
        "from_date": instance.from_date.isoformat(),
        "to_date": instance.to_date.isoformat(),
        "return_date": next_working_day(instance.to_date).isoformat(),
        "days": str(instance.days),
        "days_beyond": str(instance.days_beyond),
        "evidence": instance.leave_type.evidence_name if instance.evidence_id else "",
        "approvals": [
            {"step": d.get_step_display(), "name": d.actor_name, "decided_at": d.decided_at.isoformat()}
            for d in instance.decisions.filter(outcome="approved")
        ],
        "balances": [
            {
                "code": row["code"],
                "name": row["name"],
                "remaining": str(max(row["balance"], ZERO)),
                "pending": str(row["pending"]),
            }
            for row in balances_for(employee)
            if row["limited"]
        ],
    }
    instance.receipt = receipt
    instance.save(update_fields=["receipt"])
    return receipt


def remaining_line(receipt: dict) -> str:
    """The balances in one sentence for a notification: Annual leave 5 days, Sick leave 12 days."""
    return ", ".join(f"{row['name']} {in_days(Decimal(row['remaining']))}" for row in receipt["balances"])
