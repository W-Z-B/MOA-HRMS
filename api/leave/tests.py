from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from leave.models import LeaveLedger, LeaveRequest, LeaveType
from leave.services import balance, working_days


@pytest.mark.django_db
def test_working_days_skip_weekends_and_public_holidays(seeded):
    # 21 to 27 December 2026: Mon 21 to Fri 25 = 5 weekdays, Christmas Day 25 Dec is a holiday.
    assert working_days(date(2026, 12, 21), date(2026, 12, 27)) == 4


@pytest.mark.django_db
def test_balance_is_the_sum_of_the_ledger(employee, seeded):
    annual = LeaveType.objects.get(code="ANN")
    LeaveLedger.objects.create(
        employee=employee, leave_type=annual, entry_date=date(2026, 1, 1), days=10, reason="opening"
    )
    LeaveLedger.objects.create(
        employee=employee,
        leave_type=annual,
        entry_date=date(2026, 2, 1),
        days=Decimal("1.75"),
        reason="accrual",
    )
    assert balance(employee, annual) == Decimal("11.75")


@pytest.mark.django_db
def test_leave_request_workflow_end_to_end(employee, make_user, campus, seeded):
    annual = LeaveType.objects.get(code="ANN")
    LeaveLedger.objects.create(
        employee=employee, leave_type=annual, entry_date=date(2026, 1, 1), days=12, reason="opening"
    )
    owner = make_user("asha", "employee", campus=campus)
    employee.user = owner
    employee.save()
    supervisor = make_user("hod", "supervisor", campus=campus)
    hr = make_user("hr2", "hr_officer", campus=campus)

    client = APIClient()
    client.force_login(owner)
    created = client.post(
        "/api/v1/leave/requests/",
        {
            "employee": employee.id,
            "leave_type": annual.id,
            "from_date": "2026-11-02",
            "to_date": "2026-11-06",
            "reason": "Family",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    request_id = created.json()["id"]
    assert created.json()["days"] == "5.00" and created.json()["allowed_actions"] == ["submit", "cancel"]

    assert (
        client.post(f"/api/v1/leave/requests/{request_id}/transition/", {"action": "submit"}).status_code
        == 200
    )
    # The owner cannot approve their own request.
    denied = client.post(f"/api/v1/leave/requests/{request_id}/transition/", {"action": "approve"})
    assert denied.status_code == 403 and denied.json()["code"] == "forbidden_actor"

    client.force_login(supervisor)
    assert (
        client.post(f"/api/v1/leave/requests/{request_id}/transition/", {"action": "approve"}).status_code
        == 200
    )
    client.force_login(hr)
    final = client.post(f"/api/v1/leave/requests/{request_id}/transition/", {"action": "approve"})
    assert final.status_code == 200 and final.json()["state"] == "approved"

    assert balance(employee, annual) == Decimal("7.00")
    assert LeaveRequest.objects.get(pk=request_id).state == "approved"
    # Approving twice is an invalid transition, reported as a conflict.
    again = client.post(f"/api/v1/leave/requests/{request_id}/transition/", {"action": "approve"})
    assert again.status_code == 409 and again.json()["code"] == "invalid_transition"


@pytest.mark.django_db
def test_reject_requires_comment(employee, make_user, campus, seeded, api):
    annual = LeaveType.objects.get(code="ANN")
    req = LeaveRequest.objects.create(
        employee=employee,
        leave_type=annual,
        from_date=date(2026, 11, 2),
        to_date=date(2026, 11, 3),
        days=2,
        state="submitted",
    )
    supervisor = make_user("hod2", "supervisor", campus=campus)
    client = APIClient()
    client.force_login(supervisor)
    response = client.post(f"/api/v1/leave/requests/{req.id}/transition/", {"action": "reject"})
    assert response.status_code == 409 and response.json()["code"] == "comment_required"
    response = client.post(
        f"/api/v1/leave/requests/{req.id}/transition/", {"action": "reject", "comment": "Term time"}
    )
    assert response.status_code == 200 and response.json()["state"] == "rejected"


@pytest.mark.django_db
def test_monthly_accrual_is_idempotent(employee, seeded):
    from leave.services import accrue_month

    annual = LeaveType.objects.get(code="ANN")
    first = accrue_month(employee, annual, date(2026, 10, 1))
    second = accrue_month(employee, annual, date(2026, 10, 15))
    assert first is not None and second is None
    assert balance(employee, annual) == Decimal("1.75")
