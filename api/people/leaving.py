"""Leaving the School (item 1.12) and what is owed on leaving (item 1.14).

The rules follow the Termination of Employment and Severance Pay Act 1997 as the Ministry of Labour summarises
it (labour.gov.gy, "Termination and severance", 2024):

- During probation either side may end the employment at any time, without notice (section 9).
- Otherwise notice is at least two weeks for someone employed less than a year and one month for a year or
  more; an employee who resigns owes the same notice, and a contract may ask for longer.
- Someone whose employment ends by redundancy, or by the employer with notice, after a year or more of
  continuous service, is owed at least one week's wages for each of the first five years, two weeks' for each
  year from the sixth to the tenth, and three weeks' for each year after the tenth, up to fifty-two weeks.
- Leave not taken is paid, and notice not given by the employer is paid in lieu.

The figures are the statutory minimum on the basic salary of the grade and step paid on the last day. A
collective agreement or GSA's conditions of service may give more; Finance adds allowances and pays.
"""

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from audit.services import record, snapshot
from iam.models import Role
from notifications.services import notify, users_with_role
from org.serializers import grade_name
from people.models import Assignment, CareerEvent, Employee, Separation

Reason = Separation.Reason
State = Separation.State
WEEKS_PER_YEAR = Decimal(52)
WORKING_DAYS_PER_WEEK = Decimal(5)  # the 40-hour week over five days (Labour Act, Ministry of Labour)
CENT = Decimal("0.01")
GIVEN_BY_EMPLOYEE = (Reason.RESIGNATION,)
GIVEN_BY_SCHOOL = (Reason.NOTICE, Reason.REDUNDANCY)
SEVERANCE_REASONS = (Reason.NOTICE, Reason.REDUNDANCY)
CONFLICTS = frozenset({"already_leaving", "left"})


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _day(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def add_month(day: date) -> date:
    """The same day a month later, or the last day of that month when it is shorter."""
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def service_start(employee: Employee) -> date | None:
    """The start of continuous service: the first substantive appointment on record."""
    first = employee.assignments.filter(is_acting=False).order_by("start_date").first()
    return first.start_date if first else None


def completed_years(start: date, until: date) -> int:
    years = until.year - start.year - ((until.month, until.day) < (start.month, start.day))
    return max(years, 0)


def severance_weeks(years: int) -> int:
    """Weeks of wages owed for completed years of continuous service; nothing before one year, at most 52."""
    if years < 1:
        return 0
    weeks = min(years, 5) + 2 * max(0, min(years, 10) - 5) + 3 * max(0, years - 10)
    return min(weeks, 52)


def _working_assignment(employee: Employee, on: date) -> Assignment | None:
    """The substantive appointment held on a day: the current one, or for a leaver the last they held."""
    current = employee.current_assignment
    if current is not None:
        return current
    return (
        employee.assignments.filter(is_acting=False, start_date__lte=on)
        .select_related("position__grade__scale", "grade__scale")
        .order_by("-start_date")
        .first()
    )


def notice(employee: Employee, reason: str, notice_given_on: date | None, last_day: date) -> dict:
    """What notice the law and the contract ask for, and whether the last day leaves enough of it."""
    from people.services import current_contract

    if reason in GIVEN_BY_EMPLOYEE:
        who = "employee"
    elif reason in GIVEN_BY_SCHOOL:
        who = "school"
    else:
        return {"needed": False, "why": "No notice is needed when employment ends this way."}
    assignment = _working_assignment(employee, last_day)
    probation = assignment.probation_end if assignment and not assignment.confirmed_on else None
    given = notice_given_on or last_day
    if probation is not None and given <= probation:
        return {"needed": False, "why": "During probation either side may end the employment without notice."}
    start = service_start(employee) or given
    under_a_year = completed_years(start, given) < 1
    statutory = given + timedelta(days=14) if under_a_year else add_month(given)
    required = statutory
    contract = current_contract(employee)
    contract_days = contract.notice_period_days if contract and contract.notice_period_days else None
    if contract_days and given + timedelta(days=contract_days) > required:
        required = given + timedelta(days=contract_days)
    short = max((required - last_day).days, 0)
    rule = "two weeks, employed under a year" if under_a_year else "one month, employed a year or more"
    if contract_days and required > statutory:
        rule = f"{contract_days} days, as the contract says (the law asks for {rule.split(',')[0]})"
    return {
        "needed": True,
        "given_by": who,
        "given_on": given.isoformat(),
        "rule": rule,
        "full_notice_ends": required.isoformat(),
        "short_by_days": short,
    }


def _money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def settlement(separation: Separation) -> dict:
    """The statutory figures owed on leaving: leave not taken, notice not given, severance."""
    from leave.models import LeaveType
    from leave.services import balance

    employee, last = separation.employee, separation.last_day
    assignment = _working_assignment(employee, last)
    if assignment is None:
        return {
            "lines": [],
            "total": "0.00",
            "notes": ["No appointment is on record, so nothing can be worked out."],
        }
    grade = assignment.pay_grade
    monthly = grade.amount_on(last)
    weekly = monthly * 12 / WEEKS_PER_YEAR
    daily = weekly / WORKING_DAYS_PER_WEEK
    start = service_start(employee) or assignment.start_date
    years = completed_years(start, last)
    lines = []

    annual = LeaveType.objects.filter(code="ANN").first()
    days = balance(employee, annual, as_of=last) if annual else Decimal(0)
    if days > 0:
        lines.append(
            {
                "key": "leave",
                "label": f"Annual leave not taken: {days.normalize():f} days",
                "amount": _money(days * daily),
            }
        )
    owed = notice(employee, separation.reason, separation.notice_given_on, last)
    if owed.get("needed") and owed["given_by"] == "school" and owed["short_by_days"] > 0:
        short = owed["short_by_days"]
        lines.append(
            {
                "key": "notice",
                "label": f"Pay in lieu of notice: {short} days short of {owed['rule'].split(',')[0]}",
                "amount": _money(Decimal(short) * weekly / 7),
            }
        )
    if separation.reason in SEVERANCE_REASONS:
        weeks = severance_weeks(years)
        if weeks:
            lines.append(
                {
                    "key": "severance",
                    "label": f"Severance: {weeks} weeks' wages for {years} completed years of service",
                    "amount": _money(weeks * weekly),
                }
            )
    total = sum((Decimal(line["amount"]) for line in lines), Decimal(0))
    return {
        "last_day": last.isoformat(),
        "grade": grade_name(grade),
        "monthly": _money(monthly),
        "weekly": _money(weekly),
        "daily": _money(daily),
        "service_from": start.isoformat(),
        "completed_years": years,
        "lines": lines,
        "total": _money(total),
        "notes": [
            "The statutory minimum on the basic salary of the grade and step paid on the last day. "
            "A collective agreement or GSA's conditions of service may give more; "
            "Finance adds allowances and pays.",
            "Severance is owed when employment ends by redundancy or by the School with notice, "
            "after a year or more of continuous service: one week's wages for each of the first five years, "
            "two weeks' for each of the sixth to the tenth, three weeks' for each year after, "
            "up to fifty-two weeks.",
        ],
    }


def record_leaving(
    request,
    *,
    employee: Employee,
    reason: str,
    last_day: date,
    note: str,
    notice_given_on: date | None = None,
) -> Separation:
    name = employee.full_name
    if employee.status == Employee.Status.SEPARATED:
        raise Refused("left", f"{name} has already left the School.")
    if Separation.objects.filter(employee=employee, state=State.LEAVING).exists():
        raise Refused(
            "already_leaving", f"{name}'s leaving is already recorded. Withdraw it to record another."
        )
    if notice_given_on is not None and notice_given_on > last_day:
        raise Refused("notice_after", "Notice is given before the last day.")
    assignment = _working_assignment(employee, last_day)
    if assignment is None:
        raise Refused("no_post", f"{name} holds no appointment to end.")
    if last_day < assignment.start_date:
        raise Refused(
            "too_early", f"The last day is after {_day(assignment.start_date)}, when the appointment began."
        )
    needs_notice = reason in GIVEN_BY_EMPLOYEE + GIVEN_BY_SCHOOL
    if needs_notice and notice_given_on is None:
        raise Refused("notice_date", "Say when notice was given.")
    if reason == Reason.PROBATION and not (
        assignment.probation_end and not assignment.confirmed_on and last_day <= assignment.probation_end
    ):
        raise Refused("not_in_probation", f"{name} is not in probation on {_day(last_day)}.")
    separation = Separation(
        employee=employee,
        reason=reason,
        notice_given_on=notice_given_on,
        last_day=last_day,
        note=note.strip(),
        created_by=request.user,
        updated_by=request.user,
    )
    with transaction.atomic():
        separation.save()
        record(request, "leaving_recorded", separation, after=snapshot(separation), reason=separation.note)
        if last_day < timezone.localdate():
            complete(request, separation)
    return separation


def withdraw(request, separation: Separation, reason: str) -> Separation:
    if separation.state != State.LEAVING:
        raise Refused("not_leaving", "Only a leaving still to happen can be withdrawn.")
    with transaction.atomic():
        before = snapshot(separation)
        separation.state = State.WITHDRAWN
        separation.withdrawn_reason = reason.strip()
        separation.updated_by = request.user
        separation.save(update_fields=["state", "withdrawn_reason", "updated_by", "updated_at"])
        record(
            request, "leaving_withdrawn", separation, before=before, after=snapshot(separation), reason=reason
        )
    return separation


def complete(request, separation: Separation) -> None:
    """The person has left: their status, appointments, scheduled changes and account follow."""
    from iam.accounts import close_sessions

    actor = getattr(request, "user", None) if request is not None else None
    employee, last = separation.employee, separation.last_day
    why = f"Left the School on {_day(last)}: {separation.get_reason_display().lower()}"
    figures = settlement(separation)  # while the appointment is still current
    before = snapshot(employee)
    employee.status = Employee.Status.SEPARATED
    employee.updated_by = actor
    employee.save(update_fields=["status", "updated_by", "updated_at"])
    record(request, "update", employee, before=before, after=snapshot(employee), reason=why)
    for assignment in employee.assignments.filter(status=Assignment.Status.ACTIVE):
        before = snapshot(assignment)
        if assignment.end_date is None or assignment.end_date > last:
            assignment.end_date = max(last, assignment.start_date)
        assignment.status = Assignment.Status.ENDED
        assignment.updated_by = actor
        assignment.save(update_fields=["end_date", "status", "updated_by", "updated_at"])
        record(request, "update", assignment, before=before, after=snapshot(assignment), reason=why)
    for event in CareerEvent.objects.filter(
        employee=employee, state__in=(CareerEvent.State.SCHEDULED, CareerEvent.State.BLOCKED)
    ):
        before = snapshot(event)
        event.state = CareerEvent.State.CANCELLED
        event.save(update_fields=["state", "updated_at"])
        record(request, "career_cancelled", event, before=before, after=snapshot(event), reason=why)
    user = employee.user
    if user is not None and user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])
        ended = close_sessions(user)
        record(request, "account_deactivated", user, after={"sessions_ended": ended}, reason=why)
    separation.state = State.LEFT
    separation.completed_at = timezone.now()
    separation.settlement = figures
    separation.updated_by = actor
    separation.save(update_fields=["state", "completed_at", "settlement", "updated_by", "updated_at"])
    record(request, "leaving_completed", separation, after={"total": figures["total"]}, reason=why)


def complete_due(today: date) -> int:
    """The night after each last day: everyone whose last day has passed has left."""
    done = 0
    for separation in Separation.objects.filter(state=State.LEAVING, last_day__lt=today).select_related(
        "employee", "employee__campus", "employee__user"
    ):
        with transaction.atomic():
            complete(None, separation)
        notify(
            users_with_role(Role.HR_OFFICER, campus=separation.employee.campus),
            title=f"{separation.employee.full_name} has left: the settlement figures are ready",
            body=f"Last day {_day(separation.last_day)}. Their account is switched off.",
            link=f"/people/{separation.employee_id}",
            dedupe_key=f"left:{separation.pk}",
        )
        done += 1
    return done


def letter_answers(separation: Separation) -> dict[str, str]:
    return {"last_day": separation.last_day.isoformat()}
