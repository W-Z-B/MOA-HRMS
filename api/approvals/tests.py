"""Item 1.33: stand-ins, time limits that remind then escalate, and one list of what waits for each person."""

from datetime import date, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from approvals.time_limits import chase
from audit.models import AuditLog
from leave.models import LeaveDecision, LeaveLedger, LeaveRequest, LeaveType
from notifications.models import Notification
from org.models import OrgUnit, Position
from people.models import Assignment, Employee

MONDAY = date(2026, 3, 2)  # leave dated in the past, so balances do not depend on the day the tests run


def _person(number, first, last, campus, position, make_user, *roles):
    employee = Employee.objects.create(
        employee_no=number, first_name=first, last_name=last, date_of_birth=date(1985, 5, 5), campus=campus
    )
    Assignment.objects.create(
        employee=employee, position=position, appointment_type="permanent", start_date=date(2020, 1, 6)
    )
    employee.user = make_user(first.lower(), *roles, campus=campus)
    employee.save()
    return employee


@pytest.fixture
def team(unit, campus, make_user, seeded):
    """Asha reports to Kwame, head of the Livestock Unit, under Michael's department. Shanta is a colleague;
    Natasha the HR Officer."""
    instructor, hand = Position.objects.get(number="LIV-001"), Position.objects.get(number="LIV-002")
    grade = instructor.grade
    department = OrgUnit.objects.create(
        code="AGR", name="Department of Agriculture", unit_type="department", campus=campus
    )
    head_post = Position.objects.create(
        number="AGR-001", title="Head of Department", grade=grade, org_unit=department
    )
    lecturer = Position.objects.create(number="AGR-003", title="Lecturer", grade=grade, org_unit=department)
    admin = OrgUnit.objects.create(code="ADM", name="Administration", unit_type="section", campus=campus)
    hr_post = Position.objects.create(number="ADM-001", title="HR Officer", grade=grade, org_unit=admin)
    people = {
        "asha": _person("E0001", "Asha", "Persaud", campus, hand, make_user, "employee"),
        "kwame": _person("E0004", "Kwame", "Adams", campus, instructor, make_user, "employee", "supervisor"),
        "michael": _person(
            "E0002", "Michael", "Thomas", campus, head_post, make_user, "employee", "supervisor"
        ),
        "shanta": _person("E0003", "Shanta", "Ramdeen", campus, lecturer, make_user, "employee"),
        "natasha": _person("E0006", "Natasha", "Khan", campus, hr_post, make_user, "hr_officer"),
    }
    unit.head, unit.parent = people["kwame"], department
    unit.save()
    department.head = people["michael"]
    department.save()
    LeaveLedger.objects.create(
        employee=people["asha"],
        leave_type=LeaveType.objects.get(code="ANN"),
        entry_date=date(2026, 1, 1),
        days=10,
        reason="opening",
    )
    return people


def _as(employee) -> APIClient:
    client = APIClient()
    client.force_login(employee.user)
    return client


def _submitted(asha, day=MONDAY) -> int:
    client = _as(asha)
    body = {
        "employee": asha.id,
        "leave_type": LeaveType.objects.get(code="ANN").id,
        "from_date": day.isoformat(),
        "to_date": day.isoformat(),
    }
    created = client.post("/api/v1/leave/requests/", body, format="json").json()
    client.post(f"/api/v1/leave/requests/{created['id']}/transition/", {"action": "submit"})
    return created["id"]


def _approve(employee, request_id):
    return _as(employee).post(f"/api/v1/leave/requests/{request_id}/transition/", {"action": "approve"})


def _stand_in(client, delegate, *, starts=None, ends=None, **extra):
    body = {
        "delegate": delegate.id,
        "starts": (starts or timezone.localdate()).isoformat(),
        "ends": (ends or timezone.localdate() + timedelta(days=5)).isoformat(),
        "reason": "Annual leave",
        **extra,
    }
    return client.post("/api/v1/approvals/delegations/", body, format="json")


