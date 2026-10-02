"""The rules of the incident register (item 1.16): reporting, the record HR keeps, notices, actions, closing.

Audit rows name the incident, its state and which fields changed, never an injury or a person's name, and
carry no subject, so a person's file history shows nothing of their health.
"""

from datetime import date

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from audit.services import record_event
from iam.models import Role
from incidents.duties import day_of, duties, outstanding
from incidents.models import Action, Incident, Notice, Person
from notifications.services import notify, users_with_role

REFERENCE_LOCK = 1_016_001
CONFLICTS = frozenset({"closed", "recorded", "named", "done"})
PERSON_FIELDS = (
    "injury",
    "treatment",
    "off_work_from",
    "back_at_work_on",
    "died_on",
    "nis_form_on",
)
CORRECTABLE = (
    "kind",
    "occurred_at",
    "org_unit",
    "place",
    "industrial",
    "description",
    "immediate_action",
)


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _audit(request, event: str, incident: Incident, **after) -> None:
    after = {"incident": incident.pk, "reference": incident.reference, "state": incident.state, **after}
    record_event(request, event, "incidents.incident", after=after)


def _next_reference(year: int) -> str:
    prefix = f"IN-{year}-"
    last = (
        Incident.objects.filter(reference__startswith=prefix)
        .order_by("-id")
        .values_list("reference", flat=True)
        .first()
    )
    number = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:03d}"


def keepers(campus) -> list:
    """Who keeps the register for a campus: its HR officers, and the HR Manager."""
    officers = users_with_role(Role.HR_OFFICER, campus=campus)
    return list({u.pk: u for u in [*officers, *users_with_role(Role.HR_MANAGER)]}.values())


def _unit_on_campus(org_unit, campus) -> None:
    if org_unit is not None and org_unit.campus_id != campus.pk:
        raise Refused("other_campus", "That unit is on another campus.")


def _working(request, incident: Incident) -> None:
    """Any record HR adds starts the investigation of a report."""
    if incident.state == Incident.State.REPORTED:
        incident.state = Incident.State.INVESTIGATING
    incident.updated_by = request.user
    incident.save()


def _not_closed(incident: Incident) -> None:
    if incident.state == Incident.State.CLOSED:
        raise Refused("closed", "The incident is closed.")


