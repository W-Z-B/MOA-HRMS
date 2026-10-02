import pyotp
import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIClient

from iam.models import TotpDevice
from iam.services import role_codes, scope_queryset
from integration.auth import ServiceUser
from integration.models import ServiceClient
from people.models import Employee


@pytest.mark.django_db
def test_scoping_fails_closed_for_callers_who_are_not_people(employee):
    """An anonymous caller or a service key never reaches personnel rows through scope_queryset."""
    client = ServiceClient(name="srms", scopes=["staff:read"])
    for caller in (AnonymousUser(), ServiceUser(client)):
        assert role_codes(caller) == set()
        assert list(scope_queryset(caller, Employee.objects.all())) == []


@pytest.mark.django_db
def test_login_logout_and_me(hr_officer):
    client = APIClient()
    bad = client.post("/api/v1/auth/login/", {"username": "hr.officer", "password": "wrong"}, format="json")
    assert bad.status_code == 401
    ok = client.post(
        "/api/v1/auth/login/", {"username": "hr.officer", "password": "Str0ng-Passw0rd-123"}, format="json"
    )
    assert ok.status_code == 200
    assert ok.json()["roles"] == ["hr_officer"] and ok.json()["mfa_required"] is False
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert client.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.django_db
def test_privileged_role_must_enrol_and_verify_totp(hr_manager):
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/", {"username": "hr.manager", "password": "Str0ng-Passw0rd-123"}, format="json"
    )
    assert login.json()["mfa_required"] is True and login.json()["mfa_verified"] is False
    assert client.get("/api/v1/org/campuses/").status_code == 403

    enrol = client.post("/api/v1/auth/mfa/enrol/")
    assert enrol.status_code == 200 and "otpauth://" in enrol.json()["provisioning_uri"]
    secret = TotpDevice.objects.get(user=hr_manager).secret

    wrong = client.post("/api/v1/auth/mfa/verify/", {"code": "000000"}, format="json")
    assert wrong.status_code == 400
    good = client.post("/api/v1/auth/mfa/verify/", {"code": pyotp.TOTP(secret).now()}, format="json")
    assert good.status_code == 200 and good.json()["mfa_verified"] is True
    assert TotpDevice.objects.get(user=hr_manager).is_confirmed
    assert client.get("/api/v1/org/campuses/").status_code == 200


@pytest.mark.django_db
def test_anonymous_is_rejected(db):
    assert APIClient().get("/api/v1/employees/").status_code == 403


@pytest.mark.django_db
def test_account_locks_after_repeated_failures(hr_officer, settings):
    settings.LOGIN_MAX_FAILURES = 3
    client = APIClient()
    for _ in range(3):
        bad = client.post(
            "/api/v1/auth/login/", {"username": "hr.officer", "password": "wrong"}, format="json"
        )
        assert bad.status_code == 401
    locked = client.post(
        "/api/v1/auth/login/", {"username": "hr.officer", "password": "Str0ng-Passw0rd-123"}, format="json"
    )
    assert locked.status_code == 423 and locked.json()["code"] == "locked_out"
    # Another account is unaffected.
    assert (
        client.post(
            "/api/v1/auth/login/", {"username": "someone.else", "password": "x"}, format="json"
        ).status_code
        == 401
    )


@pytest.mark.django_db
def test_admin_needs_the_verified_web_sign_in(make_user):
    """The admin has no password form of its own and refuses a superuser who has not passed MFA."""
    admin_user = make_user("root.admin", superuser=True)
    client = APIClient()
    client.force_login(admin_user)
    assert client.get("/admin/").status_code == 302  # signed in, but no authenticator code yet

    login_form = client.get("/admin/login/")
    assert login_form.status_code == 302 and login_form["Location"] == "/"

    session = client.session
    session["mfa_verified"] = True
    session.save()
    assert client.get("/admin/").status_code == 200
