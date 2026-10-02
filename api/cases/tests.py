"""Item 1.15: the discipline and grievance register, open to named officers only, with fair steps."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from audit.models import AuditLog

OPENED = date(2026, 10, 1)


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


def _open(client, employee, kind="discipline", summary="Absent without leave on 28 and 29 September"):
    body = {"kind": kind, "employee": employee.id, "summary": summary, "opened_on": OPENED.isoformat()}
    return client.post("/api/v1/cases/", body, format="json")


def _entry(client, case_id, kind, on=date(2026, 10, 2), text="Recorded"):
    return client.post(
        f"/api/v1/cases/{case_id}/entries/", {"kind": kind, "on": on.isoformat(), "text": text}, format="json"
    )


def _decide(client, case_id, outcome, on=date(2026, 10, 20)):
    body = {"outcome": outcome, "reasons": "The absence was not explained", "decided_on": on.isoformat()}
    return client.post(f"/api/v1/cases/{case_id}/decide/", body, format="json")


@pytest.mark.django_db
def test_a_case_is_seen_only_by_the_hr_manager_and_those_named_on_it(
    api, employee, make_user, campus, hr_officer
):
    from people.models import Employee

    opened = _open(api, employee)
    assert opened.status_code == 201, opened.content
    case = opened.json()
    assert case["reference"] == "DC-2026-001" and case["state"] == "open"
    assert [o["part"] for o in case["officers"]] == ["Opened the case"]

    other_officer = _signed_in(make_user("other.officer", "hr_officer", campus=campus))
    assert other_officer.get("/api/v1/cases/").json()["count"] == 0
    assert other_officer.get(f"/api/v1/cases/{case['id']}/").status_code == 404
    assert (
        _signed_in(make_user("hr.head", "hr_manager")).get(f"/api/v1/cases/{case['id']}/").status_code == 200
    )

    supervisor = make_user("unit.head", "supervisor", campus=campus)
    named = api.post(
        f"/api/v1/cases/{case['id']}/officers/",
        {"user": supervisor.id, "part": "Chair of the hearing"},
        format="json",
    )
    assert [o["part"] for o in named.json()["officers"]] == ["Opened the case", "Chair of the hearing"]
    assert _signed_in(supervisor).get(f"/api/v1/cases/{case['id']}/").json()["summary"].startswith("Absent")

    employee.user = make_user("asha.persaud", "employee", campus=campus)
    employee.save()
    refused = api.post(
        f"/api/v1/cases/{case['id']}/officers/", {"user": employee.user.id, "part": "x"}, format="json"
    )
    assert refused.status_code == 403 and refused.json()["code"] == "own"
    assert _signed_in(employee.user).get("/api/v1/cases/").json()["count"] == 0

    hr_subject = Employee.objects.create(
        employee_no="E0050",
        first_name="Hema",
        last_name="Officer",
        date_of_birth=date(1980, 1, 1),
        campus=campus,
        user=hr_officer,
    )
    assert _open(api, hr_subject).json()["code"] == "own"  # nobody opens a case about themselves

    rows = AuditLog.objects.filter(entity="cases.case")
    assert {row.action for row in rows} == {"case_opened", "case_officer_named"}
    assert all(
        row.subject is None and "summary" not in (row.after or {}) for row in rows
    )  # never in the file


@pytest.mark.django_db
def test_fair_steps_come_before_any_action_and_a_hearing_before_a_serious_one(api, employee):
    case_id = _open(api, employee).json()["id"]
    assert _decide(api, case_id, "written_warning").json()["code"] == "unfair"
    assert _decide(api, case_id, "upheld").json()["code"] == "wrong_outcome"
    _entry(api, case_id, "allegation", text="Letter of 2 October setting out the allegation")
    dismissal = _decide(api, case_id, "dismissal")
    assert dismissal.json() == {
        "code": "unfair",
        "detail": "Before a dismissal, the employee is heard: record their response, or the hearing.",
    }
    _entry(api, case_id, "hearing", on=date(2026, 10, 15), text="Heard with a union representative present")
    decided = _decide(api, case_id, "final_warning").json()
    assert decided["state"] == "decided" and decided["outcome_name"] == "Final written warning"
    assert decided["lapses_on"] == "2028-10-20" and decided["fair_steps"] == {
        "allegation": True,
        "answered": True,
    }
    assert decided["decided_by_name"] == "hr.officer"


@pytest.mark.django_db
def test_an_appeal_is_lodged_in_time_and_heard_by_someone_else(api, employee, make_user):
    case_id = _open(api, employee).json()["id"]
    _entry(api, case_id, "allegation")
    _decide(api, case_id, "written_warning", on=date(2026, 10, 20))
    late = api.post(
        f"/api/v1/cases/{case_id}/appeal/", {"lodged_on": "2026-11-20", "grounds": "Unfair"}, format="json"
    )
    assert late.json()["code"] == "late"
    lodged = api.post(
        f"/api/v1/cases/{case_id}/appeal/",
        {"lodged_on": "2026-10-30", "grounds": "I was sick"},
        format="json",
    )
    assert lodged.json()["state"] == "appeal"
    body = {
        "outcome": "overturned",
        "reasons": "A sick note was given at the time",
        "decided_on": "2026-11-05",
    }
    same = api.post(f"/api/v1/cases/{case_id}/appeal-decision/", body, format="json")
    assert same.json()["code"] == "not_independent"
    manager = _signed_in(make_user("hr.head", "hr_manager"))
    heard = manager.post(f"/api/v1/cases/{case_id}/appeal-decision/", body, format="json").json()
    assert (
        heard["appeal_outcome_name"] == "Decision overturned" and heard["appeal_decided_by_name"] == "hr.head"
    )
    closed = manager.post(f"/api/v1/cases/{case_id}/close/").json()
    assert closed["state"] == "closed"
    assert _entry(api, case_id, "note").json()["code"] == "closed"


@pytest.mark.django_db
def test_a_grievance_has_its_own_reference_and_outcomes(api, employee, make_user, campus):
    grievance = _open(api, employee, kind="grievance", summary="Overtime not paid for September").json()
    assert grievance["reference"] == "GR-2026-001"
    assert _decide(api, grievance["id"], "written_warning").json()["code"] == "wrong_outcome"
    assert _decide(api, grievance["id"], "partly_upheld").json()["outcome_name"] == "Grievance partly upheld"
    assert _open(api, employee).json()["reference"] == "DC-2026-001"  # discipline numbers apart
    plain = _signed_in(make_user("someone", "employee", campus=campus))
    assert _open(plain, employee).status_code == 403  # Human Resources opens cases
