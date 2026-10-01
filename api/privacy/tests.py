"""Privacy rights (item 1.31): the notice and its acknowledgement, a person's own record, and corrections."""

from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from notifications.models import Notification
from privacy.models import CorrectionRequest, NoticeAcknowledgement, PrivacyNotice

NOTICE = {
    "title": "How GSA uses your personal data",
    "body": "GSA holds your record.\n\nYou may ask to see it.",
}


def signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def owner(employee, make_user, campus):
    """Asha Persaud with her own account, as staff sign in to self-service."""
    person = make_user("asha.persaud", "employee", campus=campus)
    employee.user = person
    employee.email = "asha.persaud@gsa.example"
    employee.save()
    return person


@pytest.fixture
def published(hr_manager):
    return PrivacyNotice.objects.create(
        version=1, published_at=timezone.now(), published_by=hr_manager, **NOTICE
    )


# ---------------------------------------------------------------------------------------------- the notice


@pytest.mark.django_db
def test_the_notice_is_written_published_and_read_once_per_version(hr_manager, owner, api):
    manager = signed_in(hr_manager)
    me = signed_in(owner)
    assert me.get("/api/v1/auth/me/").json()["privacy_notice_due"] is None  # nothing published yet

    draft = manager.post("/api/v1/privacy/notices/", NOTICE, format="json").json()
    assert draft["version"] == 1 and draft["published_at"] is None
    edited = manager.patch(
        f"/api/v1/privacy/notices/{draft['id']}/", {"title": "Your data at GSA"}, format="json"
    )
    assert edited.json()["title"] == "Your data at GSA"
    assert api.post("/api/v1/privacy/notices/", NOTICE, format="json").status_code == 403  # an HR officer

    published = manager.post(f"/api/v1/privacy/notices/{draft['id']}/publish/").json()
    assert published["published_at"] and published["published_by"] == "hr.manager"
    frozen = manager.patch(f"/api/v1/privacy/notices/{draft['id']}/", {"title": "Changed"}, format="json")
    assert frozen.status_code == 400
    assert manager.post(f"/api/v1/privacy/notices/{draft['id']}/publish/").json()["code"] == "published"

    assert me.get("/api/v1/auth/me/").json()["privacy_notice_due"] == 1
    current = me.get("/api/v1/privacy/notice/").json()
    assert current["notice"]["title"] == "Your data at GSA" and current["acknowledged"] is False
    wrong = me.post("/api/v1/privacy/notice/acknowledge/", {"version": 2}, format="json")
    assert wrong.status_code == 409 and wrong.json()["code"] == "not_current"
    assert me.post("/api/v1/privacy/notice/acknowledge/", {"version": 1}, format="json").json()[
        "acknowledged"
    ]
    assert me.post("/api/v1/privacy/notice/acknowledge/", {"version": 1}, format="json").status_code == 200
    assert NoticeAcknowledgement.objects.filter(user=owner).count() == 1
    assert me.get("/api/v1/auth/me/").json()["privacy_notice_due"] is None

    second = manager.post("/api/v1/privacy/notices/", NOTICE, format="json").json()
    manager.post(f"/api/v1/privacy/notices/{second['id']}/publish/")
    assert me.get("/api/v1/auth/me/").json()["privacy_notice_due"] == 2  # a new version is read again
    assert AuditLog.objects.filter(action="notice_published").count() == 2


@pytest.mark.django_db
def test_an_older_draft_cannot_replace_a_newer_notice(hr_manager):
    manager = signed_in(hr_manager)
    older = manager.post("/api/v1/privacy/notices/", NOTICE, format="json").json()
    newer = manager.post("/api/v1/privacy/notices/", NOTICE, format="json").json()
    manager.post(f"/api/v1/privacy/notices/{newer['id']}/publish/")
    refused = manager.post(f"/api/v1/privacy/notices/{older['id']}/publish/")
    assert refused.status_code == 409 and refused.json()["code"] == "older"


