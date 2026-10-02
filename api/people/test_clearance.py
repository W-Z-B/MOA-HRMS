"""Items 1.13 and 1.17: the register of items issued, the clearance of someone leaving, the exit interview."""

from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from people import leaving

TODAY = timezone.localdate


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def placed(employee, unit, make_user, campus):
    """Asha in LIV-001 since 2019, confirmed, with an account of her own."""
    from org.models import Position
    from people.models import Assignment

    employee.user = make_user("asha.persaud", "employee", campus=campus)
    employee.save()
    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2019, 9, 2),
        confirmed_on=date(2020, 3, 1),
    )
    return employee


def _issue(client, employee, description, kind="tool", issued_on=date(2026, 1, 5)):
    body = {
        "employee": employee.id,
        "kind": kind,
        "description": description,
        "issued_on": issued_on.isoformat(),
    }
    return client.post("/api/v1/issued-items/", body, format="json")


def _give_back(client, item_id, condition="good", on=None):
    body = {"returned_on": (on or TODAY()).isoformat(), "condition": condition}
    return client.post(f"/api/v1/issued-items/{item_id}/return/", body, format="json")


def _leaving(client, employee, last=None, reason="resignation"):
    body = {
        "employee": employee.id,
        "reason": reason,
        "last_day": (last or TODAY() + timedelta(days=30)).isoformat(),
        "note": "Taking up a post abroad",
    }
    if reason == "resignation":
        body["notice_given_on"] = TODAY().isoformat()
    return client.post("/api/v1/separations/", body, format="json").json()


