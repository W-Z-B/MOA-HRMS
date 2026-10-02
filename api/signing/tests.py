"""Item 1.20: asking for a signature, signing with evidence, declining, and checking the evidence later."""

import hashlib
from datetime import date

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from audit.models import AuditLog

PASSWORD = "Str0ng-Passw0rd-123"  # noqa: S105 - the test accounts' password (conftest make_user)
LETTER = b"%PDF-1.7 appointment letter"


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def asha(employee, unit, make_user, campus):
    """Asha in LIV-001 since 2019, with an account of her own."""
    from org.models import Position
    from people.models import Assignment

    employee.user = make_user("asha.persaud", "employee", campus=campus)
    employee.save()
    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2019, 9, 2),
    )
    return employee


def _document(employee, classification="confidential", content=LETTER):
    from people.models import Document

    return Document.objects.create(
        employee=employee,
        title="Appointment letter",
        doc_type="letter",
        file=ContentFile(content, name="appointment.pdf"),
        classification=classification,
    )


def _ask(client, document, kind="accept", **extra):
    return client.post(
        "/api/v1/signing/requests/", {"document": document.id, "kind": kind, **extra}, format="json"
    )


@pytest.mark.django_db
def test_the_person_reads_and_signs_and_the_evidence_is_kept(api, asha):
    from notifications.models import Notification

    document = _document(asha)
    asked = _ask(api, document)
    assert asked.status_code == 201, asked.content
    assert asked.json()["statement"] == "I have read this document and I accept it."
    assert Notification.objects.filter(
        recipient=asha.user, title="Please read and accept: Appointment letter"
    ).exists()
    assert _ask(api, document).json()["code"] == "waiting"

    me = _signed_in(asha.user)
    (waiting,) = me.get("/api/v1/signing/mine/").json()["results"]
    assert waiting["download_url"] == f"/api/v1/signing/mine/{waiting['id']}/document/"
    read = me.get(waiting["download_url"])
    assert read.status_code == 200 and b"".join(read.streaming_content) == LETTER
    sign_url = f"/api/v1/signing/mine/{waiting['id']}/sign/"
    assert me.post(sign_url, {"password": PASSWORD, "agree": False}, format="json").json()["agree"] == [
        "Tick that you agree to the sentence above."
    ]
    wrong = me.post(sign_url, {"password": "not it", "agree": True}, format="json")
    assert wrong.status_code == 400 and wrong.json()["code"] == "wrong_password"
    signed = me.post(
        sign_url,
        {"password": PASSWORD, "agree": True},
        format="json",
        HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14)",
    )
    assert signed.status_code == 200, signed.content
    evidence = signed.json()["evidence"]
    assert signed.json()["state"] == "signed"
    assert evidence["sha256"] == hashlib.sha256(LETTER).hexdigest() and evidence["file_unchanged"] is True
    assert (evidence["document_version"], evidence["statement"]) == (
        1,
        "I have read this document and I accept it.",
    )
    assert (
        evidence["method"] == "password confirmed while signed in"
        and evidence["signer_name"] == "asha.persaud"
    )
    assert AuditLog.objects.filter(entity="signing.signaturerequest", action="document_signed").exists()
    assert Notification.objects.filter(title="Asha Persaud signed: Appointment letter").exists()
    assert (
        me.post(sign_url, {"password": PASSWORD, "agree": True}, format="json").json()["code"]
        == "not_waiting"
    )

    document.file.save("tampered.pdf", ContentFile(b"%PDF-1.7 something else"), save=True)
    seen = api.get(f"/api/v1/signing/requests/{waiting['id']}/").json()["evidence"]
    assert seen["file_unchanged"] is False  # a changed file no longer matches what was signed


