"""The rest of the staff record (items 1.06 to 1.08): background, contacts, bank details, history."""

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from audit.models import AuditLog
from notifications.models import Notification
from org.models import Campus
from people.models import BankAccount, EmergencyContact, Employee


def signed_in(user, mfa=True) -> APIClient:
    client = APIClient()
    client.force_login(user)
    if mfa:
        session = client.session
        session["mfa_verified"] = True
        session.save()
    return client


@pytest.fixture
def finance(make_user, seeded):
    return make_user("finance.officer", "finance")


@pytest.fixture
def essequibo_employee(seeded):
    return Employee.objects.create(
        employee_no="ESQ-9",
        first_name="Only",
        last_name="Essequibo",
        date_of_birth=date(1991, 5, 5),
        campus=Campus.objects.get(code="ESQ"),
    )


# ---------------------------------------------------------------- background and contacts (1.06)


@pytest.mark.django_db
def test_hr_records_qualifications_and_previous_employment(api, employee):
    qualification = api.post(
        "/api/v1/qualifications/",
        {
            "employee": employee.id,
            "level": "bachelor",
            "title": "BSc Agriculture",
            "institution": "University of Guyana",
            "year_awarded": 2012,
            "verified_on": "2026-09-30",
        },
        format="json",
    )
    assert qualification.status_code == 201, qualification.content
    assert qualification.json()["level_name"] == "Bachelor's degree"
    future = api.post(
        "/api/v1/qualifications/",
        {"employee": employee.id, "level": "diploma", "title": "X", "institution": "Y", "year_awarded": 2099},
        format="json",
    )
    assert future.status_code == 400 and "year_awarded" in future.json()

    job = api.post(
        "/api/v1/previous-employment/",
        {
            "employee": employee.id,
            "employer": "Ministry of Agriculture",
            "position": "Extension Officer",
            "start_date": "2012-09-01",
            "end_date": "2010-01-01",
        },
        format="json",
    )
    assert job.status_code == 400 and "end_date" in job.json()
    listing = api.get("/api/v1/qualifications/", {"employee": employee.id}).json()
    assert listing["count"] == 1


@pytest.mark.django_db
def test_a_certificate_must_be_on_the_same_persons_file(api, employee, campus):
    from django.core.files.uploadedfile import SimpleUploadedFile

    other = Employee.objects.create(
        employee_no="E0002", first_name="B", last_name="C", date_of_birth=date(1980, 1, 1), campus=campus
    )
    upload = SimpleUploadedFile("cert.pdf", b"%PDF-1.7 certificate", content_type="application/pdf")
    document = api.post(
        "/api/v1/documents/",
        {"employee": other.id, "title": "Certificate", "doc_type": "certificate", "file": upload},
        format="multipart",
    ).json()
    response = api.post(
        "/api/v1/qualifications/",
        {
            "employee": employee.id,
            "level": "diploma",
            "title": "Diploma in Agriculture",
            "institution": "GSA",
            "document": document["id"],
        },
        format="json",
    )
    assert response.status_code == 400 and "document" in response.json()


@pytest.mark.django_db
def test_who_may_read_dependants_and_emergency_contacts(api, employee, make_user, campus, finance):
    api.post(
        "/api/v1/dependants/",
        {
            "employee": employee.id,
            "name": "Kemi Persaud",
            "relationship": "child",
            "date_of_birth": "2015-04-02",
        },
        format="json",
    )
    contact = api.post(
        "/api/v1/emergency-contacts/",
        {"employee": employee.id, "name": "Ravi Persaud", "relationship": "Brother", "phone": "600-1234"},
        format="json",
    )
    assert contact.status_code == 201
    short = api.post(
        "/api/v1/emergency-contacts/", {"employee": employee.id, "name": "X", "phone": "12"}, format="json"
    )
    assert short.status_code == 400 and "phone" in short.json()

    supervisor = signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert supervisor.get("/api/v1/emergency-contacts/", {"employee": employee.id}).json()["count"] == 1
    assert supervisor.get("/api/v1/dependants/").status_code == 403  # family details stay with HR and Finance
    assert signed_in(finance).get("/api/v1/dependants/", {"employee": employee.id}).json()["count"] == 1
    plain = signed_in(make_user("plain.person", "employee", campus=campus))
    assert plain.get("/api/v1/emergency-contacts/").status_code == 403


@pytest.mark.django_db
def test_next_of_kin_now_lives_in_emergency_contacts(api, employee):
    body = api.get(f"/api/v1/employees/{employee.id}/").json()
    assert "next_of_kin_name" not in body
    assert not hasattr(Employee, "next_of_kin_name")
    assert EmergencyContact._meta.get_field("priority").default == 1