@pytest.mark.django_db
def test_who_has_read_the_notice_is_a_report(published, owner, hr_manager):
    signed_in(owner).post("/api/v1/privacy/notice/acknowledge/", {"version": 1}, format="json")
    rows = signed_in(hr_manager).get("/api/v1/reports/privacy-acknowledgements/").json()["rows"]
    read = {row["username"]: row["read"] for row in rows}
    assert read["asha.persaud"] != "Not yet" and read["hr.manager"] == "Not yet"


# ---------------------------------------------------------------------------------------------- own record


@pytest.mark.django_db
def test_a_person_sees_everything_held_about_them(owner, employee, api):
    from people.models import BankAccount, EmergencyContact

    EmergencyContact.objects.create(
        employee=employee, name="Ravi Persaud", relationship="Brother", phone="592-600-0001"
    )
    BankAccount.objects.create(
        employee=employee,
        bank_name="Republic Bank (Guyana)",
        account_name="Asha Persaud",
        account_number="1234567890",
        account_number_last4="7890",
        state=BankAccount.State.ACTIVE,
    )
    api.patch(
        f"/api/v1/employees/{employee.id}/",
        {"phone": "592-600-1234", "change_reason": "New phone"},
        format="json",
    )

    response = signed_in(owner).get("/api/v1/privacy/my-record/")
    data = response.json()
    personal = data["staff_record"]["personal"]
    assert (personal["employee_no"], personal["nis_no"], personal["phone"]) == (
        "E0001",
        "A1234567",
        "592-600-1234",
    )
    assert data["staff_record"]["emergency_contacts"][0]["name"] == "Ravi Persaud"
    assert data["staff_record"]["bank_accounts"][0]["account_ending"] == "7890"
    assert "1234567890" not in response.content.decode()  # the full bank number never leaves in the file
    change = next(e for e in data["staff_record"]["history_of_changes"] if e["action_name"] == "Changed")
    assert change["actor"] == "hr.officer" and change["reason"] == "New phone"
    assert set(data["staff_record"]["contract_and_terms"]) >= {"position", "contract", "leave_entitlements"}
    assert (
        "employee_no" not in data["staff_record"]["contract_and_terms"]
    )  # said once, under personal details
    assert data["account"]["username"] == "asha.persaud"
    assert [r["role"] for r in data["account"]["roles"]] == ["Employee"]
    assert AuditLog.objects.filter(action="record_viewed", subject=employee.id).exists()
    # Viewing one's own record is not part of the file's story that HR reads.
    history = api.get(f"/api/v1/employees/{employee.id}/history/").json()
    assert "record_viewed" not in {row["action"] for row in history}


@pytest.mark.django_db
def test_someone_not_on_the_staff_gets_their_account_only(make_user, seeded):
    auditor = make_user("the.auditor", "auditor")
    data = signed_in(auditor).get("/api/v1/privacy/my-record/").json()
    assert data["staff_record"] is None and data["account"]["roles"][0]["role"] == "Auditor"


@pytest.mark.django_db
def test_hr_produces_a_record_for_a_request_made_on_paper(hr_manager, employee, api):
    produced = signed_in(hr_manager).get(f"/api/v1/privacy/employees/{employee.id}/record/")
    assert (
        produced.status_code == 200 and produced.json()["staff_record"]["personal"]["employee_no"] == "E0001"
    )
    assert produced.json()["account"] is None
    assert AuditLog.objects.get(action="record_produced").subject == employee.id
    assert api.get(f"/api/v1/privacy/employees/{employee.id}/record/").status_code == 403
    assert signed_in(hr_manager).get("/api/v1/privacy/employees/999999/record/").status_code == 404


# ---------------------------------------------------------------------------------------------- corrections


