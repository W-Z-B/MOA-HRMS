from datetime import date

import pytest
from django.db import IntegrityError, transaction

from audit.models import AuditLog
from people.models import Assignment, Employee


@pytest.mark.django_db
def test_identifiers_are_encrypted_at_rest_and_masked_in_api(api, employee):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT nis_no FROM people_employee WHERE id = %s", [employee.id])
        raw = cursor.fetchone()[0]
    assert b"A1234567" not in bytes(raw)
    assert Employee.objects.get(pk=employee.pk).nis_no == "A1234567"

    response = api.get(f"/api/v1/employees/{employee.id}/")
    body = response.json()
    assert response.status_code == 200
    assert "nis_no" not in body and body["nis_no_masked"].endswith("567")


@pytest.mark.django_db
def test_reveal_returns_identifiers_and_is_audited(api, employee, hr_officer):
    response = api.post(f"/api/v1/employees/{employee.id}/reveal/")
    assert response.status_code == 200
    assert response.json()["tin"] == "TIN000123"
    entry = AuditLog.objects.filter(entity="people.employee", entity_id=employee.id, action="reveal").get()
    assert entry.actor == hr_officer


@pytest.mark.django_db
def test_hr_officer_is_scoped_to_own_campus(api, employee, seeded):
    from org.models import Campus

    other = Employee.objects.create(
        employee_no="E0002",
        first_name="Devi",
        last_name="Ramnarine",
        date_of_birth=date(1988, 7, 2),
        campus=Campus.objects.get(code="ESQ"),
    )
    ids = {row["id"] for row in api.get("/api/v1/employees/").json()["results"]}
    assert employee.id in ids and other.id not in ids


@pytest.mark.django_db
def test_one_substantive_holder_per_position(employee, unit):
    from org.models import Position

    position = Position.objects.get(number="LIV-001")
    Assignment.objects.create(
        employee=employee, position=position, appointment_type="permanent", start_date=date(2026, 1, 1)
    )
    second = Employee.objects.create(
        employee_no="E0003",
        first_name="Ravi",
        last_name="Singh",
        date_of_birth=date(1992, 1, 1),
        campus=employee.campus,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Assignment.objects.create(
            employee=second, position=position, appointment_type="contract", start_date=date(2026, 6, 1)
        )
    # An acting appointment on the same post is allowed.
    Assignment.objects.create(
        employee=second,
        position=position,
        appointment_type="contract",
        start_date=date(2026, 6, 1),
        is_acting=True,
    )
    assert not position.is_vacant


@pytest.mark.django_db
def test_create_employee_via_api_writes_audit_without_identifiers_in_clear(api, campus):
    payload = {
        "employee_no": "E0100",
        "first_name": "Kamla",
        "last_name": "Boodhoo",
        "date_of_birth": "1995-05-05",
        "gender": "F",
        "campus": campus.id,
        "national_id": "999888777",
    }
    response = api.post("/api/v1/employees/", payload, format="json")
    assert response.status_code == 201, response.content
    entry = AuditLog.objects.get(entity="people.employee", entity_id=response.json()["id"], action="create")
    assert entry.after["national_id"] == "***"
