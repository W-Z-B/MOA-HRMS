"""Signed-in sessions: listed, ended from another device, and ended when idle or too old (item 1.28)."""

import time

import pytest
from rest_framework.test import APIClient

from audit.models import AuditLog
from iam.models import UserSession
from iam.sessions import LAST_ACTIVITY, SIGNED_IN_AT, describe_device

PASSWORD = "Str0ng-Passw0rd-123"
ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36"
)
WINDOWS_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36 Edg/126.0"
)


def device(username: str, agent: str = ANDROID_CHROME, address: str = "190.80.1.2") -> APIClient:
    client = APIClient(HTTP_USER_AGENT=agent, HTTP_X_REAL_IP=address)
    response = client.post("/api/v1/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    return client


def age_session(client: APIClient, **seconds_ago: float) -> None:
    session = client.session
    for key, ago in seconds_ago.items():
        session[key] = time.time() - ago
    session.save()


@pytest.mark.django_db
def test_sign_in_records_the_session_and_lists_it_as_this_device(hr_officer):
    phone = device("hr.officer")
    rows = phone.get("/api/v1/auth/sessions/").json()
    assert len(rows) == 1
    assert rows[0]["current"] is True
    assert rows[0]["device"] == "Chrome on Android"
    assert rows[0]["ip"] == "190.80.1.2"


@pytest.mark.django_db
def test_ending_another_session_signs_that_device_out(hr_officer):
    phone = device("hr.officer")
    laptop = device("hr.officer", WINDOWS_EDGE, "190.80.9.9")
    rows = phone.get("/api/v1/auth/sessions/").json()
    other = next(row for row in rows if not row["current"])
    assert other["device"] == "Edge on Windows"

    assert phone.delete(f"/api/v1/auth/sessions/{other['id']}/").status_code == 204
    refused = laptop.get("/api/v1/auth/me/")
    assert refused.status_code == 403 and refused.json()["code"] == "not_authenticated"
    assert phone.get("/api/v1/auth/me/").status_code == 200
    assert AuditLog.objects.filter(action="session_ended", actor=hr_officer).exists()


@pytest.mark.django_db
def test_people_cannot_end_someone_elses_session_or_their_own_here(hr_officer, make_user, campus):
    make_user("other.person", "employee", campus=campus)
    mine = device("hr.officer")
    theirs = device("other.person")
    their_id = theirs.get("/api/v1/auth/sessions/").json()[0]["id"]
    my_id = mine.get("/api/v1/auth/sessions/").json()[0]["id"]

    assert mine.delete(f"/api/v1/auth/sessions/{their_id}/").status_code == 404
    own = mine.delete(f"/api/v1/auth/sessions/{my_id}/")
    assert own.status_code == 409 and own.json()["code"] == "current_session"
    assert theirs.get("/api/v1/auth/me/").status_code == 200


@pytest.mark.django_db
def test_sign_out_everywhere_else(hr_officer):
    phone = device("hr.officer")
    laptop = device("hr.officer", WINDOWS_EDGE)
    tablet = device("hr.officer")
    assert phone.post("/api/v1/auth/sessions/end-others/").json() == {"ended": 2}
    assert laptop.get("/api/v1/auth/me/").status_code == 403
    assert tablet.get("/api/v1/auth/me/").status_code == 403
    assert phone.get("/api/v1/auth/me/").status_code == 200
    assert UserSession.objects.filter(user=hr_officer).count() == 1


@pytest.mark.django_db
def test_an_idle_session_ends_with_the_reason(hr_officer, settings):
    settings.SESSION_IDLE_MINUTES = 30
    phone = device("hr.officer")
    age_session(phone, **{LAST_ACTIVITY: 31 * 60})
    ended = phone.get("/api/v1/employees/")
    assert ended.status_code == 401
    assert ended.json() == {
        "code": "session_expired",
        "detail": "You were signed out after 30 minutes without activity.",
    }
    assert not UserSession.objects.filter(user=hr_officer).exists()
    assert phone.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.django_db
def test_a_busy_session_still_ends_at_the_absolute_limit(hr_officer, settings):
    settings.SESSION_COOKIE_AGE = 8 * 60 * 60
    phone = device("hr.officer")
    age_session(phone, **{SIGNED_IN_AT: 8 * 60 * 60 + 5, LAST_ACTIVITY: 10})
    ended = phone.get("/api/v1/employees/")
    assert ended.status_code == 401
    assert "time limit" in ended.json()["detail"]


@pytest.mark.django_db
def test_activity_keeps_a_session_alive_and_older_sessions_join_the_list(hr_officer):
    phone = device("hr.officer")
    UserSession.objects.all().delete()  # as for a session that signed in before the list existed
    session = phone.session
    del session[LAST_ACTIVITY]
    session.save()
    assert phone.get("/api/v1/employees/").status_code == 200
    assert UserSession.objects.filter(user=hr_officer).count() == 1


@pytest.mark.django_db
def test_signing_out_removes_the_session_from_the_list(hr_officer):
    phone = device("hr.officer")
    assert phone.post("/api/v1/auth/logout/").status_code == 204
    assert not UserSession.objects.exists()


def test_devices_are_described_in_plain_words():
    assert describe_device(ANDROID_CHROME) == "Chrome on Android"
    assert describe_device(WINDOWS_EDGE) == "Edge on Windows"
    assert describe_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1") == (
        "Safari on iPhone or iPad"
    )
    assert describe_device("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0") == (
        "Firefox on Linux"
    )
    assert describe_device("") == "Unknown device"
