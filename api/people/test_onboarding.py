"""Item H-W02: joining the School, from an accepted hire to a full member of staff."""

from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

TODAY = timezone.localdate


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def hire(unit, hr_officer):
    """An accepted hire of Keron Fraser into LIV-002 (Farm Hand), with no staff record yet."""
    from org.models import Position
    from recruitment.models import Application, Candidate, Hire, Vacancy

    position = Position.objects.get(number="LIV-002")
    vacancy = Vacancy.objects.create(
        position=position, opens_on=date(2026, 1, 1), closes_on=date(2026, 2, 1), created_by=hr_officer
    )
    candidate = Candidate.objects.create(
        first_name="Keron", last_name="Fraser", email="keron@example.com", phone="+592 600 1234"
    )
    application = Application.objects.create(
        vacancy=vacancy, candidate=candidate, state=Application.State.ACCEPTED
    )
    return Hire.objects.create(
        application=application,
        vacancy=vacancy,
        candidate=candidate,
        start_date=TODAY() + timedelta(days=7),
        created_by=hr_officer,
        updated_by=hr_officer,
    )


def _start(client, hire, **overrides):
    body = {
        "hire": hire.id,
        "employee_no": "E0777",
        "date_of_birth": "1995-04-02",
        "gender": "M",
        "appointment_type": "permanent",
        **overrides,
    }
    return client.post("/api/v1/onboarding/start/", body, format="json")


@pytest.mark.django_db
def test_starting_onboarding_creates_the_staff_record_and_checklist(api, hire):
    started = _start(api, hire)
    assert started.status_code == 201, started.content
    body = started.json()
    assert body["state"] == "in_progress"
    assert [s["code"] for s in body["steps"]] == ["documents", "account", "equipment", "induction"]
    # "complete" and "cancel" are also listed: allowed_actions reflects who may act, not whether every
    # guard would pass (the same as recruitment and leave's own allowed_actions) - completing now would
    # still be refused, by the "steps_open" guard (see test_completing_is_refused_while_a_step_is_still_open).
    assert set(body["allowed_actions"]) == {"submit_documents", "complete", "cancel"}

    from people.models import Assignment, Employee

    employee = Employee.objects.get(employee_no="E0777")
    assert employee.first_name == "Keron" and employee.last_name == "Fraser"
    assert employee.status == Employee.Status.ONBOARDING
    assignment = Assignment.objects.get(employee=employee)
    assert assignment.position.number == "LIV-002" and assignment.appointment_type == "permanent"
    hire.refresh_from_db()
    assert hire.employee_id == employee.id

    again = _start(api, hire)
    assert again.status_code == 409 and again.json()["code"] == "already_onboarded"


@pytest.mark.django_db
def test_an_employee_number_already_in_use_is_refused(api, hire, employee):
    taken = _start(api, hire, employee_no=employee.employee_no)
    assert taken.status_code == 409 and taken.json()["code"] == "employee_no_taken"


@pytest.mark.django_db
def test_only_hr_may_start_onboarding(api, hire, make_user, campus):
    plain = _signed_in(make_user("plain.jane", "employee", campus=campus))
    assert _start(plain, hire).status_code == 403


@pytest.mark.django_db
def test_the_position_already_held_refuses_a_second_substantive_appointment(api, hire, employee):
    from org.models import Position
    from people.models import Assignment

    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-002"),
        appointment_type="permanent",
        start_date=date(2020, 1, 1),
    )
    filled = _start(api, hire)
    assert filled.status_code == 409 and filled.json()["code"] == "position_filled"


@pytest.fixture
def onboarding_record(api, hire):
    return _start(api, hire).json()


@pytest.mark.django_db
def test_documents_and_account_steps_close_themselves_not_by_hand(api, onboarding_record):
    url = f"/api/v1/onboarding/{onboarding_record['id']}"
    for code in ("documents", "account"):
        done = api.post(f"{url}/steps/{code}/clear/", {"done": True}, format="json")
        assert done.status_code == 400
    # Marking either not needed, for an appointment that genuinely has none, still works by hand.
    not_needed = api.post(f"{url}/steps/documents/clear/", {"done": False}, format="json")
    assert not_needed.json()["steps"][0]["state"] == "not_needed"


