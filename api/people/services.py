"""Look-ups on the employee's place in the School: their manager, their contract and its terms."""

from decimal import Decimal

from django.utils import timezone

from people.models import Contract, Employee

WEEKS_PER_YEAR = Decimal(52)


def manager_of(employee: Employee) -> Employee | None:
    """The head of the employee's unit, or of the nearest unit above it, who can sign in.

    A head is skipped when they are the employee, have left, or have no account: a request sent to
    them would never be decided. None means nobody qualifies and the caller must fall back.
    """
    assignment = employee.current_assignment
    unit = assignment.position.org_unit if assignment else None
    seen: set[int] = set()
    while unit is not None and unit.pk not in seen:
        seen.add(unit.pk)
        head = unit.head
        if (
            head is not None
            and head.pk != employee.pk
            and head.status != Employee.Status.SEPARATED
            and head.user is not None
            and head.user.is_active
        ):
            return head
        unit = unit.parent
    return None


def current_contract(employee: Employee) -> Contract | None:
    assignment = employee.current_assignment
    return assignment.contracts.first() if assignment else None


def hourly_rate(contract: Contract) -> Decimal | None:
    """The contract's own rate, or the grade's monthly amount in force today over the contracted hours."""
    if contract.hourly_rate is not None:
        return contract.hourly_rate
    if not contract.hours_per_week:
        return None
    monthly = contract.assignment.position.grade.amount_on(timezone.localdate())
    return (monthly * 12 / (WEEKS_PER_YEAR * contract.hours_per_week)).quantize(Decimal("0.01"))


def terms_for(employee: Employee) -> dict:
    """What an employee may read about their own appointment and contract."""
    from leave.services import entitlements_for

    assignment = employee.current_assignment
    contract = current_contract(employee)
    manager = manager_of(employee)
    return {
        "employee": employee.id,
        "employee_no": employee.employee_no,
        "name": employee.full_name,
        "campus": employee.campus.name,
        "position": assignment.position.title if assignment else None,
        "unit": assignment.position.org_unit.name if assignment else None,
        "manager": manager.full_name if manager else None,
        "appointment_type": assignment.get_appointment_type_display() if assignment else None,
        "start_date": assignment.start_date if assignment else None,
        "end_date": assignment.end_date if assignment else None,
        "probation_end": assignment.probation_end if assignment else None,
        "contract": None
        if contract is None
        else {
            "id": contract.id,
            "contract_type": contract.get_contract_type_display(),
            "term_months": contract.term_months,
            "signed_on": contract.signed_on,
            "hours_per_week": contract.hours_per_week,
            "hourly_rate": hourly_rate(contract),
            "hourly_rate_is_set": contract.hourly_rate is not None,
            "notice_period_days": contract.notice_period_days,
            "other_terms": contract.other_terms,
        },
        "entitlements": entitlements_for(employee),
    }
