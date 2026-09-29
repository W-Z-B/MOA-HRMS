from datetime import date

import pytest
from rest_framework.test import APIClient

from audit.models import AuditLog
from integration.models import ServiceClient
from training.models import TrainingRecord


def _client(key: str | None) -> APIClient:
    client = APIClient()
    if key:
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
    return client


@pytest.mark.django_db
def test_key_is_stored_hashed_and_rotates(seeded):
    client, key = ServiceClient.issue("srms", ["staff:read"])
    assert key not in (client.key_hash, client.key_prefix) and len(client.key_hash) == 64
    assert ServiceClient.authenticate(key) == client
    _, new_key = ServiceClient.issue("srms", ["staff:read"])
    assert ServiceClient.authenticate(key) is None and ServiceClient.authenticate(new_key) is not None


@pytest.mark.django_db
def test_staff_endpoint_requires_key_and_scope_and_hides_identifiers(employee, unit):
    from org.models import Position
    from people.models import Assignment

    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2026, 1, 1),
    )
    _, staff_key = ServiceClient.issue("srms", ["staff:read", "org:read"])
    _, other_key = ServiceClient.issue("lms", ["training:write"])

    assert _client(None).get("/api/v1/integration/staff/").status_code in (401, 403)
    assert _client("not-a-real-key-000000000000").get("/api/v1/integration/staff/").status_code in (401, 403)
    assert _client(other_key).get("/api/v1/integration/staff/").status_code == 403

    response = _client(staff_key).get("/api/v1/integration/staff/", {"campus": "MRP"})
    assert response.status_code == 200
    row = response.json()["results"][0]
    assert row["employee_no"] == "E0001" and row["unit_code"] == "LIV" and row["campus_code"] == "MRP"
    assert row["position_title"] == "Livestock Instructor"
    assert not {"nis_no", "tin", "national_id", "date_of_birth", "address"} & set(row)
    assert AuditLog.objects.filter(action="integration:staff.read").exists()

    org = _client(staff_key).get("/api/v1/integration/org/").json()
    assert {c["code"] for c in org["campuses"]} == {"MRP", "ESQ"}
    assert any(u["code"] == "LIV" for u in org["units"])


@pytest.mark.django_db
def test_training_completion_is_idempotent(employee):
    _, key = ServiceClient.issue("lms", ["training:write"])
    payload = {
        "external_ref": "lms:site:SD-101:E0001",
        "employee_no": "E0001",
        "course": "Records management for HR officers",
        "starts": "2026-10-05",
        "ends": "2026-10-09",
        "certification": "Certificate of completion",
    }
    first = _client(key).post("/api/v1/integration/training-completions/", payload, format="json")
    assert first.status_code == 201 and first.json()["created"] is True
    again = _client(key).post("/api/v1/integration/training-completions/", payload, format="json")
    assert again.status_code == 200 and again.json()["created"] is False
    assert TrainingRecord.objects.filter(employee=employee, provider="GSA LMS").count() == 1
    missing = _client(key).post(
        "/api/v1/integration/training-completions/", {**payload, "employee_no": "NOPE"}, format="json"
    )
    assert missing.status_code == 404


@pytest.mark.django_db
def test_a_person_session_cannot_use_the_integration_api(api):
    assert api.get("/api/v1/integration/staff/").status_code in (401, 403)


@pytest.mark.django_db
def test_a_key_held_by_the_platform_is_registered_without_being_printed(monkeypatch, capsys):
    from django.core.management import CommandError, call_command

    key = "k" * 43
    monkeypatch.setenv("SERVICE_KEY_TEST", key)
    call_command("create_service_client", name="sibling", scopes=["staff:read"], key_env="SERVICE_KEY_TEST")
    assert key not in capsys.readouterr().out
    client = ServiceClient.authenticate(key)
    assert client is not None and client.name == "sibling" and client.scopes == ["staff:read"]

    monkeypatch.setenv("SERVICE_KEY_TEST", "too-short")
    with pytest.raises(CommandError):
        call_command(
            "create_service_client", name="sibling", scopes=["staff:read"], key_env="SERVICE_KEY_TEST"
        )
    assert ServiceClient.authenticate(key) is not None
