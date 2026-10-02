"""Career changes as events (item 1.11): transfer, promotion, increment, acting appointment, confirmation.

Recording a change checks it against the file as it will stand on its date. A change dated today or earlier
takes effect at once; a later one is scheduled, and the nightly task makes it take effect on its day, or holds
it up with the reason and tells HR when it no longer can (the post was filled in the meantime, say).

Appointments change only here. A move to another post ends the appointment the day before and opens the new
one from the day; the employment contract, and the leave written into it, follow the person to the new post.
"""

from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from audit.services import record, snapshot
from iam.models import Role
from iam.services import campus_in_scope
from notifications.services import notify, users_with_role
from org.models import Grade, Position
from org.serializers import grade_name
from people.models import Assignment, CareerEvent, Contract, Employee

Kind = CareerEvent.Kind
State = CareerEvent.State
MOVES = (Kind.TRANSFER, Kind.PROMOTION)
# The letter template each change is written with, by its code (letters.defaults).
LETTER_FOR = {
    Kind.TRANSFER: "transfer",
    Kind.PROMOTION: "promotion",
    Kind.INCREMENT: "increment",
    Kind.ACTING: "acting",
    Kind.CONFIRMATION: "confirmation",
}
CONFLICTS = frozenset({"post_taken", "acting_taken", "pending", "ended"})


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _day(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def _overlapping(qs, start: date, end: date | None, *, start_field: str, end_field: str):
    qs = qs.filter(Q(**{f"{end_field}__isnull": True}) | Q(**{f"{end_field}__gte": start}))
    return qs.filter(**{f"{start_field}__lte": end}) if end is not None else qs


def _post_taken(position: Position, start: date, end: date | None) -> bool:
    """Whether someone holds the post substantively at any time from start (to end), or is due to."""
    held = _overlapping(
        Assignment.objects.filter(position=position, is_acting=False),
        start,
        end,
        start_field="start_date",
        end_field="end_date",
    )
    due = CareerEvent.objects.filter(to_position=position, kind__in=MOVES, state=State.SCHEDULED)
    return held.exists() or due.exists()


def _acting_taken(position: Position, start: date, end: date | None) -> bool:
    """Whether someone acts in the post for part of that time already, or is due to."""
    acting = _overlapping(
        Assignment.objects.filter(position=position, is_acting=True, status=Assignment.Status.ACTIVE),
        start,
        end,
        start_field="start_date",
        end_field="end_date",
    )
    due = _overlapping(
        CareerEvent.objects.filter(to_position=position, kind=Kind.ACTING, state=State.SCHEDULED),
        start,
        end,
        start_field="effective_date",
        end_field="end_date",
    )
    return acting.exists() or due.exists()


def next_step(grade: Grade, on: date) -> Grade | None:
    """The next step up the same grade, as it stands on a day."""
    return (
        Grade.objects.filter(
            scale_id=grade.scale_id, code=grade.code, step=grade.step + 1, effective_from__lte=on
        )
        .order_by("-effective_from")
        .first()
    )


def _carried(pay: Grade, position: Position) -> Grade:
    """A step kept on a move to a post of the same grade; otherwise the new post's own grade."""
    same = pay.scale_id == position.grade.scale_id and pay.code == position.grade.code
    return pay if same else position.grade


def record_change(
    request,
    *,
    employee: Employee,
    kind: str,
    effective_date: date,
    reason: str,
    to_position: Position | None = None,
    end_date: date | None = None,
) -> CareerEvent:
    """Record a change, checked against the file; it takes effect now if its date has come."""
    from privacy import restrictions

    name = employee.full_name
    current = employee.current_assignment
    if employee.status == Employee.Status.SEPARATED:
        raise Refused("left", f"{name} has left the School.")
    held = restrictions.refusal(employee, restrictions.CAREER_PARTS)
    if held:  # no decision is made on an appointment the person contests or objects to (item 1.46)
        raise Refused("restricted", held)
    if kind != Kind.ACTING and current is None:
        raise Refused("no_post", f"{name} holds no post to change.")
    if current is not None and kind != Kind.ACTING and effective_date <= current.start_date:
        raise Refused(
            "too_early",
            f"The change must take effect after {_day(current.start_date)}, "
            "when the present appointment began.",
        )
    if (
        kind != Kind.ACTING
        and CareerEvent.objects.filter(employee=employee, state=State.SCHEDULED)
        .exclude(kind=Kind.ACTING)
        .exists()
    ):
        raise Refused(
            "pending", f"A change for {name} is already scheduled. Let it take effect, or cancel it first."
        )

    event = CareerEvent(
        employee=employee,
        kind=kind,
        effective_date=effective_date,
        end_date=end_date if kind == Kind.ACTING else None,
        reason=reason.strip(),
        from_assignment=current,
        from_grade=current.pay_grade if current else None,
        created_by=request.user,
        updated_by=request.user,
    )
    if kind in MOVES or kind == Kind.ACTING:
        if to_position is None:
            raise Refused("no_position", "Choose the post.")
        if not campus_in_scope(request.user, to_position.org_unit.campus_id):
            raise Refused("scope", "That post is on a campus you do not work with.")
        if to_position.status != Position.Status.APPROVED:
            raise Refused(
                "post_closed",
                f"Post {to_position.number} is {to_position.get_status_display().lower()}: "
                "only an approved post can be filled.",
            )
        if current is not None and to_position.pk == current.position_id:
            raise Refused("same_post", f"{name} already holds post {to_position.number}.")
        event.to_position = to_position
    if kind in MOVES:
        end = current.end_date if current.end_date and current.end_date >= effective_date else None
        if _post_taken(to_position, effective_date, end):
            raise Refused(
                "post_taken", f"Post {to_position.number} is held, or due to be, on {_day(effective_date)}."
            )
        event.to_grade = _carried(current.pay_grade, to_position)
        pay = current.pay_grade
        if kind == Kind.TRANSFER and event.to_grade != pay:
            raise Refused(
                "not_same_grade",
                f"A transfer is to a post on the same grade ({pay.scale.code} {pay.code}); "
                f"post {to_position.number} is on {to_position.grade.scale.code} {to_position.grade.code}. "
                "A post that pays more is a promotion.",
            )
        if kind == Kind.PROMOTION and event.to_grade.amount_on(effective_date) <= pay.amount_on(
            effective_date
        ):
            raise Refused(
                "not_higher", "A promotion is to a post that pays more. Record this one as a transfer."
            )
    elif kind == Kind.INCREMENT:
        step = next_step(current.pay_grade, effective_date)
        if step is None:
            raise Refused(
                "no_step",
                f"{grade_name(current.pay_grade)} has no higher step on {_day(effective_date)}. "
                "Finance adds steps "
                "under Organisation, Salary scales.",
            )
        event.to_grade = step
    elif kind == Kind.ACTING:
        if _acting_taken(to_position, effective_date, end_date):
            raise Refused(
                "acting_taken", f"Someone already acts in post {to_position.number} for part of that time."
            )
        event.to_grade = to_position.grade
    elif kind == Kind.CONFIRMATION and current.confirmed_on:
        raise Refused("confirmed", f"{name} was confirmed in the post on {_day(current.confirmed_on)}.")

    with transaction.atomic():
        event.save()
        record(request, "career_recorded", event, after=snapshot(event), reason=event.reason)
        if effective_date <= timezone.localdate():
            _apply(request, event)
    return event


def _apply(request, event: CareerEvent) -> None:
    """Make the change in the appointments. Raises Refused when the file no longer allows it."""
    actor = getattr(request, "user", None) if request is not None else None
    why = f"{event.get_kind_display()}: {event.reason}"[:300]
    current = event.from_assignment
    if event.kind != Kind.ACTING and (current is None or current.status != Assignment.Status.ACTIVE):
        raise Refused("ended", "The appointment it changes has ended.")

    def save(assignment: Assignment, before: dict | None):
        assignment.updated_by = actor
        assignment.save()
        record(
            request,
            "create" if before is None else "update",
            assignment,
            before=before,
            after=snapshot(assignment),
            reason=why,
        )

    if event.kind in MOVES:
        start = event.effective_date
        new = Assignment(
            employee=event.employee,
            position=event.to_position,
            appointment_type=current.appointment_type,
            start_date=start,
            end_date=current.end_date if current.end_date and current.end_date >= start else None,
            probation_end=current.probation_end
            if current.probation_end and current.probation_end >= start
            else None,
            confirmed_on=current.confirmed_on,
            grade=event.to_grade if event.to_grade_id != event.to_position.grade_id else None,
            created_by=actor,
        )
        before = snapshot(current)
        current.end_date = start - timedelta(days=1)
        current.status = Assignment.Status.ENDED
        save(current, before)
        try:
            with transaction.atomic():
                save(new, None)
        except IntegrityError as exc:
            raise Refused(
                "post_taken", f"Post {event.to_position.number} is held by someone else on {_day(start)}."
            ) from exc
        for contract in Contract.objects.filter(assignment=current):
            moved = snapshot(contract)
            contract.assignment = new
            contract.updated_by = actor
            contract.save(update_fields=["assignment", "updated_by", "updated_at"])
            record(
                request,
                "update",
                contract,
                before=moved,
                after=snapshot(contract),
                reason="The contract, and the leave written into it, follow the person to the new post",
            )
        event.to_assignment = new
    elif event.kind == Kind.INCREMENT:
        before = snapshot(current)
        current.grade = event.to_grade if event.to_grade_id != current.position.grade_id else None
        save(current, before)
        event.to_assignment = current
    elif event.kind == Kind.ACTING:
        acting = Assignment(
            employee=event.employee,
            position=event.to_position,
            appointment_type=current.appointment_type if current else Assignment.AppointmentType.TEMPORARY,
            start_date=event.effective_date,
            end_date=event.end_date,
            is_acting=True,
            created_by=actor,
        )
        save(acting, None)
        event.to_assignment = acting
    elif event.kind == Kind.CONFIRMATION:
        before = snapshot(current)
        current.confirmed_on = event.effective_date
        save(current, before)
        event.to_assignment = current

    event.state = State.APPLIED
    event.applied_at = timezone.now()
    event.problem = ""
    event.updated_by = actor
    event.save(update_fields=["to_assignment", "state", "applied_at", "problem", "updated_by", "updated_at"])
    record(
        request, "career_applied", event, after={"kind": event.kind, "to_assignment": event.to_assignment_id}
    )


def cancel(request, event: CareerEvent, reason: str) -> CareerEvent:
    if event.state not in (State.SCHEDULED, State.BLOCKED):
        raise Refused("not_scheduled", "Only a change still to take effect can be cancelled.")
    with transaction.atomic():
        before = snapshot(event)
        event.state = State.CANCELLED
        event.updated_by = request.user
        event.save(update_fields=["state", "updated_by", "updated_at"])
        record(request, "career_cancelled", event, before=before, after=snapshot(event), reason=reason)
    return event


def apply_due(today: date) -> dict[str, int]:
    """The nightly run: scheduled changes whose day has come, and acting appointments that have ended."""
    counts = {"applied": 0, "held": 0, "acting_ended": 0}
    due = CareerEvent.objects.filter(state=State.SCHEDULED, effective_date__lte=today).select_related(
        "employee", "employee__campus", "from_assignment", "to_position"
    )
    for event in due.order_by("effective_date", "id"):
        try:
            with transaction.atomic():
                _apply(None, event)
            counts["applied"] += 1
        except Refused as exc:
            event.state = State.BLOCKED
            event.problem = exc.detail[:300]
            event.save(update_fields=["state", "problem", "updated_at"])
            record(None, "career_blocked", event, after={"problem": event.problem})
            notify(
                users_with_role(Role.HR_OFFICER, campus=event.employee.campus),
                title=f"A {event.get_kind_display().lower()} did not take effect: {event.employee.full_name}",
                body=event.problem,
                link=f"/people/{event.employee_id}",
                kind="alert",
                dedupe_key=f"career-blocked:{event.pk}",
            )
            counts["held"] += 1
    over = Assignment.objects.filter(is_acting=True, status=Assignment.Status.ACTIVE, end_date__lt=today)
    for acting in over:
        before = snapshot(acting)
        acting.status = Assignment.Status.ENDED
        acting.save(update_fields=["status", "updated_at"])
        record(
            None,
            "update",
            acting,
            before=before,
            after=snapshot(acting),
            reason="The acting appointment ended",
        )
        counts["acting_ended"] += 1
    return counts


def letter_answers(event: CareerEvent) -> dict[str, str]:
    """What a change's letter asks, answered from the change itself; dates as the letter reads them."""
    from letters.fields import long_date, money

    answers = {
        "effective_date": event.effective_date.isoformat(),
        "confirmed_from": event.effective_date.isoformat(),
    }
    old = event.from_assignment
    if old is not None:
        answers["previous_post"] = old.position.title
        answers["previous_unit"] = f"{old.position.org_unit.name}, {old.position.org_unit.campus.name}"
    if event.to_position is not None:
        post, unit = event.to_position, event.to_position.org_unit
        prefix = "acting" if event.kind == Kind.ACTING else "new"
        answers[f"{prefix}_post"] = post.title
        answers[f"{prefix}_unit"] = f"{unit.name}, {unit.campus.name}"
    if event.to_grade is not None:
        answers["new_grade"] = grade_name(event.to_grade)
        answers["new_salary"] = money(event.to_grade.amount_on(event.effective_date))
    if event.kind == Kind.ACTING:
        answers["acting_until"] = long_date(event.end_date) if event.end_date else "further notice"
    return answers
