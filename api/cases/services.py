"""The rules of a case (item 1.15): who sees it, who may act on it, and the fair steps before a decision.

Audit rows for cases are events that name the case and its state, never the allegation, the reasons or the
person's name, and they carry no subject, so they never appear in the person's file history.
"""

import calendar
from datetime import date, timedelta

from django.db import connection, transaction
from django.utils import timezone

from audit.services import record_event
from cases.models import Case, CaseEntry, CaseOfficer
from iam.models import Role
from iam.services import has_role
from notifications.services import notify

Kind = Case.Kind
Outcome = Case.Outcome
REFERENCE_LOCK = 1_015_001
DISCIPLINE_OUTCOMES = {
    Outcome.NO_ACTION,
    Outcome.COUNSELLING,
    Outcome.VERBAL_WARNING,
    Outcome.WRITTEN_WARNING,
    Outcome.FINAL_WARNING,
    Outcome.SUSPENSION,
    Outcome.DISMISSAL,
    Outcome.WITHDRAWN,
}
GRIEVANCE_OUTCOMES = {Outcome.UPHELD, Outcome.PARTLY_UPHELD, Outcome.NOT_UPHELD, Outcome.WITHDRAWN}
# The outcomes that need a hearing first, beyond the allegation in writing.
SERIOUS = {Outcome.FINAL_WARNING, Outcome.SUSPENSION, Outcome.DISMISSAL}
# How long a warning counts, in months: GSA's conditions of service decide; these are common defaults.
WARNING_MONTHS = {Outcome.VERBAL_WARNING: 6, Outcome.WRITTEN_WARNING: 12, Outcome.FINAL_WARNING: 24}
APPEAL_DAYS = 14  # an appeal is lodged within this many days of the decision (GSA to confirm)
CONFLICTS = frozenset({"not_open", "not_decided", "not_under_appeal", "named"})


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def visible(user):
    """The cases a person may see: every one for the HR Manager, otherwise those they are named on."""
    cases = Case.objects.exclude(employee__user=user).select_related(
        "employee", "decided_by", "appeal_decided_by"
    )
    if has_role(user, Role.HR_MANAGER):
        return cases
    return cases.filter(officers__user=user).distinct()


def may_act(user, case: Case) -> bool:
    return has_role(user, Role.HR_MANAGER) or case.officers.filter(user=user).exists()


def _audit(request, action: str, case: Case, **after) -> None:
    record_event(request, action, "cases.case", after={"case": case.pk, "reference": case.reference, **after})


def _months_after(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _next_reference(kind: str, year: int) -> str:
    prefix = f"{'DC' if kind == Kind.DISCIPLINE else 'GR'}-{year}-"
    last = (
        Case.objects.filter(reference__startswith=prefix)
        .order_by("-id")
        .values_list("reference", flat=True)
        .first()
    )
    number = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:03d}"


