"""Item 1.21: scanned papers filed in bulk, each found by the employee number at the start of its name."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from audit.models import AuditLog

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


def _pdf(name, body=PDF):
    return SimpleUploadedFile(name, body, content_type="application/pdf")


def _batch(client, doc_type="contract", **extra):
    return client.post("/api/v1/scan-batches/", {"doc_type": doc_type, **extra}, format="json")


def _file(client, batch_id, upload, employee=None):
    data = {"file": upload} if employee is None else {"file": upload, "employee": employee}
    return client.post(f"/api/v1/scan-batches/{batch_id}/files/", data, format="multipart")


def test_the_number_and_the_title_come_from_the_name():
    from people.scanning import number_in, title_from

    assert number_in("E0001 Appointment 2014.pdf") == "E0001"
    assert number_in("e0001_contract.PDF") == "E0001"
    assert number_in("E0001-old.pdf") == number_in("E0001.pdf") == "E0001"
    assert number_in("Appointment E0001.pdf") is None
    assert number_in("E0001contract.pdf") is None  # the number stands apart from the rest
    assert number_in("scan_0042.pdf") is None
    assert title_from("E0001_appointment  letter-2014.pdf", "letter") == "appointment letter-2014"
    assert title_from("E0001.pdf", "contract") == "Contract"


@pytest.mark.django_db
def test_hr_files_a_pile_and_each_paper_lands_in_the_right_record(api, employee):
    from people.models import Document

    made = _batch(api, note="Personnel files, cabinet 2")
    assert made.status_code == 201, made.content
    assert made.json()["classification"] == "confidential"  # what a contract needs at the least
    batch = made.json()["id"]

    filed = _file(api, batch, _pdf("E0001 Appointment 2014.pdf")).json()
    assert filed["filed"] and filed["employee_name"] == "Asha Persaud"
    assert filed["document_title"] == "Appointment 2014"
    document = Document.objects.get(pk=filed["document"])
    assert (document.doc_type, document.classification) == ("contract", "confidential")
    assert document.original_name == "E0001 Appointment 2014.pdf" and document.file.read().startswith(b"%PDF")
    assert AuditLog.objects.filter(
        action="create",
        entity="people.document",
        entity_id=document.pk,
        reason=f"Scanned papers, batch {batch}",
    ).exists()

    again = _file(api, batch, _pdf("E0001 copy.pdf")).json()
    assert not again["filed"] and again["refused"].startswith("Already filed as “Appointment 2014”")
    nobody = _file(api, batch, _pdf("X9999 unknown.pdf", PDF + b"1")).json()
    assert not nobody["filed"] and "Nobody on your campuses has the number X9999" in nobody["refused"]
    unnamed = _file(api, batch, _pdf("scan_0042.pdf", PDF + b"2")).json()
    assert "does not start with an employee number" in unnamed["refused"]
    chosen = _file(api, batch, _pdf("scan_0042.pdf", PDF + b"2"), employee=employee.id).json()
    assert chosen["filed"] and chosen["document_title"] == "scan 0042"
    fake = _file(api, batch, SimpleUploadedFile("E0001 note.pdf", b"<html>not a PDF</html>")).json()
    assert not fake["filed"] and "contents do not match" in fake["refused"]

    detail = api.get(f"/api/v1/scan-batches/{batch}/").json()
    assert (detail["filed"], detail["not_filed"]) == (2, 4)
    assert (
        detail["items"][0]["name"] == "E0001 Appointment 2014.pdf"
        and detail["note"] == "Personnel files, cabinet 2"
    )
    listed = api.get("/api/v1/scan-batches/").json()["results"]
    assert (listed[0]["filed"], listed[0]["not_filed"], listed[0]["doc_type_name"]) == (2, 4, "Contract")


@pytest.mark.django_db
def test_batches_stay_with_hr_and_on_their_campuses(api, employee, make_user, campus, hr_manager):
    from org.models import Campus
    from people.models import Employee

    troy = Employee.objects.create(
        employee_no="E0099",
        first_name="Troy",
        last_name="Benjamin",
        date_of_birth=date(1997, 8, 8),
        campus=Campus.objects.get(code="ESQ"),
    )
    batch = _batch(api).json()["id"]
    elsewhere = _file(api, batch, _pdf("E0099 contract.pdf")).json()
    assert not elsewhere["filed"] and "Nobody on your campuses has the number E0099" in elsewhere["refused"]
    assert _file(api, batch, _pdf("E0099 contract.pdf"), employee=troy.id).status_code == 400

    lower = _batch(api, classification="internal")
    assert lower.json()["classification"] == ["A contract is filed as Confidential or Medical."]
    assert _batch(api, doc_type="medical").json()["classification"] == "medical"

    other = _signed_in(make_user("other.officer", "hr_officer", campus=campus))
    assert other.get("/api/v1/scan-batches/").json()["count"] == 0  # each officer's own batches
    assert _file(other, batch, _pdf("E0001 x.pdf")).status_code == 404
    manager = _signed_in(hr_manager)
    assert manager.get("/api/v1/scan-batches/").json()["count"] == 2  # every batch, for every campus
    added = _file(manager, batch, _pdf("E0001 x.pdf"))
    assert added.status_code == 403 and added.json()["code"] == "not_yours"
    supervisor = _signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert _batch(supervisor).status_code == 403
