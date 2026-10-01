"""Leave self-service: the balance and evidence rules, the employee's own manager, the receipt.

Requests in these tests are dated in the past on purpose. Leave still to come counts what will have
accrued by its first day, which would make the figures depend on the day the tests run.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from leave.models import Entitlement, LeaveDecision, LeaveLedger, LeaveRequest, LeaveType
from leave.services import accrue_month, available_on, balance, balances_for, entitlement_days, grant_year
from notifications.models import Notification
from org.models import OrgUnit, Position
from people.models import Assignment, Contract, Employee
from people.services import manager_of

MONDAY = date(2026, 3, 2)  # Monday 2 to Friday 6 March 2026: five working days, no public holiday


def _person(number, first, last, campus, position, make_user, *roles, start=date(2020, 1, 6)):
    """An employee in a post, with an account. Roles are scoped to the campus."""
    employee = Employee.objects.create(
        employee_no=number, first_name=first, last_name=last, date_of_birth=date(1985, 5, 5), campus=campus
    )
    Assignment.objects.create(
        employee=employee, position=position, appointment_type="permanent", start_date=start
    )
    employee.user = make_user(first.lower(), *roles, campus=campus)
    employee.save()
    return employee


@pytest.fixture
def team(unit, campus, make_user, seeded):
    """Asha reports to Kwame, who heads the Livestock Unit. Natasha is the HR Officer."""
    instructor, hand = Position.objects.get(number="LIV-001"), Position.objects.get(number="LIV-002")
    asha = _person("E0001", "Asha", "Persaud", campus, hand, make_user, "employee")
    kwame = _person("E0004", "Kwame", "Adams", campus, instructor, make_user, "employee")
    unit.head = kwame
    unit.save()
    admin = OrgUnit.objects.create(code="ADM", name="Administration", unit_type="section", campus=campus)
    post = Position.objects.create(
        number="ADM-001", title="Human Resources Officer", grade=instructor.grade, org_unit=admin
    )
    natasha = _person("E0006", "Natasha", "Khan", campus, post, make_user, "hr_officer")
    return {"asha": asha, "kwame": kwame, "natasha": natasha, "unit": unit}


def _credit(employee, code, days, on=date(2026, 1, 1)):
    return LeaveLedger.objects.create(
        employee=employee,
        leave_type=LeaveType.objects.get(code=code),
        entry_date=on,
        days=days,
        reason="opening",
    )


def _as(employee) -> APIClient:
    client = APIClient()
    client.force_login(employee.user)
    return client


def _request(client, employee, code, start, end):
    return client.post(
        "/api/v1/leave/requests/",
        {
            "employee": employee.id,
            "leave_type": LeaveType.objects.get(code=code).id,
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
        },
        format="json",
    )


def _move(client, request_id, action, comment=""):
    return client.post(
        f"/api/v1/leave/requests/{request_id}/transition/", {"action": action, "comment": comment}
    )


# The start of a real JPEG: uploads are checked by their contents, not their names (core.uploads).
JPEG_START = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"


def _note(name="note.jpg"):
    return {"file": SimpleUploadedFile(name, JPEG_START + b" scan of the note", content_type="image/jpeg")}


@pytest.mark.django_db
def test_sick_leave_within_the_balance_needs_no_note(team):
    asha = team["asha"]
    _credit(asha, "SIC", 14)
    client = _as(asha)

    created = _request(client, asha, "SIC", MONDAY, date(2026, 3, 3))
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["days"] == "2.00" and body["evidence_required"] is False
    assert body["balance_after"] == Decimal("12.00")
    assert _move(client, body["id"], "submit").status_code == 200


@pytest.mark.django_db
def test_sick_leave_beyond_the_balance_needs_a_doctors_note(team):
    asha, kwame, natasha = team["asha"], team["kwame"], team["natasha"]
    sick = LeaveType.objects.get(code="SIC")
    _credit(asha, "SIC", 1)
    _credit(asha, "ANN", 10)
    client = _as(asha)

    created = _request(client, asha, "SIC", MONDAY, date(2026, 3, 4)).json()
    assert created["days"] == "3.00" and created["evidence_required"] is True
    assert created["evidence_name"] == "Doctor's note"

    refused = _move(client, created["id"], "submit")
    assert refused.status_code == 409 and refused.json()["code"] == "evidence_required"
    assert "2 days of this request are beyond your balance" in refused.json()["detail"]

    attached = client.post(f"/api/v1/leave/requests/{created['id']}/evidence/", _note(), format="multipart")
    assert attached.status_code == 201 and attached.json()["has_evidence"] is True
    assert _move(client, created["id"], "submit").status_code == 200

    assert _move(_as(kwame), created["id"], "approve").status_code == 200
    final = _move(_as(natasha), created["id"], "approve")
    assert final.status_code == 200 and final.json()["state"] == "approved"

    # The ledger is taken down to zero, never below; the rest is recorded on the request.
    assert balance(asha, sick) == Decimal("0.00")
    assert final.json()["days_beyond"] == "2.00"
    receipt = final.json()["receipt"]
    assert receipt["days_beyond"] == "2.00" and receipt["evidence"] == "Doctor's note"
    assert {row["code"]: row["remaining"] for row in receipt["balances"]} == {"ANN": "10.00", "SIC": "0.00"}
    note = Notification.objects.get(recipient=asha.user, title="Your leave request was approved")
    assert "2 days beyond your entitlement, supported by your doctor's note" in note.body


@pytest.mark.django_db
def test_the_note_is_seen_by_the_employee_and_hr_only(team, make_user, campus):
    asha, kwame, natasha = team["asha"], team["kwame"], team["natasha"]
    client = _as(asha)
    created = _request(client, asha, "SIC", MONDAY, MONDAY).json()
    url = f"/api/v1/leave/requests/{created['id']}/evidence/"

    assert client.post(url, _note("virus.exe"), format="multipart").status_code == 400
    assert client.post(url, _note(), format="multipart").status_code == 201
    assert _move(client, created["id"], "submit").status_code == 200

    document = LeaveRequest.objects.get(pk=created["id"]).evidence
    assert document.classification == "medical" and document.employee == asha

    assert client.get(url).status_code == 200
    assert _as(natasha).get(url).status_code == 200
    # The manager decides on the request and is told a note is attached, but cannot open it.
    manager = _as(kwame)
    assert manager.get(f"/api/v1/leave/requests/{created['id']}/").json()["has_evidence"] is True
    assert manager.get(url).status_code == 403
    assert manager.post(url, _note(), format="multipart").status_code == 403
    # An employee cannot name a document as evidence, only attach a file to their own request.
    named = client.post(
        "/api/v1/leave/requests/",
        {
            "employee": asha.id,
            "leave_type": LeaveType.objects.get(code="SIC").id,
            "from_date": "2026-04-06",
            "to_date": "2026-04-06",
            "evidence": document.id,
        },
        format="json",
    )
    assert named.status_code == 400 and "evidence" in named.json()


@pytest.mark.django_db
def test_annual_leave_beyond_the_balance_is_refused(team):
    asha = team["asha"]
    _credit(asha, "ANN", 3)
    client = _as(asha)

    refused = _request(client, asha, "ANN", MONDAY, date(2026, 3, 6))
    assert refused.status_code == 400
    assert refused.json()["to_date"] == [
        "This needs 5 days of annual leave and 3 days will be available on 02/03/2026."
    ]
    assert _request(client, asha, "ANN", MONDAY, date(2026, 3, 4)).status_code == 201


@pytest.mark.django_db
def test_days_awaiting_a_decision_are_not_available_twice(team):
    asha = team["asha"]
    _credit(asha, "ANN", 5)
    client = _as(asha)
    first = _request(client, asha, "ANN", MONDAY, date(2026, 3, 4)).json()
    assert _move(client, first["id"], "submit").status_code == 200

    second = _request(client, asha, "ANN", date(2026, 3, 9), date(2026, 3, 11))
    assert second.status_code == 400 and "2 days will be available" in second.json()["to_date"][0]
    row = next(r for r in balances_for(asha) if r["code"] == "ANN")
    assert (row["balance"], row["pending"], row["available"]) == (Decimal(5), Decimal(3), Decimal(2))


@pytest.mark.django_db
def test_leave_to_come_counts_what_will_have_accrued(team):
    asha = team["asha"]
    annual = LeaveType.objects.get(code="ANN")
    _credit(asha, "ANN", 3)
    today = date(2026, 9, 29)
    # 1 October and 1 November each credit 21 / 12 = 1.75 days before leave starting on 2 November.
    assert available_on(asha, annual, date(2026, 11, 2), today=today) == Decimal("6.50")
    assert available_on(asha, annual, date(2026, 9, 29), today=today) == Decimal("3.00")
    # Sick leave is granted whole, so nothing more is due later in the year.
    sick = LeaveType.objects.get(code="SIC")
    assert available_on(asha, sick, date(2026, 11, 2), today=today) == Decimal("0")


@pytest.mark.django_db
def test_overlapping_dates_are_refused(team):
    asha = team["asha"]
    _credit(asha, "ANN", 15)
    client = _as(asha)
    first = _request(client, asha, "ANN", MONDAY, date(2026, 3, 6)).json()
    assert _move(client, first["id"], "submit").status_code == 200

    clash = _request(client, asha, "SIC", date(2026, 3, 5), date(2026, 3, 9))
    assert clash.status_code == 400
    assert clash.json()["from_date"] == [
        "These dates overlap annual leave from 02/03/2026 to 06/03/2026 (submitted)."
    ]
    # The form asks before saving and is told the same.
    checked = client.post(
        "/api/v1/leave/requests/check/",
        {
            "leave_type": LeaveType.objects.get(code="SIC").id,
            "from_date": "2026-03-05",
            "to_date": "2026-03-09",
        },
        format="json",
    ).json()
    assert [p["code"] for p in checked["problems"]] == ["overlap"] and checked["days"] == Decimal("3")
    # A cancelled request frees its dates.
    assert _move(client, first["id"], "cancel").status_code == 200
    assert _request(client, asha, "SIC", date(2026, 3, 5), date(2026, 3, 9)).status_code == 201


@pytest.mark.django_db
def test_a_request_goes_to_the_employees_own_manager(team, make_user, campus):
    asha, kwame, natasha = team["asha"], team["kwame"], team["natasha"]
    _credit(asha, "ANN", 10)
    another = make_user("another.head", "supervisor", campus=campus)
    client = _as(asha)
    created = _request(client, asha, "ANN", MONDAY, date(2026, 3, 3)).json()
    submitted = _move(client, created["id"], "submit").json()

    assert submitted["manager_name"] == "Kwame Adams"
    assert Notification.objects.filter(recipient=kwame.user, kind="approval").count() == 1
    assert not Notification.objects.filter(recipient=another).exists()

    # Holding the supervisor role is not enough: the request was sent to Kwame.
    other = APIClient()
    other.force_login(another)
    assert _move(other, created["id"], "approve").status_code == 403
    # HR gives the final approval only, after the manager.
    assert _move(_as(natasha), created["id"], "approve").status_code == 403

    # Kwame holds no supervisor role: he decides because he is Asha's manager.
    manager = _as(kwame)
    listed = manager.get("/api/v1/leave/requests/?state=submitted").json()["results"]
    assert [r["id"] for r in listed] == [created["id"]] and listed[0]["allowed_actions"] == [
        "approve",
        "reject",
    ]
    approved = _move(manager, created["id"], "approve").json()
    assert approved["state"] == "supervisor_approved"
    assert [(d["step"], d["outcome"], d["actor_name"]) for d in approved["decisions"]] == [
        ("manager", "approved", "Kwame Adams")
    ]
    progress = Notification.objects.get(recipient=asha.user)
    assert progress.title == "Your manager approved your leave request"
    assert "Approved by Kwame Adams" in progress.body and "Human Resources" in progress.body


@pytest.mark.django_db
def test_a_head_of_unit_is_sent_to_the_head_above(team, campus, make_user):
    asha, kwame, unit = team["asha"], team["kwame"], team["unit"]
    assert manager_of(asha) == kwame
    # Nobody above Kwame yet: he cannot be his own manager, so the campus supervisors stand in.
    assert manager_of(kwame) is None

    department = OrgUnit.objects.create(code="AGR", name="Department of Agriculture", campus=campus)
    post = Position.objects.create(
        number="AGR-001",
        title="Head of Department",
        grade=kwame.current_assignment.position.grade,
        org_unit=department,
    )
    michael = _person("E0002", "Michael", "Thomas", campus, post, make_user, "employee")
    department.head = michael
    department.save()
    unit.parent = department
    unit.save()
    assert manager_of(kwame) == michael

    # A head who has left, or who has no account, is passed over for the next one up.
    kwame.status = Employee.Status.SEPARATED
    kwame.save()
    assert manager_of(asha) == michael


@pytest.mark.django_db
def test_nobody_decides_their_own_request(team, make_user, campus):
    natasha = team["natasha"]
    _credit(natasha, "ANN", 10)
    stand_in = make_user("stand.in", "supervisor", campus=campus)
    client = _as(natasha)
    created = _request(client, natasha, "ANN", MONDAY, MONDAY).json()
    assert _move(client, created["id"], "submit").json()["manager_name"] is None

    supervisor = APIClient()
    supervisor.force_login(stand_in)
    assert _move(supervisor, created["id"], "approve").status_code == 200
    # Natasha is the HR Officer, and this is her own leave.
    own = client.get(f"/api/v1/leave/requests/{created['id']}/").json()
    assert own["allowed_actions"] == ["cancel"]
    assert _move(client, created["id"], "approve").status_code == 403
    assert _move(client, created["id"], "reject", "No").status_code == 403


@pytest.mark.django_db
def test_the_receipt_shows_what_is_left(team):
    asha, kwame, natasha = team["asha"], team["kwame"], team["natasha"]
    _credit(asha, "ANN", 10)
    _credit(asha, "SIC", 14)
    client = _as(asha)
    created = _request(client, asha, "ANN", MONDAY, date(2026, 3, 6)).json()
    assert client.get(f"/api/v1/leave/requests/{created['id']}/receipt/").status_code == 404

    _move(client, created["id"], "submit")
    _move(_as(kwame), created["id"], "approve")
    assert _move(_as(natasha), created["id"], "approve").status_code == 200

    receipt = client.get(f"/api/v1/leave/requests/{created['id']}/receipt/").json()
    assert receipt["number"] == f"LR-2026-{created['id']:06d}"
    assert (receipt["days"], receipt["return_date"]) == ("5.00", "2026-03-09")
    assert [(a["step"], a["name"]) for a in receipt["approvals"]] == [
        ("Manager", "Kwame Adams"),
        ("Human Resources", "Natasha Khan"),
    ]
    assert {row["name"]: row["remaining"] for row in receipt["balances"]} == {
        "Annual leave": "5.00",
        "Sick leave": "14.00",
    }
    note = Notification.objects.get(recipient=asha.user, title="Your leave request was approved")
    assert "Remaining: Annual leave 5 days, Sick leave 14 days." in note.body
    assert "Return to work on 09/03/2026." in note.body and receipt["number"] in note.body

    # The receipt is a record of the day of approval: later leave does not rewrite it.
    _credit(asha, "ANN", -2, on=date(2026, 4, 1))
    again = client.get(f"/api/v1/leave/requests/{created['id']}/receipt/").json()
    assert again["balances"] == receipt["balances"]


@pytest.mark.django_db
def test_a_rejection_is_recorded_and_takes_no_days(team):
    asha, kwame = team["asha"], team["kwame"]
    _credit(asha, "ANN", 10)
    client = _as(asha)
    created = _request(client, asha, "ANN", MONDAY, date(2026, 3, 3)).json()
    _move(client, created["id"], "submit")

    rejected = _move(_as(kwame), created["id"], "reject", "Examinations that week").json()
    assert rejected["state"] == "rejected"
    decision = LeaveDecision.objects.get(request_id=created["id"])
    assert (decision.step, decision.outcome, decision.comment) == (
        "manager",
        "rejected",
        "Examinations that week",
    )
    assert balance(asha, LeaveType.objects.get(code="ANN")) == Decimal("10")
    note = Notification.objects.get(recipient=asha.user)
    assert "Examinations that week" in note.body and "No days were taken" in note.body


@pytest.mark.django_db
def test_only_a_draft_can_be_changed(team):
    asha, kwame = team["asha"], team["kwame"]
    _credit(asha, "ANN", 10)
    client = _as(asha)
    created = _request(client, asha, "ANN", MONDAY, date(2026, 3, 3)).json()
    url = f"/api/v1/leave/requests/{created['id']}/"

    changed = client.patch(url, {"to_date": "2026-03-04"}, format="json")
    assert changed.status_code == 200 and changed.json()["days"] == "3.00"
    # Another employee's draft is not theirs to change: it is not even visible to them.
    assert _as(kwame).patch(url, {"to_date": "2026-03-05"}, format="json").status_code == 404

    _move(client, created["id"], "submit")
    assert client.patch(url, {"to_date": "2026-03-06"}, format="json").status_code == 403
    assert client.delete(url).status_code == 403
    # The manager may decide on it but not rewrite it.
    assert _as(kwame).patch(url, {"to_date": "2026-03-06"}, format="json").status_code == 403
    assert LeaveRequest.objects.get(pk=created["id"]).days == Decimal("3.00")


@pytest.mark.django_db
def test_the_contract_sets_the_entitlement(team):
    asha = team["asha"]
    annual, sick = LeaveType.objects.get(code="ANN"), LeaveType.objects.get(code="SIC")
    assert entitlement_days(asha, annual) == Decimal("21") and entitlement_days(asha, sick) == Decimal("14")

    contract = Contract.objects.create(assignment=asha.current_assignment, contract_type="open_ended")
    Entitlement.objects.create(contract=contract, leave_type=annual, annual_days=30)
    Entitlement.objects.create(contract=contract, leave_type=sick, annual_days=10)

    assert entitlement_days(asha, annual) == Decimal("30")
    assert accrue_month(asha, annual, date(2026, 10, 1)).days == Decimal("2.50")
    assert grant_year(asha, sick, 2026)[0].days == Decimal("10.00")
    rows = {r["code"]: r for r in balances_for(asha)}
    assert rows["ANN"]["entitlement"] == Decimal("30") and rows["SIC"]["balance"] == Decimal("10")


@pytest.mark.django_db
def test_the_years_sick_leave_is_granted_once(team, campus, make_user):
    asha = team["asha"]
    sick, annual = LeaveType.objects.get(code="SIC"), LeaveType.objects.get(code="ANN")

    first = grant_year(asha, sick, 2026)
    assert [(r.reason, r.days, r.entry_date) for r in first] == [
        ("accrual", Decimal("14.00"), date(2026, 1, 1))
    ]
    assert grant_year(asha, sick, 2026) == []
    # Annual leave accrues monthly and is left to that job.
    assert grant_year(asha, annual, 2026) == []

    # Three days taken in 2026. The eleven left are not carried into 2027.
    _credit(asha, "SIC", -3, on=date(2026, 6, 1))
    second = grant_year(asha, sick, 2027)
    assert [(r.reason, r.days) for r in second] == [
        ("forfeit", Decimal("-11.00")),
        ("accrual", Decimal("14.00")),
    ]
    assert balance(asha, sick) == Decimal("14.00")

    # Appointed on 6 July: July to December is six months of the year.
    post = Position.objects.create(
        number="LIV-003",
        title="Farm Hand",
        grade=asha.current_assignment.position.grade,
        org_unit=team["unit"],
    )
    roxanne = _person("E0005", "Roxanne", "Williams", campus, post, make_user, start=date(2026, 7, 6))
    granted = grant_year(roxanne, sick, 2026)
    assert [(r.days, r.entry_date) for r in granted] == [(Decimal("7.00"), date(2026, 7, 6))]


@pytest.mark.django_db
def test_an_opening_balance_counts_as_the_years_grant(team):
    from leave.tasks import grant_entitlements

    asha, kwame = team["asha"], team["kwame"]
    sick = LeaveType.objects.get(code="SIC")
    _credit(asha, "SIC", 9, on=date.today().replace(month=1, day=1))

    created = grant_entitlements()
    # Asha brought her balance over at migration; Kwame and Natasha receive the grant.
    assert created == 2
    assert balance(asha, sick) == Decimal("9") and balance(kwame, sick) == Decimal("14")
    assert grant_entitlements() == 0


@pytest.mark.django_db
def test_someone_with_no_role_yet_can_still_ask_for_their_own_leave(employee, seeded):
    """The employee field is limited to the caller's campuses, but a person may always name themselves."""
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    from leave.models import LeaveType

    person = get_user_model().objects.create_user("no.role.yet", password="x" * 14)
    employee.user = person
    employee.save()
    client = APIClient()
    client.force_login(person)
    response = client.post(
        "/api/v1/leave/requests/",
        {
            "employee": employee.id,
            "leave_type": LeaveType.objects.get(code="SPE").id,
            "from_date": "2026-11-02",
            "to_date": "2026-11-02",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