# ---------------------------------------------------------------- bank details (1.07)


def propose(client, employee, number="1234-5678-90") -> dict:
    response = client.post(
        "/api/v1/bank-accounts/",
        {
            "employee": employee.id,
            "bank_name": "Republic Bank (Guyana)",
            "branch": "Water Street",
            "account_name": employee.full_name,
            "account_number": number,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.django_db
def test_bank_details_need_a_second_person_and_the_employee_is_told(api, employee, hr_manager, finance):
    owner = get_user_model().objects.create_user("asha.persaud", password="x" * 14)
    employee.user = owner
    employee.save()

    proposal = propose(api, employee)  # the HR officer proposes
    assert proposal["state"] == "pending" and proposal["account_number_masked"] == "••••7890"
    assert "account_number" not in proposal
    assert Notification.objects.filter(
        recipient=finance, title__startswith="Bank details to approve"
    ).exists()

    officer_tries = api.post(f"/api/v1/bank-accounts/{proposal['id']}/approve/")
    assert officer_tries.status_code == 403  # an HR officer proposes but does not decide

    approved = signed_in(finance).post(f"/api/v1/bank-accounts/{proposal['id']}/approve/", {}, format="json")
    assert approved.status_code == 200 and approved.json()["state"] == "active"
    assert approved.json()["effective_from"]
    notice = Notification.objects.get(recipient=owner)
    assert notice.title == "Your bank details were changed" and "ending 7890" in notice.body

    second = propose(api, employee, "99887766")
    signed_in(hr_manager).post(f"/api/v1/bank-accounts/{second['id']}/approve/", {}, format="json")
    states = dict(BankAccount.objects.values_list("account_number_last4", "state"))
    assert states == {"7890": "superseded", "7766": "active"}


@pytest.mark.django_db
def test_the_proposer_cannot_approve_their_own_change(employee, hr_manager):
    manager = signed_in(hr_manager)
    proposal = propose(manager, employee)
    refused = manager.post(f"/api/v1/bank-accounts/{proposal['id']}/approve/", {}, format="json")
    assert refused.status_code == 403 and refused.json()["code"] == "same_person"


@pytest.mark.django_db
def test_one_change_at_a_time_and_a_rejection_says_why(api, employee, finance):
    first = propose(api, employee)
    again = api.post(
        "/api/v1/bank-accounts/",
        {"employee": employee.id, "bank_name": "GBTI", "account_name": "A", "account_number": "11112222"},
        format="json",
    )
    assert again.status_code == 400
    decider = signed_in(finance)
    assert decider.post(f"/api/v1/bank-accounts/{first['id']}/reject/", {}, format="json").status_code == 400
    rejected = decider.post(
        f"/api/v1/bank-accounts/{first['id']}/reject/",
        {"note": "Name does not match the bank letter"},
        format="json",
    )
    assert rejected.json()["state"] == "rejected"
    assert decider.post(f"/api/v1/bank-accounts/{first['id']}/approve/", {}, format="json").status_code == 409


@pytest.mark.django_db
def test_bank_numbers_are_never_logged_and_reveal_is_restricted(api, employee, finance):
    proposal = propose(api, employee, "5550001234")
    for entry in AuditLog.objects.filter(entity="people.bankaccount"):
        assert "5550001234" not in str(entry.before) + str(entry.after)
    assert api.post(f"/api/v1/bank-accounts/{proposal['id']}/reveal/").status_code == 403
    shown = signed_in(finance).post(f"/api/v1/bank-accounts/{proposal['id']}/reveal/")
    assert shown.json() == {"account_number": "5550001234"}
    assert AuditLog.objects.filter(entity="people.bankaccount", action="reveal").exists()
    assert (
        api.patch(f"/api/v1/bank-accounts/{proposal['id']}/", {"bank_name": "X"}, format="json").status_code
        == 405
    )


# ---------------------------------------------------------------- campus scope on every write


@pytest.mark.django_db
def test_campus_scoped_hr_cannot_file_records_for_another_campus(api, essequibo_employee, seeded):
    esq = essequibo_employee
    attempts = {
        "employee": api.post(
            "/api/v1/employees/",
            {
                "employee_no": "ESQ-10",
                "first_name": "New",
                "last_name": "Hire",
                "date_of_birth": "1995-01-01",
                "campus": esq.campus_id,
            },
            format="json",
        ),
        "qualification": api.post(
            "/api/v1/qualifications/",
            {"employee": esq.id, "level": "diploma", "title": "X", "institution": "Y"},
            format="json",
        ),
        "contact": api.post(
            "/api/v1/emergency-contacts/",
            {"employee": esq.id, "name": "X", "phone": "6001234567"},
            format="json",
        ),
        "bank": api.post(
            "/api/v1/bank-accounts/",
            {"employee": esq.id, "bank_name": "GBTI", "account_name": "X", "account_number": "12345678"},
            format="json",
        ),
    }
    from django.core.files.uploadedfile import SimpleUploadedFile

    from leave.models import LeaveType
    from org.models import Grade, OrgUnit, Position, SalaryScale

    unit = OrgUnit.objects.create(code="ESQ-X", name="Essequibo unit", unit_type="unit", campus=esq.campus)
    grade = Grade.objects.create(
        scale=SalaryScale.objects.create(code="GSX", name="Scale"),
        code="G1",
        step=1,
        amount=1,
        effective_from=date(2026, 1, 1),
    )
    post = Position.objects.create(number="ESQ-X-1", title="Field Instructor", grade=grade, org_unit=unit)
    attempts["appointment"] = api.post(
        "/api/v1/assignments/",
        {
            "employee": esq.id,
            "position": post.id,
            "appointment_type": "permanent",
            "start_date": "2026-01-05",
        },
        format="json",
    )
    attempts["document"] = api.post(
        "/api/v1/documents/",
        {
            "employee": esq.id,
            "title": "Letter",
            "doc_type": "letter",
            "file": SimpleUploadedFile("letter.pdf", b"%PDF-1.7 letter", content_type="application/pdf"),
        },
        format="multipart",
    )
    attempts["leave request"] = api.post(
        "/api/v1/leave/requests/",
        {
            "employee": esq.id,
            "leave_type": LeaveType.objects.get(code="ANN").id,
            "from_date": "2026-11-02",
            "to_date": "2026-11-03",
        },
        format="json",
    )
    for what, response in attempts.items():
        # Refused, and the refusal says nothing about the person: an id on another campus reads as unknown.
        assert response.status_code in (400, 403), (what, response.content)
        body = response.content.decode()
        assert "available" not in body and "balance" not in body, (what, body)
        if response.status_code == 400:
            assert set(response.json()) <= {"employee", "campus", "position"}, (what, body)
    assert not Employee.objects.filter(employee_no="ESQ-10").exists()


# ---------------------------------------------------------------- history (1.08)


@pytest.mark.django_db
def test_changes_to_the_personal_record_say_why_and_appear_in_its_history(api, employee):
    url = f"/api/v1/employees/{employee.id}/"
    no_reason = api.patch(url, {"phone": "600-0001"}, format="json")
    assert no_reason.status_code == 400 and "change_reason" in no_reason.json()

    changed = api.patch(
        url,
        {"phone": "600-0001", "nis_no": "B7654321", "change_reason": "Form signed 30/09/2026"},
        format="json",
    )
    assert changed.status_code == 200
    history = api.get(f"{url}history/").json()
    latest = history[0]
    assert latest["record"] == "Personal details" and latest["action_name"] == "Changed"
    assert latest["reason"] == "Form signed 30/09/2026"
    fields = {c["field"]: c for c in latest["changes"]}
    assert fields["Phone"]["after"] == "600-0001"
    assert fields["NIS number"] == {"field": "NIS number", "before": "(hidden)", "after": "(hidden)"}
    assert "B7654321" not in str(history)


@pytest.mark.django_db
def test_the_record_as_it_stood_on_a_day(api, employee):
    from django.utils import timezone

    Employee.objects.filter(pk=employee.pk).update(created_at=timezone.now() - timedelta(days=10), phone="")
    url = f"/api/v1/employees/{employee.id}/"
    api.patch(url, {"phone": "600-0002", "change_reason": "New number"}, format="json")

    def as_at(days_ago: int):
        return api.get(f"{url}as-at/", {"date": (date.today() - timedelta(days=days_ago)).isoformat()})

    before_change = as_at(1).json()
    assert before_change["current"] is False and before_change["record"]["phone"] == ""
    now = as_at(0).json()
    assert now["current"] is True and now["record"]["phone"] == "600-0002"
    assert now["record"]["nis_no"] == "(hidden)" and "created_at" not in now["record"]
    assert as_at(20).status_code == 404  # not on file yet
    assert api.get(f"{url}as-at/", {"date": "not-a-date"}).status_code == 400


@pytest.mark.django_db
def test_history_is_for_hr_principal_and_auditors(employee, make_user, campus):
    supervisor = signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert supervisor.get(f"/api/v1/employees/{employee.id}/history/").status_code == 403
    auditor = signed_in(make_user("the.auditor", "auditor"))
    assert auditor.get(f"/api/v1/employees/{employee.id}/history/").status_code == 200