@pytest.mark.django_db
def test_a_stand_in_decides_what_is_sent_to_someone_away(team):
    asha, kwame, shanta = team["asha"], team["kwame"], team["shanta"]
    request_id = _submitted(asha)
    assert LeaveRequest.objects.get(pk=request_id).manager == kwame
    assert _approve(shanta, request_id).status_code == 404  # not hers to see, let alone decide

    named = _stand_in(_as(kwame), shanta)
    assert named.status_code == 201, named.content
    assert named.json()["in_force"] is True and named.json()["delegate_name"] == "Shanta Ramdeen"
    assert Notification.objects.filter(recipient=shanta.user, title="You stand in for Kwame Adams").exists()
    (item,) = _as(shanta).get("/api/v1/approvals/waiting/").json()
    assert item["kind"] == "leave" and item["for_whom"] == "standing in for Kwame Adams"
    assert item["link"] == f"/leave/requests/{request_id}" and item["overdue"] is False

    assert _approve(shanta, request_id).status_code == 200
    decision = LeaveDecision.objects.get(request_id=request_id)
    assert (decision.step, decision.actor_name) == ("manager", "Shanta Ramdeen, standing in for Kwame Adams")

    later = _submitted(asha, MONDAY + timedelta(days=7))  # once the stand-in ends, Kwame's alone again
    assert LeaveRequest.objects.get(pk=later).state == "submitted"
    ended = _as(kwame).post(f"/api/v1/approvals/delegations/{named.json()['id']}/end/")
    assert ended.json()["cancelled"] is True and ended.json()["in_force"] is False
    assert _approve(shanta, later).status_code == 404


@pytest.mark.django_db
def test_a_stand_in_is_named_within_the_rules(team, make_user):
    from org.models import Campus

    asha, kwame, shanta, natasha = team["asha"], team["kwame"], team["shanta"], team["natasha"]
    client = _as(kwame)
    assert _stand_in(client, kwame).json()["delegate"] == ["A stand-in is someone else."]
    far = Employee.objects.create(
        employee_no="E0099",
        first_name="Far",
        last_name="Away",
        date_of_birth=date(1980, 1, 1),
        campus=Campus.objects.get(code="ESQ"),
    )
    assert (
        "does not exist" in _stand_in(client, far).json()["delegate"][0]
    )  # nobody named beyond what they see
    asha.user.is_active = False
    asha.user.save()
    assert _stand_in(client, asha).json()["delegate"] == ["Asha Persaud cannot sign in to decide."]
    today = timezone.localdate()
    assert _stand_in(client, shanta, starts=today, ends=today - timedelta(days=1)).json()["ends"] == [
        "It ends on or after the day it starts."
    ]
    assert _stand_in(client, shanta).status_code == 201
    overlap = _stand_in(client, natasha, starts=today + timedelta(days=2), ends=today + timedelta(days=9))
    assert overlap.json()["starts"] == ["Kwame Adams already has a stand-in for part of that time."]

    assert _stand_in(_as(shanta), natasha, delegator=kwame.id).json()["delegator"] == [
        "You can name a stand-in for yourself only."
    ]
    hr = _stand_in(_as(natasha), shanta, delegator=team["michael"].id)
    assert hr.status_code == 201 and hr.json()["delegator_name"] == "Michael Thomas"
    assert _as(shanta).post(f"/api/v1/approvals/delegations/{hr.json()['id']}/end/").status_code == 403
    listed = _as(natasha).get("/api/v1/approvals/delegations/", {"employee": team["michael"].id}).json()
    assert [d["delegate_name"] for d in listed["results"]] == ["Shanta Ramdeen"]


def _waiting_since(request_id, when: datetime):
    LeaveRequest.objects.filter(pk=request_id).update(waiting_since=when)