@pytest.mark.django_db
def test_wrong_passwords_while_signing_count_towards_the_lockout(api, asha):
    request_id = _ask(api, _document(asha)).json()["id"]
    me = _signed_in(asha.user)
    url = f"/api/v1/signing/mine/{request_id}/sign/"
    for _ in range(5):
        assert (
            me.post(url, {"password": "guess", "agree": True}, format="json").json()["code"]
            == "wrong_password"
        )
    locked = me.post(url, {"password": PASSWORD, "agree": True}, format="json")
    assert locked.status_code == 429 and locked.json()["code"] == "locked"


@pytest.mark.django_db
def test_signing_is_asked_only_where_it_can_happen_and_kept_to_its_readers(api, asha, make_user, campus):
    from org.models import Campus
    from people.models import Employee

    assert _ask(api, _document(asha, classification="medical")).json()["code"] == "medical"
    nobody = Employee.objects.create(
        employee_no="E0090",
        first_name="No",
        last_name="Account",
        date_of_birth=date(1980, 1, 1),
        campus=campus,
    )
    assert _ask(api, _document(nobody)).json()["code"] == "no_account"
    elsewhere = _signed_in(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    assert "document" in _ask(elsewhere, _document(asha)).json()
    supervisor = _signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert supervisor.get("/api/v1/signing/requests/").status_code == 403

    request_id = _ask(api, _document(asha), kind="acknowledge", message="Please read before Monday").json()[
        "id"
    ]
    someone = _signed_in(make_user("someone", "employee", campus=campus))
    assert someone.get("/api/v1/signing/mine/").json()["count"] == 0
    assert (
        someone.post(
            f"/api/v1/signing/mine/{request_id}/sign/", {"password": PASSWORD, "agree": True}
        ).status_code
        == 404
    )

    me = _signed_in(asha.user)
    declined = me.post(
        f"/api/v1/signing/mine/{request_id}/decline/", {"reason": "The dates are wrong"}, format="json"
    )
    assert (
        declined.json()["state"] == "declined" and declined.json()["decline_reason"] == "The dates are wrong"
    )
    again = _ask(api, _document(asha)).json()["id"]
    withdrawn = api.post(
        f"/api/v1/signing/requests/{again}/withdraw/", {"reason": "Sent in error"}, format="json"
    )
    assert withdrawn.json()["state"] == "withdrawn"
    assert [r["state"] for r in me.get("/api/v1/signing/mine/").json()["results"]] == [
        "declined"
    ]  # withdrawn hidden


@pytest.mark.django_db
def test_a_letter_can_ask_to_be_accepted_when_it_is_issued(api, asha, campus):
    from letters.models import Letter, LetterTemplate
    from notifications.models import Notification
    from people.models import Employee
    from signing.models import SignatureRequest

    template = LetterTemplate.objects.get(code="job_letter")
    body = {
        "employee": asha.id,
        "template": template.id,
        "answers": {"purpose": "a bank loan"},
        "ask": "acknowledge",
    }
    issued = api.post("/api/v1/letters/", body, format="json")
    assert issued.status_code == 201, issued.content
    wanted = SignatureRequest.objects.get(document=Letter.objects.get(pk=issued.json()["id"]).document)
    assert wanted.kind == "acknowledge" and wanted.state == "waiting"
    titles = list(Notification.objects.filter(recipient=asha.user).values_list("title", flat=True))
    assert titles == [
        "Please read and acknowledge: Job letter, " + issued.json()["reference"]
    ]  # one notice, not two

    nobody = Employee.objects.create(
        employee_no="E0091",
        first_name="No",
        last_name="Account",
        date_of_birth=date(1980, 1, 1),
        campus=campus,
    )
    from org.models import Position
    from people.models import Assignment

    Assignment.objects.create(
        employee=nobody,
        position=Position.objects.get(number="LIV-002"),
        appointment_type="permanent",
        start_date=date(2020, 1, 1),
    )
    refused = api.post("/api/v1/letters/", {**body, "employee": nobody.id}, format="json")
    assert refused.status_code == 409 and refused.json()["code"] == "no_account"
    assert not Letter.objects.filter(employee=nobody).exists()  # nothing issued half way
