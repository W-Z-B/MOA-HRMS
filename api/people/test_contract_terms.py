"""Contract terms: hours, hourly rate, notice, entitlements, and who may read the pay."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from leave.models import LeaveType
from org.models import Position
from people.models import Assignment, Contract
from people.services import hourly_rate


@pytest.fixture
def contract(employee, unit):
    assignment = Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="contract",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 12, 31),
    )
    return Contract.objects.create(
        assignment=assignment,
        contract_type="fixed_term",
        term_months=12,
        hours_per_week=40,
        notice_period_days=30,
    )


def _login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_the_hourly_rate_comes_from_the_contract_or_the_grade(contract):
    # Grade GS5 pays 250,000 a month: 3,000,000 a year over 52 weeks of 40 hours.
    assert hourly_rate(contract) == Decimal("1442.31")
    contract.hourly_rate = Decimal("1800")
    assert hourly_rate(contract) == Decimal("1800")
    contract.hourly_rate, contract.hours_per_week = None, None
    assert hourly_rate(contract) is None


@pytest.mark.django_db
def test_hr_records_the_terms_and_the_entitlements(contract, api):
    saved = api.patch(
        f"/api/v1/contracts/{contract.id}/",
        {"hourly_rate": "1650.00", "hours_per_week": "37.5", "other_terms": "Housing allowance"},
        format="json",
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["hourly_rate"] == "1650.00" and saved.json()["hourly_rate_effective"] == "1650.00"
    assert api.patch(f"/api/v1/contracts/{contract.id}/", {"hours_per_week": "0"}).status_code == 400

    sick = LeaveType.objects.get(code="SIC")
    row = {"contract": contract.id, "leave_type": sick.id, "annual_days": "10"}
    assert api.post("/api/v1/leave/entitlements/", row, format="json").status_code == 201
    # One figure for each leave type in a contract.
    assert api.post("/api/v1/leave/entitlements/", row, format="json").status_code == 400
    listed = api.get(f"/api/v1/leave/entitlements/?contract={contract.id}").json()["results"]
    assert [(r["leave_type_code"], r["annual_days"]) for r in listed] == [("SIC", "10.00")]


@pytest.mark.django_db
def test_a_supervisor_reads_the_terms_without_the_pay(contract, make_user, campus):
    contract.hourly_rate = Decimal("1650")
    contract.save()
    shown = _login(make_user("hod", "supervisor", campus=campus)).get(f"/api/v1/contracts/{contract.id}/")
    assert shown.status_code == 200
    body = shown.json()
    assert body["hourly_rate"] is None and body["hourly_rate_effective"] is None
    assert body["hours_per_week"] == "40.0" and body["notice_period_days"] == 30

    finance = _login(make_user("fin", "finance"))
    session = finance.session
    session["mfa_verified"] = True
    session.save()
    assert finance.get(f"/api/v1/contracts/{contract.id}/").json()["hourly_rate"] == "1650.00"


@pytest.mark.django_db
def test_an_employee_reads_their_own_terms(contract, employee, make_user, campus):
    unlinked = _login(make_user("nobody", "employee", campus=campus))
    assert unlinked.get("/api/v1/contracts/mine/").status_code == 404
    # The contract list stays closed to employees; their own terms have their own door.
    assert unlinked.get("/api/v1/contracts/").status_code == 403

    employee.user = make_user("asha", "employee", campus=campus)
    employee.save()
    mine = _login(employee.user).get("/api/v1/contracts/mine/")
    assert mine.status_code == 200, mine.content
    body = mine.json()
    assert (body["name"], body["position"], body["unit"]) == (
        "Asha Persaud",
        "Livestock Instructor",
        "Livestock Unit",
    )
    assert body["appointment_type"] == "Contract" and body["end_date"] == "2026-12-31"
    terms = body["contract"]
    assert (terms["hourly_rate"], terms["hourly_rate_is_set"], terms["hours_per_week"]) == (
        1442.31,
        False,
        40,
    )
    assert [(e["code"], e["annual_days"]) for e in body["entitlements"]] == [("ANN", 21), ("SIC", 14)]
