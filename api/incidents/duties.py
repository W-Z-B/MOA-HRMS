"""Which written notices the Occupational Safety and Health Act requires for an incident, and by when.

Notices are about workers, and GSA gives them for its own staff: a contractor's employer notifies for its
own workers. Whether a student on practical work counts as a worker is for GSA to confirm; until then an
injury to a student is recorded but raises no notice. A dangerous occurrence away from an industrial
establishment, such as on a farm, needs none either (section 74), though nothing stops HR sending one.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from incidents.models import Incident, Notice, Person

Duty = Notice.Duty
Recipient = Notice.Recipient

SECTION = {
    Duty.DEATH: "69(1)(a)",
    Duty.DISABLEMENT: "69(1)(b)",
    Duty.LATER_DEATH: "69(2)",
    Duty.RECOVERED: "69(3)",
    Duty.DISEASE: "70",
    Duty.DANGEROUS: "74",
}
DISABLEMENT_DAYS = 4  # within four days of an accident keeping a worker from full wages for more than a day
RECOVERED_DAYS = 14  # within two weeks of the day the disablement ended
DANGEROUS_DAYS = 2  # within two days of a dangerous occurrence
NIS_BENEFIT_AFTER_DAYS = 3  # NIS pays injury benefit when the incapacity lasts more than three days


@dataclass
class Due:
    duty: str
    person: Person | None
    due_on: date
    recipients: tuple[str, ...]
    sent: dict[str, Notice] = field(default_factory=dict)

    @property
    def section(self) -> str:
        return SECTION[self.duty]

    @property
    def unsent(self) -> list[str]:
        return [r for r in self.recipients if r not in self.sent]

    def overdue(self, today: date) -> bool:
        return bool(self.unsent) and today > self.due_on


def day_of(incident: Incident) -> date:
    return timezone.localtime(incident.occurred_at).date()


def days_off(person: Person, today: date) -> int:
    """Days kept from full wages so far: to the day back at work, or to today while still off."""
    if person.off_work_from is None:
        return 0
    return max(((person.back_at_work_on or today) - person.off_work_from).days, 0)


def told() -> tuple[str, ...]:
    """The Authority, and the committee, representative or union unless GSA has none (SAFETY_TELL_WORKERS)."""
    if settings.SAFETY_TELL_WORKERS:
        return (Recipient.AUTHORITY, Recipient.WORKERS)
    return (Recipient.AUTHORITY,)


def duties(incident: Incident, today: date | None = None) -> list[Due]:
    today = today or timezone.localdate()
    day = day_of(incident)
    notices = list(incident.notices.all())
    found: list[Due] = []
    for person in incident.people.all():
        if person.who != Person.Who.STAFF:
            continue
        if incident.kind == Incident.Kind.DISEASE:
            extra = (Recipient.SANITARY,) + ((Recipient.MEDICAL,) if incident.industrial else ())
            found.append(Due(Duty.DISEASE, person, day, told() + extra))
            continue
        within_four_days = day + timedelta(days=DISABLEMENT_DAYS)
        if person.died_on is not None:
            # A death after the disablement was notified is a later death (69(2)); otherwise the accident
            # killed the worker (69(1)(a)). Either way the notice is due forthwith: the same day.
            notified = any(
                n.person_id == person.pk and n.duty == Duty.DISABLEMENT and n.sent_on <= person.died_on
                for n in notices
            )
            if notified:
                found.append(Due(Duty.DISABLEMENT, person, within_four_days, told()))
                found.append(Due(Duty.LATER_DEATH, person, person.died_on, told()))
            else:
                found.append(Due(Duty.DEATH, person, person.died_on, told()))
        elif days_off(person, today) > 1:
            found.append(Due(Duty.DISABLEMENT, person, within_four_days, told()))
            if person.back_at_work_on is not None:
                ended = person.back_at_work_on + timedelta(days=RECOVERED_DAYS)
                found.append(Due(Duty.RECOVERED, person, ended, told()))
    if incident.kind == Incident.Kind.DANGEROUS and incident.industrial and not found:
        found.append(Due(Duty.DANGEROUS, None, day + timedelta(days=DANGEROUS_DAYS), told()))
    for due in found:
        about = due.person.pk if due.person else None
        due.sent = {n.recipient: n for n in notices if n.duty == due.duty and n.person_id == about}
    return found


def outstanding(incident: Incident, today: date | None = None, *, health: bool = True) -> list[str]:
    """What is left to do before the incident can be closed, in words. Without `health` it leaves out who is
    still off work and their NIS claim, which are for those who keep the register."""
    today = today or timezone.localdate()
    left = []
    for due in duties(incident, today):
        names = " and ".join(Recipient(r).label[0].lower() + Recipient(r).label[1:] for r in due.unsent)
        if names:
            whom = f" ({due.person.display_name})" if due.person else ""
            what = Duty(due.duty).label.lower()
            left.append(f"Send notice of {what}{whom} to {names} by {due.due_on:%d/%m/%Y}")
    for person in incident.people.all() if health else ():
        if person.who != Person.Who.STAFF:
            continue
        if person.off_work_from and not person.back_at_work_on and not person.died_on:
            left.append(f"Record the day {person.display_name} is back at work")
        if person.nis_form_on is None and days_off(person, today) > NIS_BENEFIT_AFTER_DAYS:
            left.append(
                f"Give {person.display_name} the NIS notice of accident (Form IB1), for injury benefit"
            )
    for action in incident.actions.all():
        if action.done_on is None:
            left.append(f"Finish the action: {action.what}")
    if not incident.cause.strip():
        left.append("Record what the investigation found")
    return left
