"""The checks a person used to make by hand before a leave request went forward.

One assessment serves the request form (before saving), the saved draft and the submission, so the
employee is told the same thing at every step.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from leave.models import LeaveRequest, LeaveType
from leave.services import PENDING_STATES, ZERO, available_on, is_eligible, working_days

# A request in one of these states holds its dates: nothing else may overlap it.
HOLDING_STATES = (*PENDING_STATES, LeaveRequest.State.APPROVED)


def in_days(value: Decimal) -> str:
    """2.00 reads as '2 days', 1.00 as '1 day', 3.50 as '3.5 days'."""
    number = f"{value.normalize():f}" if value else "0"
    return f"{number} day" if value == 1 else f"{number} days"


@dataclass
class Problem:
    code: str
    field: str
    detail: str


@dataclass
class Assessment:
    days: Decimal
    available: Decimal
    beyond: Decimal
    evidence_required: bool
    evidence_name: str
    problems: list[Problem] = field(default_factory=list)

    @property
    def remaining(self) -> Decimal:
        return max(self.available - self.days, ZERO)

    def as_dict(self) -> dict:
        return {
            "days": self.days,
            "available": self.available,
            "remaining": self.remaining,
            "beyond": self.beyond,
            "evidence_required": self.evidence_required,
            "evidence_name": self.evidence_name,
            "problems": [vars(p) for p in self.problems],
        }


def assess(
    employee,
    leave_type: LeaveType,
    from_date: date,
    to_date: date,
    *,
    exclude: LeaveRequest | None = None,
    today: date | None = None,
) -> Assessment:
    """Work out the days, what the balance covers, whether evidence is needed, and what blocks it."""
    days = Decimal(working_days(from_date, to_date))
    limited = leave_type.over_balance != LeaveType.OverBalance.ALLOW
    available = available_on(employee, leave_type, from_date, exclude=exclude, today=today)
    beyond = max(days - max(available, ZERO), ZERO) if limited else ZERO
    by_evidence = leave_type.over_balance == LeaveType.OverBalance.EVIDENCE
    result = Assessment(
        days=days,
        available=available,
        beyond=beyond,
        evidence_required=leave_type.requires_evidence or (by_evidence and beyond > 0),
        evidence_name=leave_type.evidence_name,
    )
    if days == 0:
        result.problems.append(
            Problem("no_working_days", "from_date", "The period contains no working days.")
        )
    if not is_eligible(employee, leave_type):
        result.problems.append(
            Problem(
                "not_eligible", "leave_type", f"{leave_type.name} is not open to your type of appointment."
            )
        )
    clash = LeaveRequest.objects.filter(
        employee=employee, state__in=HOLDING_STATES, from_date__lte=to_date, to_date__gte=from_date
    )
    if exclude is not None and exclude.pk:
        clash = clash.exclude(pk=exclude.pk)
    other = clash.select_related("leave_type").first()
    if other is not None:
        result.problems.append(
            Problem(
                "overlap",
                "from_date",
                f"These dates overlap {other.leave_type.name.lower()} from {other.from_date:%d/%m/%Y} "
                f"to {other.to_date:%d/%m/%Y} ({other.get_state_display().lower()}).",
            )
        )
    if beyond > 0 and leave_type.over_balance == LeaveType.OverBalance.REFUSE:
        result.problems.append(
            Problem(
                "over_balance",
                "to_date",
                f"This needs {in_days(days)} of {leave_type.name.lower()} and "
                f"{in_days(max(available, ZERO))} will be available on {from_date:%d/%m/%Y}.",
            )
        )
    return result
