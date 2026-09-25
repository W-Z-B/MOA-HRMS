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


@pytest.mark.django_db
def test_directory_search_matches_words_and_prefixes(api, employee):
    def ids(q):
        return {r["id"] for r in api.get("/api/v1/employees/", {"q": q}).json()["results"]}

    assert employee.id in ids("persaud asha")  # any order, whole words
    assert employee.id in ids("Pers")  # surname prefix
    assert employee.id in ids("E00")  # employee number prefix
    assert employee.id not in ids("Ramnarine")


@pytest.mark.django_db
def test_document_upload_stores_file_and_lists_it(api, employee):
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("offer.pdf", b"%PDF-1.4 demo", content_type="application/pdf")
    response = api.post(
        "/api/v1/documents/",
        {
            "employee": employee.id,
            "title": "Offer letter",
            "doc_type": "letter",
            "classification": "internal",
            "file": upload,
        },
        format="multipart",
    )
    assert response.status_code == 201, response.content
    assert response.json()["file"].endswith(".pdf")
    listing = api.get("/api/v1/documents/", {"employee": employee.id}).json()
    assert listing["count"] == 1 and listing["results"][0]["title"] == "Offer letter"


@pytest.mark.django_db
def test_document_download_is_authenticated_scoped_and_audited(api, employee, hr_officer, make_user, seeded):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from rest_framework.test import APIClient

    upload = SimpleUploadedFile("contract.pdf", b"%PDF-1.4 contract", content_type="application/pdf")
    created = api.post(
        "/api/v1/documents/",
        {"employee": employee.id, "title": "Contract", "doc_type": "contract", "file": upload},
        format="multipart",
    ).json()
    assert "file" not in created and created["download_url"].endswith(f"/documents/{created['id']}/download/")

    response = api.get(created["download_url"])
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"%PDF-1.4 contract"
    assert "attachment" in response["Content-Disposition"]
    assert AuditLog.objects.filter(
        entity="people.document", entity_id=created["id"], action="download"
    ).exists()

    # Unauthenticated and other-campus users cannot fetch it.
    assert APIClient().get(created["download_url"]).status_code == 403
    from org.models import Campus

    other = make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ"))
    client = APIClient()
    client.force_login(other)
    assert client.get(created["download_url"]).status_code == 404
