"""Item 1.46: restriction while accuracy is contested or on objection, honoured where the record is used, and
objections decided by the data protection officer."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from audit.models import AuditLog
from notifications.models import Notification


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def asha(employee, make_user, campus, unit):
    """Asha in post LIV-001, with a contract and an account of her own."""
    from org.models import Position
    from people.models import Assignment, Contract

    employee.user = make_user("asha.persaud", "employee", campus=campus)
    employee.save()
    assignment = Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2019, 9, 2),
    )
    Contract.objects.create(
        assignment=assignment, contract_type="open_ended", hours_per_week=Decimal("40"), notice_period_days=30
    )
    return employee


@pytest.fixture
def officer(make_user):
    return make_user("privacy.officer", "data_protection_officer")


def _job_letter(client, employee):
    from letters.models import LetterTemplate

    template = LetterTemplate.objects.filter(code="job_letter").order_by("-version").first()
    body = {"employee": employee.id, "template": template.id, "answers": {"purpose": "a bank loan"}}
    return client.post("/api/v1/letters/", body, format="json")


@pytest.mark.django_db
def test_a_contested_part_is_kept_but_not_used_until_the_correction_is_answered(api, asha, hr_officer):
    from integration.models import ServiceClient

    me = _signed_in(asha.user)
    asked = me.post(
        "/api/v1/privacy/corrections/",
        {"subject": "appointment", "wrong": "My post", "should_be": "Senior instructor", "restrict": True},
        format="json",
    )
    assert asked.status_code == 201, asked.content
    assert asked.json()["restricted"] is True and "restrict" not in asked.json()
    held = api.get(f"/api/v1/employees/{asha.id}/").json()["restricted"]
    assert held == ["Appointment or contract: its accuracy is contested"]

    refused = _job_letter(api, asha)
    assert refused.status_code == 409 and refused.json()["code"] == "restricted"
    assert "is restricted (its accuracy is contested)" in refused.json()["detail"]
    change = {
        "employee": asha.id,
        "kind": "increment",
        "effective_date": "2026-11-01",
        "reason": "Annual increment",
    }
    assert api.post("/api/v1/career-events/", change, format="json").json()["code"] == "restricted"

    _, key = ServiceClient.issue("srms", ["staff:read"])
    feed = APIClient()
    feed.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
    (row,) = feed.get("/api/v1/integration/staff/").json()["results"]
    assert row["restricted"] == ["appointment"] and row["position_title"] is None and row["unit_code"] is None
    assert row["full_name"] == "Asha Persaud"  # the number and name always go, so others know who is who

    correction = asked.json()["id"]
    answered = api.post(
        f"/api/v1/privacy/corrections/{correction}/decide/", {"outcome": "declined", "note": "As appointed"}
    )
    assert answered.status_code == 200, answered.content
    assert api.get(f"/api/v1/employees/{asha.id}/").json()["restricted"] == []
    assert Notification.objects.filter(recipient=asha.user, title__contains="is lifted").exists()
    assert _job_letter(api, asha).status_code == 201
    assert AuditLog.objects.filter(action="restriction_lifted", subject=asha.id).exists()


@pytest.mark.django_db
def test_an_objection_restricts_its_part_until_the_officer_decides(api, asha, officer, hr_manager):
    me = _signed_in(asha.user)
    lodged = me.post(
        "/api/v1/privacy/objections/",
        {"part": "contact", "grounds": "My phone number is shared with the farm roster"},
        format="json",
    )
    assert lodged.status_code == 201, lodged.content
    objection = lodged.json()
    assert objection["state"] == "open" and objection["is_mine"]
    assert Notification.objects.filter(recipient=officer, link="/admin/objections").exists()
    assert me.get("/api/v1/privacy/restrictions/?in_force=1").json()["results"][0]["ground"] == "objection"

    path = f"/api/v1/privacy/objections/{objection['id']}/decide/"
    assert api.post(path, {"outcome": "upheld", "reasons": "x"}).status_code == 403  # HR does not decide
    officer_client = _signed_in(officer)
    assert officer_client.post(path, {"outcome": "not_upheld"}).status_code == 400  # reasons required
    decided = officer_client.post(
        path, {"outcome": "not_upheld", "reasons": "Needed to reach staff in an emergency at work"}
    )
    assert decided.status_code == 200 and decided.json()["state"] == "not_upheld"
    assert me.get("/api/v1/privacy/restrictions/?in_force=1").json()["count"] == 0
    told = Notification.objects.filter(recipient=asha.user, title__contains="is lifted").get()
    assert told.body.startswith("Your objection was not upheld: Needed to reach staff")
    again = officer_client.post(path, {"outcome": "upheld", "reasons": "Changed my mind"})
    assert again.status_code == 409

    second = me.post("/api/v1/privacy/objections/", {"part": "bank", "grounds": "Not needed"}, format="json")
    upheld = officer_client.post(
        f"/api/v1/privacy/objections/{second.json()['id']}/decide/",
        {"outcome": "upheld", "reasons": "Not needed for pay yet"},
    )
    assert upheld.json()["state"] == "upheld"
    assert me.get("/api/v1/privacy/restrictions/?in_force=1").json()["results"][0]["part"] == "bank"
    assert _signed_in(hr_manager).get("/api/v1/privacy/objections/").json()["count"] == 2
    assert api.get("/api/v1/privacy/objections/").json()["count"] == 0  # an HR officer sees only their own


@pytest.mark.django_db
def test_hr_restricts_and_lifts_with_reasons_only_on_their_campuses(api, asha, make_user, campus, officer):
    from org.models import Campus

    placed = api.post(
        "/api/v1/privacy/restrictions/",
        {"employee": asha.id, "part": "bank", "ground": "unlawful", "note": "Collected without a notice"},
        format="json",
    )
    assert placed.status_code == 201, placed.content
    assert Notification.objects.filter(
        recipient=asha.user, title="Bank details in your record is restricted"
    ).exists()
    objection_ground = {"employee": asha.id, "part": "bank", "ground": "objection", "note": "x"}
    assert api.post("/api/v1/privacy/restrictions/", objection_ground, format="json").status_code == 400

    elsewhere = _signed_in(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    lift_path = f"/api/v1/privacy/restrictions/{placed.json()['id']}/lift/"
    assert elsewhere.post(lift_path, {"reason": "x"}).status_code == 404
    assert (
        elsewhere.post(
            "/api/v1/privacy/restrictions/", {**objection_ground, "ground": "unlawful"}
        ).status_code
        == 400
    )
    supervisor = _signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert (
        supervisor.post(
            "/api/v1/privacy/restrictions/", {**objection_ground, "ground": "unlawful"}
        ).status_code
        == 403
    )
    assert _signed_in(asha.user).post(lift_path, {"reason": "Mine"}).status_code == 403

    assert api.post(lift_path, {}).status_code == 400  # a reason is required: the person is told it
    lifted = api.post(lift_path, {"reason": "A notice was given and acknowledged"})
    assert lifted.status_code == 200 and lifted.json()["in_force"] is False
    assert api.post(lift_path, {"reason": "Again"}).status_code == 409
    assert _signed_in(officer).get("/api/v1/privacy/restrictions/").json()["count"] == 1


@pytest.mark.django_db
def test_a_persons_copy_of_their_record_lists_their_restrictions_and_objections(asha):
    from privacy.services import record_of_employee

    me = _signed_in(asha.user)
    me.post("/api/v1/privacy/objections/", {"part": "leave", "grounds": "My reasons"}, format="json")
    copy = record_of_employee(asha)["staff_record"]
    assert [row["about"] for row in copy["objections"]] == ["Leave records"]
    assert [row["ground"] for row in copy["restrictions"]] == ["The person has objected"]
