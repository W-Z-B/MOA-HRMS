"""Public holidays (item 1.25): the rules, the seeded days, and the screen's API."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from audit.models import AuditLog
from core import holidays
from core.models import PublicHoliday
from leave.services import working_days


def signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


def test_easter_and_the_days_that_follow_from_it():
    assert [holidays.easter(y) for y in (2024, 2025, 2026, 2027)] == [
        date(2024, 3, 31),
        date(2025, 4, 20),
        date(2026, 4, 5),
        date(2027, 3, 28),
    ]
    named = {e.name: e.day for e in holidays.by_rule(2026)}
    assert named["Good Friday"] == date(2026, 4, 3) and named["Easter Monday"] == date(2026, 4, 6)
    assert named["CARICOM Day"] == date(2026, 7, 6) and holidays.first_monday(2027, 7) == date(2027, 7, 5)
    assert named["Labour Day"] == date(2026, 5, 1)
    assert [e.name for e in holidays.expected(2026) if e.day is None] == [
        "Phagwah",
        "Eid ul-Adha",
        "Youman Nabi",
        "Deepavali",
    ]


@pytest.mark.django_db
def test_labour_day_is_seeded_so_leave_over_it_counts_right(seeded):
    assert PublicHoliday.objects.get(date=date(2026, 5, 1)).name == "Labour Day"
    # Monday 27 April to Friday 1 May 2026: five weekdays, Labour Day among them.
    assert working_days(date(2026, 4, 27), date(2026, 5, 1)) == 4
    assert PublicHoliday.objects.filter(date=date(2027, 3, 26), name="Good Friday").exists()


@pytest.mark.django_db
def test_the_year_is_checked_against_guyanas_holidays(hr_manager, api):
    manager = signed_in(hr_manager)
    calendar = api.get("/api/v1/holidays/calendar/", {"year": 2026}).json()  # everyone signed in may read
    rows = {row["name"]: row for row in calendar["expected"]}
    assert rows["Labour Day"]["on_file"]["weekday"] == "Friday"
    assert rows["Phagwah"]["date"] is None and rows["Phagwah"]["on_file"] is None
    assert rows["Good Friday"]["rule"] == "Two days before Easter Sunday"

    added = manager.post("/api/v1/holidays/", {"date": "2026-03-03", "name": "Phagwah (Holi)"}, format="json")
    assert added.status_code == 201
    substitute = manager.post(
        "/api/v1/holidays/", {"date": "2026-11-09", "name": "Deepavali Holiday"}, format="json"
    )
    manager.post("/api/v1/holidays/", {"date": "2026-11-08", "name": "Deepavali"}, format="json")
    calendar = manager.get("/api/v1/holidays/calendar/", {"year": 2026}).json()
    rows = {row["name"]: row for row in calendar["expected"]}
    assert rows["Phagwah"]["on_file"]["date"] == "2026-03-03"
    assert rows["Deepavali"]["on_file"]["date"] == "2026-11-08"
    assert [h["name"] for h in calendar["others"]] == ["Deepavali Holiday"]
    assert "Deepavali" in {h["name"] for h in calendar["sundays"]}

    twice = manager.post("/api/v1/holidays/", {"date": "2026-03-03", "name": "Again"}, format="json")
    assert twice.status_code == 400
    assert (
        api.post("/api/v1/holidays/", {"date": "2026-06-01", "name": "x"}, format="json").status_code == 403
    )
    next_year = manager.post(
        "/api/v1/holidays/", {"date": "2027-03-22", "name": "Phagwah"}, format="json"
    ).json()
    renamed = manager.patch(f"/api/v1/holidays/{next_year['id']}/", {"name": "Phagwah (Holi)"}, format="json")
    assert renamed.status_code == 200
    assert (
        manager.delete(
            f"/api/v1/holidays/{substitute.json()['id']}/",
            {"change_reason": "Gazette corrected"},
            format="json",
        ).status_code
        == 204
    )
    assert [h["date"] for h in api.get("/api/v1/holidays/", {"year": 2027}).json()][:1] == ["2027-01-01"]
    assert AuditLog.objects.filter(entity="core.publicholiday", action="create").count() == 4
    bad = api.get("/api/v1/holidays/", {"year": "soon"})
    assert bad.status_code == 400 and bad.json()["year"] == ["Give a year such as 2027."]


@pytest.mark.django_db
def test_a_leave_types_code_never_changes(hr_manager, seeded):
    from leave.models import LeaveType

    manager = signed_in(hr_manager)
    annual = LeaveType.objects.get(code="ANN")
    refused = manager.patch(f"/api/v1/leave/types/{annual.id}/", {"code": "ANNUAL"}, format="json")
    assert refused.status_code == 400 and "never changes" in refused.json()["code"][0]
    assert (
        manager.patch(
            f"/api/v1/leave/types/{annual.id}/", {"name": "Annual leave (vacation)"}, format="json"
        ).status_code
        == 200
    )