@pytest.mark.django_db
def test_a_new_hire_submits_documents_and_hr_confirms_them(api, onboarding_record, make_user, campus):
    from people.models import Onboarding, OnboardingStep

    record = Onboarding.objects.get(pk=onboarding_record["id"])
    new_hire_user = make_user("keron.fraser", "employee", campus=campus)
    record.employee.user = new_hire_user
    record.employee.save()
    mine = _signed_in(new_hire_user)

    refused = mine.post(f"/api/v1/onboarding/{record.pk}/transition/", {"action": "submit_documents"})
    assert refused.status_code == 409 and refused.json()["code"] == "no_documents"

    upload = mine.post(
        f"/api/v1/onboarding/{record.pk}/documents/",
        {"title": "Signed contract", "doc_type": "contract", "file": _pdf()},
        format="multipart",
    )
    assert upload.status_code == 201, upload.content

    submitted = mine.post(f"/api/v1/onboarding/{record.pk}/transition/", {"action": "submit_documents"})
    assert submitted.status_code == 200 and submitted.json()["state"] == "documents_submitted"

    # The new hire cannot confirm their own documents; HR does.
    assert (
        mine.post(f"/api/v1/onboarding/{record.pk}/transition/", {"action": "confirm_documents"}).status_code
        == 403
    )

    confirmed = api.post(f"/api/v1/onboarding/{record.pk}/transition/", {"action": "confirm_documents"})
    assert confirmed.status_code == 200 and confirmed.json()["state"] == "in_progress"
    documents_step = OnboardingStep.objects.get(onboarding=record, code="documents")
    assert documents_step.state == "done"


def _pdf():
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("contract.pdf", b"%PDF-1.4\n", content_type="application/pdf")


@pytest.mark.django_db
def test_onboarding_completes_once_every_step_is_closed(api, onboarding_record):
    from notifications.models import Notification
    from people.models import Employee, Onboarding

    record_id = onboarding_record["id"]
    url = f"/api/v1/onboarding/{record_id}"
    # documents: not needed; account: opened; equipment and induction: done.
    api.post(f"{url}/steps/documents/clear/", {"done": False}, format="json")
    opened = api.post(f"{url}/open-account/")
    assert opened.status_code == 200
    employee_id = opened.json()["employee"]
    api.post(f"{url}/steps/equipment/clear/", {"done": True}, format="json")
    api.post(f"{url}/steps/induction/clear/", {"done": True}, format="json")

    completed = api.post(f"{url}/transition/", {"action": "complete"})
    assert completed.status_code == 200 and completed.json()["state"] == "completed"
    employee = Employee.objects.get(pk=employee_id)
    assert employee.status == Employee.Status.ACTIVE
    assert employee.user_id is not None
    record = Onboarding.objects.get(pk=record_id)
    assert record.completed_at is not None
    assert Notification.objects.filter(title="Your onboarding is complete").exists()


@pytest.mark.django_db
def test_opening_the_account_refuses_once_already_open(api, onboarding_record):
    url = f"/api/v1/onboarding/{onboarding_record['id']}/open-account/"
    assert api.post(url).status_code == 200
    again = api.post(url)
    assert again.status_code == 409 and again.json()["code"] == "account_step_closed"


@pytest.mark.django_db
def test_completing_is_refused_while_a_step_is_still_open(api, onboarding_record):
    url = f"/api/v1/onboarding/{onboarding_record['id']}/transition/"
    refused = api.post(url, {"action": "complete"})
    assert refused.status_code == 409 and refused.json()["code"] == "steps_open"


@pytest.mark.django_db
def test_cancelling_onboarding_ends_the_appointment(api, onboarding_record):
    from people.models import Assignment, Employee

    cancelled = api.post(
        f"/api/v1/onboarding/{onboarding_record['id']}/transition/",
        {"action": "cancel", "comment": "The offer was withdrawn before the start date"},
    )
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    employee = Employee.objects.get(pk=onboarding_record["employee"])
    assert employee.status == Employee.Status.SEPARATED
    assignment = Assignment.objects.get(employee=employee)
    assert assignment.status == Assignment.Status.ENDED


@pytest.mark.django_db
def test_a_new_hire_sees_only_their_own_onboarding(api, onboarding_record, make_user, campus):
    from people.models import Onboarding

    record = Onboarding.objects.get(pk=onboarding_record["id"])
    new_hire_user = make_user("keron.fraser", "employee", campus=campus)
    record.employee.user = new_hire_user
    record.employee.save()
    mine = _signed_in(new_hire_user)

    seen = mine.get("/api/v1/onboarding/").json()
    assert seen["count"] == 1 and seen["results"][0]["id"] == record.pk

    other = _signed_in(make_user("someone.else", "employee", campus=campus))
    assert other.get("/api/v1/onboarding/").json()["count"] == 0


@pytest.mark.django_db
def test_the_nightly_job_reminds_hr_of_onboarding_left_open(onboarding_record):
    from notifications.models import Notification
    from people.models import Onboarding

    record = Onboarding.objects.get(pk=onboarding_record["id"])
    record.started_on = TODAY() - timedelta(days=10)
    record.save(update_fields=["started_on"])

    from people.onboarding_tasks import alert_overdue_onboarding

    assert alert_overdue_onboarding(TODAY()) == 1
    assert Notification.objects.filter(title__startswith="Onboarding overdue").exists()
    # Not yet due: nothing sent.
    record.started_on = TODAY()
    record.save(update_fields=["started_on"])
    assert alert_overdue_onboarding(TODAY()) == 0