@pytest.mark.django_db
def test_items_are_issued_and_given_back(api, placed, make_user, campus):
    from org.models import Campus

    key = _issue(api, placed, "Key to the livestock pens", kind="key")
    assert key.status_code == 201 and key.json()["kind_name"] == "Key" and key.json()["returned_on"] is None
    supervisor = _signed_in(make_user("unit.head", "supervisor", campus=campus))
    machete = _issue(supervisor, placed, "Machete")
    assert machete.status_code == 201 and machete.json()["issued_by"] == "unit.head"
    plain = _signed_in(make_user("someone", "employee", campus=campus))
    assert _issue(plain, placed, "Boots").status_code == 403
    elsewhere = _signed_in(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    assert "employee" in _issue(elsewhere, placed, "Boots").json()

    out = api.get("/api/v1/issued-items/", {"employee": placed.id, "outstanding": "1"}).json()
    assert out["count"] == 2
    assert _give_back(api, key.json()["id"], on=date(2025, 1, 1)).json()["code"] == "too_early"
    back = _give_back(api, key.json()["id"])
    assert (
        back.json()["returned_on"] == TODAY().isoformat() and back.json()["condition_name"] == "In good order"
    )
    assert _give_back(api, key.json()["id"]).json()["code"] == "returned"
    assert api.get("/api/v1/issued-items/", {"employee": placed.id, "outstanding": "1"}).json()["count"] == 1


@pytest.mark.django_db
def test_leaving_opens_the_clearance_and_items_out_hold_it(api, placed):
    boots = _issue(api, placed, "Rubber boots", kind="protective").json()
    laptop = _issue(api, placed, "Laptop", kind="device").json()
    separation = _leaving(api, placed)
    assert separation["clearance"] == {
        "done": 0,
        "total": 6,
        "open": [step for _, step, _ in leaving.CLEARANCE],
    }
    clearance = api.get(f"/api/v1/separations/{separation['id']}/clearance/").json()
    assert [step["code"] for step in clearance["steps"]] == [
        "items",
        "handover",
        "money",
        "library",
        "interview",
        "account",
    ]
    assert {item["description"] for item in clearance["outstanding_items"]} == {"Rubber boots", "Laptop"}

    url = f"/api/v1/separations/{separation['id']}/clearance"
    held = api.post(f"{url}/items/", {"note": "All back"}, format="json")
    assert held.status_code == 409 and held.json()["detail"].startswith(
        "2 items are still out: Rubber boots, Laptop."
    )
    _give_back(api, boots["id"], condition="worn")
    _give_back(api, laptop["id"], condition="lost")
    cleared = api.post(f"{url}/items/", {"note": "Laptop lost; reported to Finance"}, format="json").json()
    assert cleared["outstanding_items"] == [] and cleared["steps"][0]["state"] == "done"
    assert (
        api.post(f"{url}/handover/", {"note": "Confirmed by Kwame Adams"}, format="json").status_code == 200
    )
    money = api.post(f"{url}/money/", {"done": False, "note": "No advances"}, format="json").json()
    assert (
        money["steps"][2]["state_name"] == "Not needed"
        and money["steps"][2]["cleared_by_name"] == "hr.officer"
    )
    assert api.post(f"{url}/money/", {}, format="json").json()["code"] == "not_open"
    assert api.post(f"{url}/account/", {}, format="json").json()["code"] == "system_step"
    assert api.post(f"{url}/interview/", {}, format="json").json()["code"] == "interview_step"
    assert api.post(f"{url}/nonsense/", {}, format="json").status_code == 404
    summary = api.get(f"/api/v1/separations/{separation['id']}/").json()["clearance"]
    assert (summary["done"], summary["total"]) == (3, 6)


@pytest.mark.django_db
def test_the_exit_interview_is_for_hr_and_the_principal(api, placed, make_user):
    separation = _leaving(api, placed)
    url = f"/api/v1/separations/{separation['id']}/exit-interview/"
    assert api.get(url).status_code == 404
    answers = {
        "held_on": TODAY().isoformat(),
        "main_reason": "pay",
        "would_recommend": "yes",
        "rating_pay": 2,
        "rating_supervision": 4,
        "keep": "The farm work with students",
        "change": "Pay on time",
    }
    assert api.post(url, {**answers, "rating_pay": 6}, format="json").status_code == 400
    saved = api.post(url, answers, format="json")
    assert saved.status_code == 200 and saved.json()["main_reason_name"] == "Pay and benefits"
    steps = api.get(f"/api/v1/separations/{separation['id']}/clearance/").json()["steps"]
    assert next(s for s in steps if s["code"] == "interview")["note"] == "Held"
    principal = _signed_in(make_user("the.principal", "principal"))
    assert principal.get(url).json()["change"] == "Pay on time"
    auditor = _signed_in(make_user("audit.reader", "auditor"))
    assert auditor.get(f"/api/v1/separations/{separation['id']}/").status_code == 200  # the leaving, yes
    assert auditor.get(url).status_code == 403  # their views of their managers, no


@pytest.mark.django_db
def test_a_declined_interview_and_the_last_day_close_their_steps(api, placed, campus):
    from people.models import ClearanceStep, Employee, Separation

    separation = _leaving(api, placed, last=TODAY() + timedelta(days=2))
    url = f"/api/v1/separations/{separation['id']}/exit-interview/"
    assert (
        api.post(url, {"held_on": TODAY().isoformat(), "declined": True}, format="json").json()["declined"]
        is True
    )
    leaving.complete_due(TODAY() + timedelta(days=3))
    steps = {s.code: s for s in ClearanceStep.objects.filter(separation_id=separation["id"])}
    assert (steps["interview"].state, steps["interview"].note) == ("done", "Offered, and declined")
    assert steps["account"].state == "done" and steps["account"].note.startswith(
        "Switched off after the last day"
    )

    other = Employee.objects.create(
        employee_no="E0050",
        first_name="No",
        last_name="Account",
        date_of_birth=date(1980, 1, 1),
        campus=campus,
    )
    from org.models import Position
    from people.models import Assignment

    Assignment.objects.create(
        employee=other,
        position=Position.objects.get(number="LIV-002"),
        appointment_type="temporary",
        start_date=date(2020, 1, 1),
    )
    gone = _leaving(api, other, last=TODAY() - timedelta(days=1), reason="contract_end")
    assert Separation.objects.get(pk=gone["id"]).state == "left"
    account = ClearanceStep.objects.get(separation_id=gone["id"], code="account")
    assert (account.state, account.note) == ("not_needed", "No sign-in account")
