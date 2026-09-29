import pytest


@pytest.mark.django_db
def test_positions_report_vacancy(api, unit):
    response = api.get("/api/v1/org/positions/", {"org_unit": unit.id})
    assert response.status_code == 200
    rows = response.json()["results"]
    assert {r["number"] for r in rows} == {"LIV-001", "LIV-002"}
    assert all(r["is_vacant"] for r in rows)


@pytest.mark.django_db
def test_hr_officer_cannot_create_campus(api):
    response = api.post("/api/v1/org/campuses/", {"code": "NEW", "name": "New Campus"})
    assert response.status_code == 403


@pytest.mark.django_db
def test_hr_manager_creates_campus_with_audit_row(hr_manager, seeded):
    from rest_framework.test import APIClient

    from audit.models import AuditLog

    client = APIClient()
    client.force_login(hr_manager)
    session = client.session
    session["mfa_verified"] = True  # hr_manager is an MFA role; simulate a verified session
    session.save()
    response = client.post("/api/v1/org/campuses/", {"code": "BER", "name": "Berbice (planned)"})
    assert response.status_code == 201, response.content
    entry = AuditLog.objects.get(entity="org.campus", entity_id=response.json()["id"])
    assert entry.action == "create" and entry.actor == hr_manager and entry.after["code"] == "BER"


@pytest.mark.django_db
def test_mfa_role_is_blocked_until_verified(hr_manager, seeded):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_login(hr_manager)
    response = client.get("/api/v1/org/campuses/")
    assert response.status_code == 403
    assert "Multi-factor" in response.json()["detail"]
