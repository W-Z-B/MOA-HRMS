"""Item 1.42: the sign-in email changes only once the new address confirms it, and the old one is told."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from iam.models import EmailChange, LoginAttempt

PASSWORD = "Str0ng-Passw0rd-123"  # make_user's
CHANGE = "/api/v1/auth/email/change/"
CONFIRM = "/api/v1/auth/email/confirm/"


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


def _token(message) -> str:
    return re.search(r"/#/confirm-email/(\S+)", message.body).group(1)


def _confirm(token):
    return APIClient().post(CONFIRM, {"token": token}, format="json")


@pytest.fixture
def asha(employee, make_user, campus):
    user = make_user("asha.persaud", "employee", campus=campus)
    user.first_name = "Asha"
    user.email = employee.email = "asha@gsa.example"
    user.save()
    employee.user = user
    employee.save()
    return user


@pytest.mark.django_db
def test_a_person_changes_their_sign_in_email_once_the_new_address_confirms_it(asha, employee, api):
    client = _signed_in(asha)
    wrong = client.post(CHANGE, {"email": "asha.new@gsa.example", "password": "not it"}, format="json")
    assert wrong.status_code == 400 and wrong.json()["code"] == "wrong_password"
    assert LoginAttempt.objects.filter(username="asha.persaud", success=False).count() == 1
    assert not mail.outbox

    asked = client.post(CHANGE, {"email": "Asha.New@GSA.example", "password": PASSWORD}, format="json")
    assert asked.status_code == 200, asked.content
    assert asked.json()["emailed"] and asked.json()["pending"]["new_email"] == "Asha.New@gsa.example"
    link, told = mail.outbox
    assert link.to == ["Asha.New@gsa.example"] and "https://" in link.body and "48 hours" in link.body
    assert told.to == ["asha@gsa.example"] and "As…@gsa.example" in told.body
    assert "You asked" in told.body and "confirm-email" not in told.body
    asha.refresh_from_db()
    assert asha.email == "asha@gsa.example"  # nothing changes until the link is followed
    assert client.get("/api/v1/auth/email/").json()["pending"]["new_email"] == "Asha.New@gsa.example"

    token = _token(link)
    done = _confirm(token)
    assert done.status_code == 200, done.content
    assert done.json() == {
        "detail": "The sign-in email address is now Asha.New@gsa.example.",
        "email": "Asha.New@gsa.example",
    }
    asha.refresh_from_db()
    employee.refresh_from_db()
    assert asha.email == employee.email == "Asha.New@gsa.example"  # the staff record follows
    assert mail.outbox[-1].to == ["asha@gsa.example"] and "has changed" in mail.outbox[-1].subject
    assert _confirm(token).json()["code"] == "expired"  # once only
    changed = AuditLog.objects.get(action="sign_in_email_changed")
    assert changed.before == {"email": "asha@gsa.example"} and changed.after == {
        "email": "Asha.New@gsa.example"
    }
    assert client.get("/api/v1/auth/email/").json() == {"email": "Asha.New@gsa.example", "pending": None}
    history = api.get(f"/api/v1/employees/{employee.pk}/history/")
    assert history.status_code == 200, history.content
    assert "Sign-in email" not in history.content.decode()  # an account event, not the file's story


@pytest.mark.django_db
def test_only_the_latest_link_works_and_only_in_time(asha, make_user, settings):
    client = _signed_in(asha)

    def ask(address):
        return client.post(CHANGE, {"email": address, "password": PASSWORD}, format="json")

    ask("first@gsa.example")
    first = _token(mail.outbox[-2])
    ask("second@gsa.example")
    second = _token(mail.outbox[-2])
    assert _confirm(first).json()["code"] == "expired"  # replaced by the newer request
    EmailChange.objects.filter(new_email="second@gsa.example").update(
        asked_at=timezone.now() - timedelta(hours=settings.EMAIL_CHANGE_HOURS + 1)
    )
    assert _confirm(second).json()["code"] == "expired"
    assert client.get("/api/v1/auth/email/").json()["pending"] is None

    other = make_user("someone.else")
    other.email = "taken@gsa.example"
    other.save()
    taken = ask("TAKEN@gsa.example")
    assert taken.status_code == 409 and taken.json()["code"] == "taken"
    assert ask("asha@gsa.example").json()["code"] == "same"
    assert ask("not an address").status_code == 400

    settings.LOGIN_MAX_FAILURES = 2
    for _ in range(2):
        client.post(CHANGE, {"email": "third@gsa.example", "password": "wrong"}, format="json")
    locked = ask("third@gsa.example")
    assert locked.status_code == 429 and locked.json()["code"] == "too_many_attempts"


@pytest.mark.django_db
def test_hr_asks_with_a_reason_and_the_person_confirms_from_the_new_address(api, asha, hr_officer):
    path = f"/api/v1/accounts/{asha.pk}/email/"
    assert api.post(path, {"email": "asha.hr@gsa.example"}, format="json").status_code == 400  # no reason
    asked = api.post(
        path, {"email": "asha.hr@gsa.example", "reason": "Her old mailbox was closed"}, format="json"
    )
    assert asked.status_code == 200, asked.content
    assert asked.json()["pending_email"] == "asha.hr@gsa.example" and asked.json()["emailed"] is True
    assert "Human Resources asked" in mail.outbox[-1].body
    row = AuditLog.objects.get(action="email_change_asked")
    assert row.reason == "Her old mailbox was closed" and row.actor == hr_officer
    assert row.after == {"new_email": "asha.hr@gsa.example", "asked_by_the_person": False}
    listed = api.get("/api/v1/accounts/?q=asha").json()["results"]
    assert listed[0]["pending_email"] == "asha.hr@gsa.example"
    own = api.post(f"/api/v1/accounts/{hr_officer.pk}/email/", {"email": "x@gsa.example", "reason": "r"})
    assert own.status_code in (403, 404)  # one's own address is changed from My account, with a password

    asha.is_active = False
    asha.save()
    assert _confirm(_token(mail.outbox[-2])).json()["code"] == "switched_off"
    off = api.post(path, {"email": "asha.again@gsa.example", "reason": "Try"}, format="json")
    assert off.status_code == 409 and off.json()["code"] == "switched_off"


@pytest.mark.django_db
def test_old_requests_go_with_the_sign_in_records(asha, seeded):
    from privacy.retention import purge

    _signed_in(asha).post(CHANGE, {"email": "asha.new@gsa.example", "password": PASSWORD}, format="json")
    EmailChange.objects.update(asked_at=timezone.now() - timedelta(days=400))
    assert purge()["sign-in-records"] >= 1 and not EmailChange.objects.exists()