def open_case(request, *, kind: str, employee, summary: str, opened_on: date) -> Case:
    if employee.user_id is not None and employee.user_id == request.user.pk:
        raise Refused("own", "Nobody handles a case about themselves.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [REFERENCE_LOCK])
        case = Case.objects.create(
            reference=_next_reference(kind, opened_on.year),
            kind=kind,
            employee=employee,
            summary=summary.strip(),
            opened_on=opened_on,
            created_by=request.user,
            updated_by=request.user,
        )
        CaseOfficer.objects.create(
            case=case, user=request.user, part="Opened the case", named_by=request.user
        )
        _audit(request, "case_opened", case, kind=kind, state=case.state)
    return case


def name_officer(request, case: Case, user, part: str) -> CaseOfficer:
    if not may_act(request.user, case):
        raise Refused("not_named", "Only the HR Manager, or someone named on the case, names others.")
    if case.employee.user_id == user.pk:
        raise Refused("own", "Nobody is named on a case about themselves.")
    if not user.is_active:
        raise Refused("inactive", "That account is switched off.")
    if case.officers.filter(user=user).exists():
        raise Refused("named", "They are already named on this case.")
    with transaction.atomic():
        officer = CaseOfficer.objects.create(case=case, user=user, part=part.strip(), named_by=request.user)
        _audit(request, "case_officer_named", case, officer=user.pk, part=officer.part)
    notify(
        [user],
        title=f"You are named on case {case.reference}",
        body=f"As {officer.part.lower()}. Its papers are under Cases.",
        link=f"/cases/{case.pk}",
        dedupe_key=f"case:{case.pk}:officer:{user.pk}",
    )
    return officer


def add_entry(request, case: Case, *, kind: str, on: date, text: str) -> CaseEntry:
    if case.state == Case.State.CLOSED:
        raise Refused("closed", "The case is closed.")
    with transaction.atomic():
        entry = CaseEntry.objects.create(
            case=case, kind=kind, on=on, text=text.strip(), created_by=request.user, updated_by=request.user
        )
        _audit(request, "case_entry", case, entry=kind)
    return entry


def fair_steps(case: Case) -> dict[str, bool]:
    kinds = set(case.entries.values_list("kind", flat=True))
    return {
        "allegation": CaseEntry.Kind.ALLEGATION in kinds,
        "answered": bool(kinds & {CaseEntry.Kind.RESPONSE, CaseEntry.Kind.HEARING}),
    }


def decide(request, case: Case, *, outcome: str, reasons: str, decided_on: date) -> Case:
    if case.state != Case.State.OPEN:
        raise Refused("not_open", "Only an open case is decided.")
    allowed = DISCIPLINE_OUTCOMES if case.kind == Kind.DISCIPLINE else GRIEVANCE_OUTCOMES
    if outcome not in allowed:
        raise Refused("wrong_outcome", f"That is not an outcome of a {case.get_kind_display().lower()} case.")
    steps = fair_steps(case)
    if case.kind == Kind.DISCIPLINE and outcome not in (Outcome.NO_ACTION, Outcome.WITHDRAWN):
        if not steps["allegation"]:
            raise Refused("unfair", "Before any action, the allegation is put to the employee in writing.")
        if outcome in SERIOUS and not steps["answered"]:
            raise Refused(
                "unfair",
                f"Before a {Outcome(outcome).label.lower()}, the employee is heard: record their response, "
                "or the hearing.",
            )
    with transaction.atomic():
        case.outcome = outcome
        case.outcome_reasons = reasons.strip()
        case.decided_on = decided_on
        case.decided_by = request.user
        case.lapses_on = (
            _months_after(decided_on, WARNING_MONTHS[outcome]) if outcome in WARNING_MONTHS else None
        )
        case.state = Case.State.DECIDED
        case.updated_by = request.user
        case.save()
        _audit(request, "case_decided", case, outcome=outcome, state=case.state)
    return case


def lodge_appeal(request, case: Case, *, lodged_on: date, grounds: str) -> Case:
    if case.state != Case.State.DECIDED:
        raise Refused("not_decided", "Only a decided case is appealed.")
    if lodged_on > case.decided_on + timedelta(days=APPEAL_DAYS):
        raise Refused("late", f"An appeal is lodged within {APPEAL_DAYS} days of the decision.")
    with transaction.atomic():
        case.appeal_lodged_on = lodged_on
        case.appeal_grounds = grounds.strip()
        case.state = Case.State.APPEAL
        case.updated_by = request.user
        case.save()
        _audit(request, "case_appealed", case, state=case.state)
    return case


def decide_appeal(request, case: Case, *, outcome: str, reasons: str, decided_on: date) -> Case:
    if case.state != Case.State.APPEAL:
        raise Refused("not_under_appeal", "Only a case under appeal has its appeal decided.")
    if case.decided_by_id == request.user.pk:
        raise Refused("not_independent", "An appeal is heard by someone who did not make the decision.")
    with transaction.atomic():
        case.appeal_outcome = outcome
        case.appeal_reasons = reasons.strip()
        case.appeal_decided_on = decided_on
        case.appeal_decided_by = request.user
        case.state = Case.State.DECIDED
        case.updated_by = request.user
        case.save()
        _audit(request, "case_appeal_decided", case, appeal_outcome=outcome, state=case.state)
    return case


def close(request, case: Case) -> Case:
    if case.state != Case.State.DECIDED:
        raise Refused("not_decided", "A case is closed once it is decided, and any appeal heard.")
    with transaction.atomic():
        case.state = Case.State.CLOSED
        case.closed_on = timezone.localdate()
        case.updated_by = request.user
        case.save()
        _audit(request, "case_closed", case, state=case.state)
    return case
