import pyotp
import pytest
from rest_framework.test import APIClient

from iam.models import TotpDevice


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
