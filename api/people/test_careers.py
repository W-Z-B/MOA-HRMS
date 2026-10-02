"""Item 1.11: transfers, promotions, increments, acting appointments and confirmations as recorded events."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog

TODAY = timezone.localdate


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


def _post(number):
    from org.models import Position

    return Position.objects.get(number=number)


@pytest.fixture
def staffed(employee, unit):
    """Asha in LIV-001 (GS5 step 1) since 2019, on a contract with 25 days of annual leave written into it.

    The unit also has LIV-002 on the same grade, LIV-003 on GS7, which pays more, and LIV-009, frozen.
    """
    from leave.models import Entitlement, LeaveType
    from org.models import Grade, Position
    from people.models import Assignment, Contract

    gs5 = Grade.objects.get(code="GS5")
    gs7 = Grade.objects.create(
        scale=gs5.scale, code="GS7", step=1, amount=Decimal("300000"), effective_from=date(2026, 1, 1)
    )
    Position.objects.create(number="LIV-003", title="Senior Instructor", grade=gs7, org_unit=unit)
    Position.objects.create(number="LIV-009", title="Old post", grade=gs5, org_unit=unit, status="frozen")
    assignment = Assignment.objects.create(
        employee=employee,
        position=_post("LIV-001"),
        appointment_type="permanent",
        start_date=date(2019, 9, 2),
        probation_end=date(2020, 3, 1),
    )
    contract = Contract.objects.create(
        assignment=assignment, contract_type="open_ended", hours_per_week=Decimal("40"), notice_period_days=30
    )
    Entitlement.objects.create(
        contract=contract, leave_type=LeaveType.objects.get(code="ANN"), annual_days=25
    )
    return employee


def _change(client, employee, kind, number=None, *, on=None, until=None, reason="Needs of the unit"):
    body = {
        "employee": employee.id,
        "kind": kind,
        "effective_date": (on or TODAY()).isoformat(),
        "reason": reason,
    }
    if number:
        body["to_position"] = _post(number).id
    if until:
        body["end_date"] = until.isoformat()
    return client.post("/api/v1/career-events/", body, format="json")


@pytest.mark.django_db
def test_a_transfer_today_moves_the_post_and_the_contract_and_leave_with_it(api, staffed):
    from leave.models import LeaveType
    from leave.services import entitlement_days
    from people.models import Assignment, CareerEvent

    old = staffed.current_assignment
    moved = _change(api, staffed, "transfer", "LIV-002")
    assert moved.status_code == 201, moved.content
    assert moved.json()["state"] == "applied" and moved.json()["to_post"] == "LIV-002 Farm Hand"
    now = staffed.current_assignment
    assert now.position.number == "LIV-002" and now.start_date == TODAY() and now.probation_end is None
    old.refresh_from_db()
    assert old.status == Assignment.Status.ENDED and old.end_date == TODAY() - timedelta(days=1)
    assert now.contracts.count() == 1 and old.contracts.count() == 0
    assert entitlement_days(staffed, LeaveType.objects.get(code="ANN")) == Decimal(
        "25"
    )  # still the contract's
    assert _post("LIV-001").is_vacant and not _post("LIV-002").is_vacant
    event = CareerEvent.objects.get(pk=moved.json()["id"])
    assert event.to_assignment == now and event.from_grade.code == event.to_grade.code == "GS5"
    actions = set(AuditLog.objects.filter(subject=staffed.id).values_list("action", flat=True))
    assert {"career_recorded", "career_applied", "update", "create"} <= actions


@pytest.mark.django_db
def test_a_change_is_checked_against_the_file_before_it_is_recorded(api, staffed, make_user, campus):
    from people.models import Assignment, Employee

    assert _change(api, staffed, "transfer", "LIV-001").json()["code"] == "same_post"
    not_same = _change(api, staffed, "transfer", "LIV-003").json()
    assert (
        not_same["code"] == "not_same_grade" and "A post that pays more is a promotion." in not_same["detail"]
    )
    assert _change(api, staffed, "transfer", "LIV-009").json()["code"] == "post_closed"
    assert _change(api, staffed, "transfer", "LIV-002", on=date(2019, 9, 1)).json()["code"] == "too_early"
    assert _change(api, staffed, "promotion", "LIV-002").json()["code"] == "not_higher"
    assert _change(api, staffed, "increment").json()["code"] == "no_step"
    assert _change(api, staffed, "transfer", "LIV-002", reason="").json()["reason"] == ["Say why."]
    early_end = _change(api, staffed, "acting", "LIV-003", until=TODAY() - timedelta(days=1))
    assert early_end.json()["end_date"] == ["It ends after it begins."]

    someone = Employee.objects.create(
        employee_no="E0002",
        first_name="Ravi",
        last_name="Singh",
        date_of_birth=date(1985, 5, 5),
        campus=campus,
    )
    Assignment.objects.create(
        employee=someone, position=_post("LIV-002"), appointment_type="permanent", start_date=date(2020, 1, 1)
    )
    taken = _change(api, staffed, "transfer", "LIV-002")
    assert taken.status_code == 409 and taken.json()["code"] == "post_taken"

    from org.models import Campus

    elsewhere = _signed_in(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    assert "employee" in _change(elsewhere, staffed, "increment").json()  # not on their campus


@pytest.mark.django_db
def test_a_promotion_for_a_later_day_waits_then_takes_effect(api, staffed):
    from people.careers import apply_due

    later = TODAY() + timedelta(days=10)
    promoted = _change(api, staffed, "promotion", "LIV-003", on=later)
    assert promoted.status_code == 201 and promoted.json()["state"] == "scheduled"
    assert staffed.current_assignment.position.number == "LIV-001"  # not yet
    assert _change(api, staffed, "increment").json()["code"] == "pending"
    assert _change(api, staffed, "transfer", "LIV-002").status_code == 409
    assert apply_due(later - timedelta(days=1))["applied"] == 0
    assert apply_due(later) == {"applied": 1, "held": 0, "acting_ended": 0}
    now = staffed.current_assignment
    assert now.position.number == "LIV-003" and now.pay_grade.code == "GS7" and now.grade is None
    applied = api.get(f"/api/v1/career-events/{promoted.json()['id']}/").json()
    assert applied["state"] == "applied" and applied["from_grade_name"] == "GS GS5, step 1"
    assert applied["to_grade_name"] == "GS GS7, step 1"


@pytest.mark.django_db
def test_a_change_that_can_no_longer_happen_is_held_up_and_hr_is_told(api, staffed, campus, make_user):
    from notifications.models import Notification
    from people.careers import apply_due
    from people.models import Assignment, Employee

    later = TODAY() + timedelta(days=10)
    scheduled = _change(api, staffed, "transfer", "LIV-002", on=later).json()
    someone = Employee.objects.create(
        employee_no="E0002",
        first_name="Ravi",
        last_name="Singh",
        date_of_birth=date(1985, 5, 5),
        campus=campus,
    )
    Assignment.objects.create(
        employee=someone,
        position=_post("LIV-002"),
        appointment_type="permanent",
        start_date=later - timedelta(days=3),
    )
    assert apply_due(later)["held"] == 1
    held = api.get(f"/api/v1/career-events/{scheduled['id']}/").json()
    assert held["state"] == "blocked" and held["problem"].startswith("Post LIV-002 is held by someone else")
    assert staffed.current_assignment.position.number == "LIV-001"  # nothing half done
    told = Notification.objects.filter(title__startswith="A transfer did not take effect: Asha Persaud")
    assert told.exists()
    cancelled = api.post(
        f"/api/v1/career-events/{scheduled['id']}/cancel/", {"reason": "Post filled"}, format="json"
    )
    assert cancelled.json()["state"] == "cancelled"
    again = api.post(f"/api/v1/career-events/{scheduled['id']}/cancel/", {"reason": "x"}, format="json")
    assert again.status_code == 400 and again.json()["code"] == "not_scheduled"


@pytest.mark.django_db
def test_an_increment_moves_the_step_and_the_pay_with_it(api, staffed):
    from letters.fields import record_values
    from org.models import Grade
    from people.services import current_contract, hourly_rate

    gs5 = Grade.objects.get(code="GS5", step=1)
    Grade.objects.create(
        scale=gs5.scale, code="GS5", step=2, amount=Decimal("260000"), effective_from=date(2026, 1, 1)
    )
    raised = _change(api, staffed, "increment")
    assert raised.status_code == 201 and raised.json()["to_grade_name"] == "GS GS5, step 2"
    assignment = staffed.current_assignment
    assert assignment.grade.step == 2 and assignment.position.grade.step == 1  # the person's, not the post's
    assert hourly_rate(current_contract(staffed)) == Decimal("1500.00")  # 260,000 x 12 / (52 x 40)
    assert record_values(staffed, TODAY())["monthly_salary"] == "G$260,000.00"
    moved = _change(api, staffed, "transfer", "LIV-002", on=TODAY() + timedelta(days=1))
    assert (
        moved.json()["to_grade_name"] == "GS GS5, step 2"
    )  # the step goes with them to a post on the same grade


@pytest.mark.django_db
def test_acting_ends_on_its_day_and_confirmation_happens_once(api, staffed, campus):
    from people.careers import apply_due
    from people.models import Assignment, Employee

    until = TODAY() + timedelta(days=30)
    acting = _change(api, staffed, "acting", "LIV-003", until=until)
    assert acting.status_code == 201 and acting.json()["state"] == "applied"
    held = Assignment.objects.get(employee=staffed, is_acting=True)
    assert held.position.number == "LIV-003" and held.end_date == until
    assert staffed.current_assignment.position.number == "LIV-001"  # the substantive post is kept
    other = Employee.objects.create(
        employee_no="E0002",
        first_name="Ravi",
        last_name="Singh",
        date_of_birth=date(1985, 5, 5),
        campus=campus,
    )
    Assignment.objects.create(
        employee=other, position=_post("LIV-002"), appointment_type="permanent", start_date=date(2020, 1, 1)
    )
    assert _change(api, other, "acting", "LIV-003").json()["code"] == "acting_taken"
    assert apply_due(until + timedelta(days=1))["acting_ended"] == 1
    held.refresh_from_db()
    assert held.status == Assignment.Status.ENDED

    assert _change(api, staffed, "confirmation").json()["state"] == "applied"
    assert staffed.current_assignment.confirmed_on == TODAY()
    assert _change(api, staffed, "confirmation").json()["code"] == "confirmed"


@pytest.mark.django_db
def test_the_letter_for_a_change_is_written_from_the_change(api, staffed, make_user, campus):
    from letters.models import Letter, LetterTemplate

    moved = _change(api, staffed, "transfer", "LIV-002").json()
    assert moved["letter_template"] == "transfer"
    answers = moved["letter_answers"]
    assert (answers["previous_post"], answers["new_post"]) == ("Livestock Instructor", "Farm Hand")
    assert (
        answers["new_unit"] == f"Livestock Unit, {campus.name}"
        and answers["effective_date"] == TODAY().isoformat()
    )
    template = LetterTemplate.objects.get(code="transfer")
    issued = api.post(
        "/api/v1/letters/",
        {"employee": staffed.id, "template": template.id, "answers": answers, "career_event": moved["id"]},
        format="json",
    )
    assert issued.status_code == 201, issued.content
    letter = Letter.objects.get(pk=issued.json()["id"])
    assert letter.career_event_id == moved["id"] and letter.values["previous_post"] == "Livestock Instructor"
    listed = api.get(f"/api/v1/career-events/{moved['id']}/").json()["letters"]
    assert [entry["reference"] for entry in listed] == [letter.reference]

    supervisor = _signed_in(make_user("unit.head", "supervisor", campus=campus))
    seen = supervisor.get("/api/v1/career-events/", {"employee": staffed.id}).json()["results"][0]
    assert seen["kind_name"] == "Transfer" and seen["letter_answers"] is None and seen["letters"] == []
    assert supervisor.post("/api/v1/career-events/", {}, format="json").status_code == 403