def report(
    request,
    *,
    kind: str,
    occurred_at,
    campus,
    place: str,
    description: str,
    org_unit=None,
    industrial: bool = False,
    immediate_action: str = "",
    hurt: bool = False,
    injury: str = "",
) -> Incident:
    if occurred_at > timezone.now():
        raise Refused("future", "An incident is reported once it has happened.")
    _unit_on_campus(org_unit, campus)
    reporter = getattr(request.user, "employee", None)
    if hurt and reporter is None:
        raise Refused("no_record", "Say in the description who was hurt; HR records them.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [REFERENCE_LOCK])
        incident = Incident.objects.create(
            reference=_next_reference(timezone.localtime(occurred_at).year),
            kind=kind,
            occurred_at=occurred_at,
            campus=campus,
            org_unit=org_unit,
            place=place.strip(),
            industrial=industrial,
            description=description.strip(),
            immediate_action=immediate_action.strip(),
            created_by=request.user,
            updated_by=request.user,
        )
        if hurt:
            Person.objects.create(
                incident=incident,
                who=Person.Who.STAFF,
                employee=reporter,
                injury=injury.strip(),
                created_by=request.user,
                updated_by=request.user,
            )
        _audit(request, "incident_reported", incident, kind=kind)
    notify(
        [u for u in keepers(campus) if u.pk != request.user.pk],
        title=f"{incident.get_kind_display()} reported at {campus.name}: {incident.reference}",
        body=f"At {incident.place}. Look into it under Incidents.",
        link=f"/incidents/{incident.pk}",
        kind="alert",
        dedupe_key=f"incident:{incident.pk}:reported",
    )
    return incident


def correct(request, incident: Incident, **fields) -> Incident:
    _not_closed(incident)
    _unit_on_campus(fields.get("org_unit", incident.org_unit), incident.campus)
    if "occurred_at" in fields and fields["occurred_at"] > timezone.now():
        raise Refused("future", "An incident is reported once it has happened.")
    changed = sorted(k for k, v in fields.items() if k in CORRECTABLE and getattr(incident, k) != v)
    with transaction.atomic():
        for key in changed:
            setattr(incident, key, fields[key])
        _working(request, incident)
        _audit(request, "incident_corrected", incident, fields=changed)
    return incident


def _check_dates(incident: Incident, values: dict) -> None:
    today = timezone.localdate()
    day = day_of(incident)
    for key in ("off_work_from", "back_at_work_on", "died_on", "nis_form_on"):
        value = values.get(key)
        if value is None:
            continue
        if value > today:
            raise Refused("future", "Record what has happened, not what is expected.")
        if value < day:
            raise Refused("before", "That is before the incident.")
    off, back = values.get("off_work_from"), values.get("back_at_work_on")
    if back is not None and (off is None or back <= off):
        raise Refused("dates", "The day back at work comes after the first day off.")


def add_person(request, incident: Incident, *, who: str, employee=None, name: str = "", **details) -> Person:
    _not_closed(incident)
    if who == Person.Who.STAFF:
        if employee is None:
            raise Refused("who", "Choose the member of staff.")
        name = ""
        if incident.people.filter(employee=employee).exists():
            raise Refused("named", "They are already recorded on this incident.")
    else:
        employee = None
        if not name.strip():
            raise Refused("who", "Give their name.")
    values = {key: details.get(key) for key in PERSON_FIELDS}
    values["injury"] = (values["injury"] or "").strip()
    values["treatment"] = values["treatment"] or ""
    _check_dates(incident, values)
    with transaction.atomic():
        person = Person.objects.create(
            incident=incident,
            who=who,
            employee=employee,
            name=name.strip(),
            created_by=request.user,
            updated_by=request.user,
            **values,
        )
        _working(request, incident)
        _audit(request, "incident_person_added", incident, person=person.pk, who=who)
    return person


def change_person(request, incident: Incident, person: Person, **details) -> Person:
    """Correct what is known of someone hurt. A death or a return to work after closing reopens the incident:
    it may need a notice."""
    values = {key: details[key] for key in PERSON_FIELDS if key in details}
    if "injury" in values:
        values["injury"] = (values["injury"] or "").strip()
    if "treatment" in values:
        values["treatment"] = values["treatment"] or ""
    merged = {key: getattr(person, key) for key in PERSON_FIELDS} | values
    _check_dates(incident, merged)
    changed = sorted(key for key, value in values.items() if getattr(person, key) != value)
    with transaction.atomic():
        if incident.state == Incident.State.CLOSED and changed:
            incident.state = Incident.State.INVESTIGATING
            incident.closed_on = None
            incident.closed_by = None
            _audit(request, "incident_reopened", incident, person=person.pk)
        for key in changed:
            setattr(person, key, values[key])
        person.updated_by = request.user
        person.save()
        _working(request, incident)
        _audit(request, "incident_person_changed", incident, person=person.pk, fields=changed)
    if "died_on" in changed and person.died_on is not None:
        notify(
            keepers(incident.campus),
            title=f"A death to notify forthwith: {incident.reference}",
            body="The Occupational Safety and Health Act asks for written notice at once. See Incidents.",
            link=f"/incidents/{incident.pk}",
            kind="alert",
            dedupe_key=f"incident:{incident.pk}:death:{person.pk}",
        )
    return person


def record_notice(
    request, incident: Incident, *, duty: str, recipient: str, sent_on: date, how: str, person=None, **extra
) -> Notice:
    _not_closed(incident)
    about = person.pk if person else None
    match = [d for d in duties(incident) if d.duty == duty and (d.person.pk if d.person else None) == about]
    if not match or recipient not in match[0].recipients:
        raise Refused("not_due", "That notice is not one this incident needs.")
    due = match[0]
    if recipient in due.sent:
        raise Refused("recorded", "That notice is already recorded.")
    if sent_on > timezone.localdate():
        raise Refused("future", "A notice is recorded once it is sent.")
    if sent_on < day_of(incident):
        raise Refused("before", "That is before the incident.")
    with transaction.atomic():
        notice = Notice.objects.create(
            incident=incident,
            person=person,
            duty=duty,
            recipient=recipient,
            sent_on=sent_on,
            how=how.strip(),
            their_reference=(extra.get("their_reference") or "").strip(),
            created_by=request.user,
            updated_by=request.user,
        )
        _working(request, incident)
        _audit(
            request, "incident_notice", incident, duty=duty, recipient=recipient, late=sent_on > due.due_on
        )
    return notice


def investigate(request, incident: Incident, *, cause: str, investigated_on: date) -> Incident:
    _not_closed(incident)
    if investigated_on > timezone.localdate():
        raise Refused("future", "Record what has happened, not what is expected.")
    with transaction.atomic():
        incident.cause = cause.strip()
        incident.investigated_on = investigated_on
        incident.investigated_by = request.user
        _working(request, incident)
        _audit(request, "incident_investigated", incident)
    return incident


def add_action(request, incident: Incident, *, what: str, owner, due_on: date) -> Action:
    _not_closed(incident)
    with transaction.atomic():
        action = Action.objects.create(
            incident=incident,
            what=what.strip(),
            owner=owner,
            due_on=due_on,
            created_by=request.user,
            updated_by=request.user,
        )
        _working(request, incident)
        _audit(request, "incident_action", incident, action=action.pk)
    if owner.user_id is not None and owner.user_id != request.user.pk:
        notify(
            [owner.user],
            title=f"A safety action for you, from {incident.reference}",
            body=f"{action.what} By {due_on:%d/%m/%Y}. Mark it done under Incidents.",
            link="/incidents",
            kind="approval",
            dedupe_key=f"incident:action:{action.pk}",
        )
    return action


def finish_action(request, action: Action, *, done_on: date, note: str = "") -> Action:
    incident = action.incident
    _not_closed(incident)
    if action.done_on is not None:
        raise Refused("done", "That action is already done.")
    if done_on > timezone.localdate():
        raise Refused("future", "Record what has happened, not what is expected.")
    with transaction.atomic():
        action.done_on = done_on
        action.done_note = note.strip()
        action.updated_by = request.user
        action.save()
        _audit(request, "incident_action_done", incident, action=action.pk)
    return action


def close(request, incident: Incident) -> Incident:
    _not_closed(incident)
    left = outstanding(incident)
    if left:
        raise Refused("outstanding", "Not yet: " + "; ".join(left) + ".")
    with transaction.atomic():
        incident.state = Incident.State.CLOSED
        incident.closed_on = timezone.localdate()
        incident.closed_by = request.user
        incident.updated_by = request.user
        incident.save()
        _audit(request, "incident_closed", incident)
    return incident


def mine(user):
    """The incidents someone reported, or was hurt in."""
    return (
        Incident.objects.filter(Q(created_by=user) | Q(people__employee__user=user))
        .distinct()
        .select_related("campus")
    )
