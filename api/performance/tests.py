"""Item H-M03: review cycles, goals, and the self-assessment plus manager-assessment workflow."""

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

TODAY = date.today


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def manager(campus, unit, make_user):
    from people.models import Employee

    person = Employee.objects.create(
        employee_no="E0500",
        first_name="Natasha",
        last_name="Khan",
        date_of_birth=date(1975, 1, 1),
        campus=campus,
        user=make_user("natasha.khan", "supervisor", campus=campus),
    )
    unit.head = person
    unit.save()
    return person


@pytest.fixture
def staffer(employee, unit, manager, make_user, campus):
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


@pytest.fixture
def cycle(hr_officer):
    from performance.models import AppraisalCycle

    return AppraisalCycle.objects.create(
        name="Annual appraisal", year=2026, starts=date(2026, 1, 1), ends=date(2026, 12, 31), is_open=True
    )


def _start(client, employee, cycle, kind="annual"):
    return client.post(
        "/api/v1/performance/appraisals/start/",
        {"employee": employee.id, "cycle": cycle.id, "kind": kind},
        format="json",
    )


@pytest.mark.django_db
def test_an_appraisal_goes_from_self_assessment_to_signed_off(api, staffer, manager, cycle, hr_manager):
    from notifications.models import Notification
    from performance.models import Appraisal

    opened = _start(api, staffer, cycle)
    assert opened.status_code == 201, opened.content
    body = opened.json()
    assert body["state"] == "draft" and body["manager_name"] == "Natasha Khan"
    assert body["allowed_actions"] == []  # the employee has not written anything yet
    appraisal_id = body["id"]
    url = f"/api/v1/performance/appraisals/{appraisal_id}"

    mine = _signed_in(staffer.user)
    refused = mine.post(f"{url}/transition/", {"action": "submit_self_assessment"})
    assert refused.status_code == 409 and refused.json()["code"] == "no_self_assessment"

    denied = mine.patch(f"{url}/manager-assessment/", {"manager_assessment": "x", "overall_rating": 4})
    assert denied.status_code == 403

    written = mine.patch(f"{url}/self-assessment/", {"self_assessment": "I met my targets this year."})
    assert written.status_code == 200 and written.json()["self_assessment"].startswith("I met")
    submitted = mine.post(f"{url}/transition/", {"action": "submit_self_assessment"})
    assert submitted.status_code == 200 and submitted.json()["state"] == "self_assessed"
    assert Notification.objects.filter(title__contains="completed their self-assessment").exists()

    locked = mine.patch(f"{url}/self-assessment/", {"self_assessment": "Changed my mind"})
    assert locked.status_code == 409 and locked.json()["code"] == "not_draft"

    rates = _signed_in(manager.user)
    signs = _signed_in(hr_manager)
    too_soon = signs.post(f"{url}/transition/", {"action": "sign_off"})
    assert too_soon.status_code == 409

    rated = rates.patch(
        f"{url}/manager-assessment/",
        {
            "manager_assessment": "Strong year, exceeded expectations.",
            "overall_rating": 5,
            "outcome": "increment",
        },
    )
    assert rated.status_code == 200
    moved = rates.post(f"{url}/transition/", {"action": "rate"})
    assert moved.status_code == 200 and moved.json()["state"] == "rated"
    assert Notification.objects.filter(title="Your appraisal has been rated").exists()

    cannot_sign = rates.post(f"{url}/transition/", {"action": "sign_off"})
    assert cannot_sign.status_code == 403

    signed = signs.post(f"{url}/transition/", {"action": "sign_off"})
    assert signed.status_code == 200 and signed.json()["state"] == "signed"
    final = Appraisal.objects.get(pk=appraisal_id)
    assert final.signed_at is not None and final.outcome == "increment"

    reopened = signs.post(f"{url}/transition/", {"action": "reopen", "comment": "Figures were revised"})
    assert reopened.status_code == 200 and reopened.json()["state"] == "self_assessed"


@pytest.mark.django_db
def test_only_one_appraisal_of_a_kind_per_cycle(api, staffer, cycle):
    first = _start(api, staffer, cycle)
    assert first.status_code == 201
    again = _start(api, staffer, cycle)
    assert again.status_code == 409 and again.json()["code"] == "already_open"


@pytest.mark.django_db
def test_an_employee_sees_only_their_own_appraisal_and_a_manager_their_team(
    api, staffer, manager, cycle, make_user
):
    opened = _start(api, staffer, cycle).json()

    mine = _signed_in(staffer.user)
    seen = mine.get("/api/v1/performance/appraisals/").json()
    assert seen["count"] == 1 and seen["results"][0]["id"] == opened["id"]
    assert seen["results"][0]["is_mine"] is True

    rates = _signed_in(manager.user)
    team = rates.get("/api/v1/performance/appraisals/").json()
    assert team["count"] == 1 and team["results"][0]["is_rated_by_me"] is True

    bystander = _signed_in(make_user("someone.else", "employee"))
    assert bystander.get("/api/v1/performance/appraisals/").json()["count"] == 0


@pytest.mark.django_db
def test_goals_are_set_by_the_manager_or_hr_and_seen_by_the_employee(api, staffer, manager, cycle):
    goal = api.post(
        "/api/v1/performance/goals/",
        {"employee": staffer.id, "cycle": cycle.id, "title": "Finish the farm survey", "weight": 60},
        format="json",
    )
    assert goal.status_code == 201, goal.content

    rates = _signed_in(manager.user)
    second = rates.post(
        "/api/v1/performance/goals/",
        {"employee": staffer.id, "cycle": cycle.id, "title": "Mentor a junior instructor", "weight": 40},
        format="json",
    )
    assert second.status_code == 201

    mine = _signed_in(staffer.user)
    denied = mine.post(
        "/api/v1/performance/goals/",
        {"employee": staffer.id, "cycle": cycle.id, "title": "Set my own goal"},
        format="json",
    )
    assert denied.status_code == 403

    seen = mine.get("/api/v1/performance/goals/").json()
    assert seen["count"] == 2

    opened = _start(api, staffer, cycle).json()
    assert len(opened["goals"]) == 2


@pytest.mark.django_db
def test_the_nightly_jobs_remind_of_cycles_ending_and_overdue(api, staffer, manager, cycle):
    from notifications.models import Notification
    from performance.tasks import alert_cycle_ending, alert_overdue

    cycle.ends = TODAY() + timedelta(days=30)
    cycle.save()
    opened = _start(api, staffer, cycle).json()

    assert alert_cycle_ending(TODAY()) == 2  # the employee and their manager
    assert Notification.objects.filter(title__contains="ends in 30 days").exists()
    assert alert_cycle_ending(TODAY()) == 0  # same horizon, same dedupe key: not sent twice
    assert alert_overdue(TODAY()) == 0  # not due yet

    cycle.ends = TODAY() - timedelta(days=1)
    cycle.save()
    assert alert_overdue(TODAY()) == 1
    assert Notification.objects.filter(title=f"Appraisal overdue: {staffer.full_name}").exists()

    from performance.models import Appraisal

    Appraisal.objects.filter(pk=opened["id"]).update(state=Appraisal.State.SIGNED)
    assert alert_overdue(TODAY()) == 0