@pytest.mark.django_db
def test_a_correction_is_asked_for_answered_and_told(owner, employee, hr_officer, settings):
    settings.PRIVACY_RESPONSE_DAYS = 30
    me = signed_in(owner)
    asked = me.post(
        "/api/v1/privacy/corrections/",
        {"subject": "personal", "wrong": "My date of birth reads 1990.", "should_be": "14 March 1991"},
        format="json",
    )
    assert asked.status_code == 201, asked.content
    correction = asked.json()
    assert correction["state_name"] == "With Human Resources" and correction["is_mine"] is True
    assert correction["due_by"] == (timezone.localdate() + timedelta(days=30)).isoformat()
    assert Notification.objects.filter(
        recipient=hr_officer, title="Correction requested: Asha Persaud"
    ).exists()

    hr = APIClient()
    hr.force_login(hr_officer)
    queue = hr.get("/api/v1/privacy/corrections/", {"state": "open"}).json()["results"]
    assert [c["employee_no"] for c in queue] == ["E0001"]
    assert (
        me.post(
            f"/api/v1/privacy/corrections/{correction['id']}/decide/", {"outcome": "corrected"}
        ).status_code
        == 403
    )

    url = f"/api/v1/privacy/corrections/{correction['id']}/decide/"
    no_reason = hr.post(url, {"outcome": "declined"}, format="json")
    assert no_reason.status_code == 400 and no_reason.json()["note"] == ["Say why the record is not changed."]
    answered = hr.post(
        url, {"outcome": "declined", "note": "The birth certificate on file says 1990."}, format="json"
    )
    assert answered.json()["state_name"] == "Not changed"
    assert hr.post(url, {"outcome": "corrected"}, format="json").status_code == 409
    told = Notification.objects.get(recipient=owner, title="Your correction request was not changed")
    assert "birth certificate" in told.body
    assert (
        AuditLog.objects.get(action="correction_declined").reason
        == "The birth certificate on file says 1990."
    )
    assert me.get("/api/v1/privacy/corrections/").json()["results"][0]["decided_by_name"] == "hr.officer"


@pytest.mark.django_db
def test_corrections_stay_with_the_person_and_their_campus_hr(owner, employee, hr_officer, make_user, campus):
    from org.models import Campus
    from people.models import Employee

    colleague_user = make_user("devon.charles", "employee", campus=campus)
    colleague = Employee.objects.create(
        employee_no="E0007",
        first_name="Devon",
        last_name="Charles",
        date_of_birth=date(1992, 12, 1),
        campus=campus,
        user=colleague_user,
    )
    me = signed_in(owner)
    about_someone_else = {"employee": colleague.id, "subject": "contact", "wrong": "x", "should_be": "y"}
    assert me.post("/api/v1/privacy/corrections/", about_someone_else, format="json").status_code == 403
    me.post(
        "/api/v1/privacy/corrections/",
        {"subject": "contact", "wrong": "Old phone", "should_be": "New"},
        format="json",
    )
    assert signed_in(colleague_user).get("/api/v1/privacy/corrections/").json()["count"] == 0

    elsewhere = make_user("hr.essequibo", "hr_officer", campus=Campus.objects.get(code="ESQ"))
    assert signed_in(elsewhere).get("/api/v1/privacy/corrections/").json()["count"] == 0

    # HR can file a request made on paper for someone on their campus.
    on_paper = {
        "employee": colleague.id,
        "subject": "dependants",
        "wrong": "A child missing",
        "should_be": "Add Ria",
    }
    filed = signed_in(hr_officer).post("/api/v1/privacy/corrections/", on_paper, format="json")
    assert filed.status_code == 201 and filed.json()["employee_no"] == "E0007"


@pytest.mark.django_db
def test_hr_never_answers_a_request_about_themselves(make_user, campus, seeded):
    from people.models import Employee

    officer = make_user("natasha.khan", "hr_officer", "employee", campus=campus)
    Employee.objects.create(
        employee_no="E0006",
        first_name="Natasha",
        last_name="Khan",
        date_of_birth=date(1988, 9, 12),
        campus=campus,
        user=officer,
    )
    client = signed_in(officer)
    mine = client.post(
        "/api/v1/privacy/corrections/",
        {"subject": "contact", "wrong": "Old", "should_be": "New"},
        format="json",
    ).json()
    refused = client.post(
        f"/api/v1/privacy/corrections/{mine['id']}/decide/", {"outcome": "corrected"}, format="json"
    )
    assert refused.status_code == 403 and "Someone else" in refused.json()["detail"]
    assert CorrectionRequest.objects.get().state == "open"
