"""What a letter can say about a member of staff, read from their record on the day it is written."""

from datetime import date
from decimal import Decimal

from org.serializers import grade_name

# The fields a template may use, with the words the template editor shows for each.
RECORD_FIELDS: dict[str, str] = {
    "today": "The date the letter is issued",
    "reference": "The letter's reference",
    "full_name": "Full name",
    "first_name": "First name",
    "last_name": "Last name",
    "employee_no": "Employee number",
    "address": "Home address",
    "campus": "Campus",
    "campus_address": "Campus address",
    "post_title": "Post held",
    "post_number": "Post number",
    "unit": "Unit",
    "grade": "Grade and step",
    "appointment_type": "Type of appointment",
    "appointed_on": "Date appointed to the post",
    "first_appointed": "Date first employed by the School",
    "probation_end": "End of probation",
    "monthly_salary": "Monthly salary",
    "hours_per_week": "Hours a week",
    "notice_period": "Notice period",
}
# Fields that state pay: a letter that uses one is filed as Confidential at the least.
PAY_FIELDS = frozenset({"monthly_salary"})
# What a template may ask for when a letter is written, beyond the record.
ASK_TYPES = {"text": "Words", "date": "A date"}


def long_date(day: date | None) -> str:
    return f"{day.day} {day:%B %Y}" if day else ""


def money(amount: Decimal | None) -> str:
    return f"G${amount:,.2f}" if amount is not None else ""


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def record_values(employee, on: date) -> dict[str, str]:
    """Every record field for one person on one day, as words. A missing value is an empty string."""
    from people.services import current_contract

    assignment = employee.current_assignment
    position = assignment.position if assignment else None
    contract = current_contract(employee)
    first = employee.assignments.filter(is_acting=False).order_by("start_date").first()
    grade = position.grade if position else None
    days = contract.notice_period_days if contract else None
    values = {
        "today": long_date(on),
        "full_name": employee.full_name,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "employee_no": employee.employee_no,
        "address": employee.address,
        "campus": employee.campus.name,
        "campus_address": employee.campus.address,
        "post_title": position.title if position else "",
        "post_number": position.number if position else "",
        "unit": position.org_unit.name if position else "",
        "grade": grade_name(grade) if grade else "",
        # The plain word, to read "on a permanent appointment": permanent, contract, temporary, sessional...
        "appointment_type": assignment.appointment_type if assignment else "",
        "appointed_on": long_date(assignment.start_date) if assignment else "",
        "first_appointed": long_date(first.start_date) if first else "",
        "probation_end": long_date(assignment.probation_end) if assignment else "",
        "monthly_salary": money(grade.amount_on(on)) if grade else "",
        "hours_per_week": _number(contract.hours_per_week) if contract and contract.hours_per_week else "",
        "notice_period": f"{days} {'day' if days == 1 else 'days'}" if days else "",
    }
    # One line each: a value never adds a line or a paragraph to the letter.
    return {key: " ".join(str(value).split()) for key, value in values.items()}