@pytest.mark.django_db
def test_a_request_left_waiting_is_chased_then_sent_up_the_line(team):
    asha, kwame, michael = team["asha"], team["kwame"], team["michael"]
    request_id = _submitted(asha)
    monday = timezone.make_aware(datetime(2026, 10, 5, 10, 0))  # no public holiday from 5 to 12 October 2026
    _waiting_since(request_id, monday)
    assert chase(date(2026, 10, 7))["reminded"] == 0  # two working days: not yet
    assert chase(date(2026, 10, 8))["reminded"] == 1  # three: Kwame is reminded, once
    assert chase(date(2026, 10, 8))["reminded"] == 0
    assert Notification.objects.filter(
        recipient=kwame.user, title__startswith="Waiting 3 working days"
    ).exists()

    assert chase(date(2026, 10, 12))["escalated"] == 1  # five working days: it goes on to Michael
    request = LeaveRequest.objects.get(pk=request_id)
    assert (
        request.manager == michael
        and timezone.localtime(request.waiting_since).date() == timezone.localdate()
    )
    assert AuditLog.objects.filter(
        entity="leave.leaverequest", entity_id=request_id, action="escalated"
    ).exists()
    assert Notification.objects.filter(
        recipient=michael.user, title="Leave request sent on to you: Asha Persaud"
    ).exists()
    assert Notification.objects.filter(
        recipient=asha.user, title="Your leave request was sent on to Michael Thomas"
    ).exists()
    assert Notification.objects.filter(
        recipient=kwame.user, title="A leave request was sent on to Michael Thomas"
    ).exists()
    assert _approve(michael, request_id).status_code == 200


@pytest.mark.django_db
def test_hr_is_chased_too_and_then_the_hr_manager_is_told(team, make_user):
    asha, kwame = team["asha"], team["kwame"]
    hr_manager = make_user("hr.head", "hr_manager")
    request_id = _submitted(asha)
    _approve(kwame, request_id)
    _waiting_since(request_id, timezone.make_aware(datetime(2026, 10, 5, 10, 0)))
    assert chase(date(2026, 10, 8))["hr_reminded"] == 1
    assert Notification.objects.filter(
        recipient=team["natasha"].user, title__startswith="Waiting 3 working days"
    ).exists()
    assert chase(date(2026, 10, 12))["hr_escalated"] == 1
    assert Notification.objects.filter(
        recipient=hr_manager, title__startswith="Waiting 5 working days for Human"
    ).exists()


@pytest.mark.django_db
def test_everything_waiting_for_hr_is_in_one_list(team, make_user):
    from people.models import BankAccount, CareerEvent
    from privacy.models import CorrectionRequest
    from signing.models import SignatureRequest

    asha, kwame, natasha = team["asha"], team["kwame"], team["natasha"]
    request_id = _submitted(asha)
    _approve(kwame, request_id)
    finance = make_user("finance.officer", "finance")
    BankAccount.objects.create(
        employee=asha,
        bank_name="Republic Bank",
        account_name="Asha Persaud",
        account_number="123456789",
        account_number_last4="6789",
        created_by=finance,
    )
    CorrectionRequest.objects.create(
        employee=asha, subject="contact", wrong="Old phone", should_be="New phone", due_by=date(2026, 11, 1)
    )
    CareerEvent.objects.create(
        employee=asha,
        kind="transfer",
        effective_date=date(2026, 11, 1),
        reason="x",
        state="blocked",
        problem="Post LIV-001 is held by someone else on 1 November 2026.",
    )
    items = _as(natasha).get("/api/v1/approvals/waiting/").json()
    assert {item["kind"] for item in items} == {
        "leave_hr",
        "correction",
        "career",
    }  # bank details: HR officers do not decide
    career = next(item for item in items if item["kind"] == "career")
    assert career["link"] == f"/people/{asha.id}/appointments" and "held by someone else" in career["title"]

    hr_manager = make_user("hr.head", "hr_manager")
    session = APIClient()
    session.force_login(hr_manager)
    s = session.session
    s["mfa_verified"] = True
    s.save()
    assert "bank" in {item["kind"] for item in session.get("/api/v1/approvals/waiting/").json()}

    from django.core.files.base import ContentFile

    from people.models import Document

    document = Document.objects.create(
        employee=asha, title="Policy", doc_type="other", file=ContentFile(b"%PDF", name="p.pdf")
    )
    SignatureRequest.objects.create(
        document=document, employee=asha, kind="acknowledge", statement="I have read it."
    )
    mine = _as(asha).get("/api/v1/approvals/waiting/").json()
    assert [(item["kind"], item["link"]) for item in mine] == [
        ("signature", "/me")
    ]  # not her own leave or correction
