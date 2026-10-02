"""The retention schedule, reviewed disposal and the breach register (item 1.32)."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from notifications.models import Notification
from privacy.models import DisposalRun, RetentionRule
from privacy.retention import months_after, months_before, purge
from privacy.tasks import retention_purge

PDF = b"%PDF-1.4\n%fictional doctor's note\n"


def signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def administrator(make_user, seeded):
    return make_user("sys.admin", "administrator")


def leave_with_note(employee, *, ended: date, doc_type: str = "medical"):
    from leave.models import LeaveRequest, LeaveType
    from people.models import Document

    note = Document.objects.create(
        employee=employee,
        doc_type=doc_type,
        title=f"Doctor's note: sick leave ending {ended:%d/%m/%Y}",
        file=SimpleUploadedFile("note.pdf", PDF, content_type="application/pdf"),
        classification=Document.Classification.MEDICAL
        if doc_type == "medical"
        else Document.Classification.CONFIDENTIAL,
    )
    request = LeaveRequest.objects.create(
        employee=employee,
        leave_type=LeaveType.objects.get(code="SIC"),
        from_date=ended - timedelta(days=1),
        to_date=ended,
        days=2,
        state="approved",
        evidence=note,
    )
    return note, request


def rule(code: str) -> RetentionRule:
    return RetentionRule.objects.get(code=code)


def test_months_are_counted_as_people_count_them():
    assert months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)
    assert months_before(date(2026, 10, 1), 24) == date(2024, 10, 1)
    assert months_after(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert months_after(date(2025, 12, 15), 1) == date(2026, 1, 15)


@pytest.mark.django_db
def test_old_doctors_notes_are_destroyed_only_when_a_second_person_approves(
    hr_manager, administrator, employee
):
    from people.models import Document

    today = timezone.localdate()
    old_note, old_leave = leave_with_note(employee, ended=months_before(today, 25))
    recent_note, _ = leave_with_note(employee, ended=months_before(today, 6))
    stored = old_note.file.storage
    stored_name = old_note.file.name
    assert stored.exists(stored_name)

    manager = signed_in(hr_manager)
    found = manager.post(f"/api/v1/privacy/retention-rules/{rule('doctors-notes').id}/find/")
    assert found.status_code == 201, found.content
    run = found.json()["run"]
    assert [item["employee_no"] for item in run["items"]] == ["E0001"]
    assert run["proposed_by"] == "hr.manager" and run["state"] == "proposed" and run["proposed_by_me"] is True
    assert Notification.objects.filter(
        recipient=administrator, title__startswith="Records to dispose of"
    ).exists()

    same = manager.post(f"/api/v1/privacy/disposal-runs/{run['id']}/approve/")
    assert same.status_code == 403 and same.json()["code"] == "same_person"
    assert Document.objects.filter(pk=old_note.pk).exists()

    approved = signed_in(administrator).post(f"/api/v1/privacy/disposal-runs/{run['id']}/approve/").json()
    assert approved["state"] == "done" and approved["items"][0]["disposed_at"]
    assert not Document.objects.filter(pk=old_note.pk).exists() and not stored.exists(stored_name)
    assert Document.objects.filter(pk=recent_note.pk).exists()
    old_leave.refresh_from_db()
    assert old_leave.evidence is None
    gone = AuditLog.objects.get(action="disposed")
    assert gone.subject == employee.id and gone.entity_id == old_note.pk
    assert gone.reason.startswith("Retention schedule: Doctor's notes")
    assert gone.before["title"] == old_note.title  # what was destroyed stays on record

    again = manager.post(f"/api/v1/privacy/retention-rules/{rule('doctors-notes').id}/find/")
    assert again.json() == {"detail": "Nothing is due under this rule.", "run": None}


@pytest.mark.django_db
def test_a_record_can_be_kept_back_with_the_reason(hr_manager, administrator, employee):
    from people.models import Document

    note, _ = leave_with_note(
        employee, ended=months_before(timezone.localdate(), 30), doc_type="leave_evidence"
    )
    run = (
        signed_in(hr_manager)
        .post(f"/api/v1/privacy/retention-rules/{rule('leave-evidence').id}/find/")
        .json()["run"]
    )
    url = f"/api/v1/privacy/disposal-runs/{run['id']}/keep/"
    assert (
        signed_in(hr_manager)
        .post(url, {"item": run["items"][0]["id"], "reason": ""}, format="json")
        .status_code
        == 400
    )
    kept = signed_in(hr_manager).post(
        url, {"item": run["items"][0]["id"], "reason": "Needed for a tribunal hearing"}, format="json"
    )
    assert kept.json()["items"][0]["keep_reason"] == "Needed for a tribunal hearing"
    assert signed_in(hr_manager).post(url, {"item": 999999, "reason": "x"}, format="json").status_code == 404
    signed_in(administrator).post(f"/api/v1/privacy/disposal-runs/{run['id']}/approve/")
    assert Document.objects.filter(pk=note.pk).exists()
    assert AuditLog.objects.get(action="disposal_approved").after == {"disposed": 0, "kept": 1}
    decided = signed_in(hr_manager).post(
        url, {"item": run["items"][0]["id"], "reason": "late"}, format="json"
    )
    assert decided.status_code == 409


@pytest.mark.django_db
def test_one_run_waits_per_rule_and_a_run_can_be_cancelled(hr_manager, employee):
    leave_with_note(employee, ended=months_before(timezone.localdate(), 30))
    manager = signed_in(hr_manager)
    url = f"/api/v1/privacy/retention-rules/{rule('doctors-notes').id}/find/"
    run = manager.post(url).json()["run"]
    second = manager.post(url)
    assert second.status_code == 409 and second.json()["code"] == "open_run"
    assert manager.get("/api/v1/privacy/retention-rules/").json()[0]["open_run"] in {run["id"], None}
    cancelled = manager.post(f"/api/v1/privacy/disposal-runs/{run['id']}/cancel/").json()
    assert cancelled["state"] == "cancelled"
    assert manager.post(url).status_code == 201  # a new run may now be proposed
    assert DisposalRun.objects.count() == 2


@pytest.mark.django_db
def test_a_document_no_longer_due_when_the_run_is_approved_is_left(hr_manager, administrator, employee):
    from people.models import Document

    document = Document.objects.create(
        employee=employee,
        doc_type="letter",
        title="Letter of appointment",
        file=SimpleUploadedFile("letter.pdf", PDF, content_type="application/pdf"),
        retention_date=timezone.localdate() - timedelta(days=1),
    )
    run = (
        signed_in(hr_manager)
        .post(f"/api/v1/privacy/retention-rules/{rule('dated-documents').id}/find/")
        .json()["run"]
    )
    Document.objects.filter(pk=document.pk).update(retention_date=timezone.localdate() + timedelta(days=365))
    approved = signed_in(administrator).post(f"/api/v1/privacy/disposal-runs/{run['id']}/approve/").json()
    assert approved["items"][0]["keep_reason"] == "No longer due when the run was approved"
    assert Document.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db
def test_a_changed_period_is_confirmed_again_and_only_keepers_change_it(hr_manager, make_user, api):
    manager = signed_in(hr_manager)
    notes = rule("doctors-notes")
    confirmed = manager.post(f"/api/v1/privacy/retention-rules/{notes.id}/confirm/").json()
    assert confirmed["confirmed"] is True and confirmed["confirmed_by_name"] == "hr.manager"
    changed = manager.patch(
        f"/api/v1/privacy/retention-rules/{notes.id}/", {"keep_months": 36}, format="json"
    ).json()
    assert changed["keep_months"] == 36 and changed["confirmed"] is False
    assert AuditLog.objects.get(action="retention_changed").before["keep_months"] == 24
    dated = rule("dated-documents")
    assert (
        manager.patch(
            f"/api/v1/privacy/retention-rules/{dated.id}/", {"keep_months": 12}, format="json"
        ).status_code
        == 400
    )
    assert (
        manager.patch(
            f"/api/v1/privacy/retention-rules/{notes.id}/", {"keep_months": 0}, format="json"
        ).status_code
        == 400
    )

    auditor = signed_in(make_user("the.auditor", "auditor"))
    assert len(auditor.get("/api/v1/privacy/retention-rules/").json()) == 6
    assert (
        auditor.patch(
            f"/api/v1/privacy/retention-rules/{notes.id}/", {"keep_months": 1}, format="json"
        ).status_code
        == 403
    )
    assert api.get("/api/v1/privacy/retention-rules/").status_code == 403  # an HR officer
    automatic = manager.post(f"/api/v1/privacy/retention-rules/{rule('sign-in-records').id}/find/")
    assert automatic.status_code == 409 and automatic.json()["code"] == "automatic"


@pytest.mark.django_db
def test_old_logs_go_every_night_without_review(hr_officer, seeded):
    from iam.models import LoginAttempt, PasswordResetRequest

    today = timezone.localdate()
    long_ago = timezone.now() - timedelta(days=400)
    old = LoginAttempt.objects.create(username="hr.officer", success=True)
    LoginAttempt.objects.filter(pk=old.pk).update(at=long_ago)
    LoginAttempt.objects.create(username="hr.officer", success=True)
    asked = PasswordResetRequest.objects.create(source_ip="190.80.1.2")
    PasswordResetRequest.objects.filter(pk=asked.pk).update(at=long_ago)
    read = Notification.objects.create(
        recipient=hr_officer, title="Read long ago", read_at=timezone.now() - timedelta(days=800)
    )
    unread = Notification.objects.create(recipient=hr_officer, title="Never read")
    Notification.objects.filter(pk=unread.pk).update(created_at=timezone.now() - timedelta(days=800))

    assert purge(today) == {"sign-in-records": 2, "letter-checks": 0, "read-notifications": 1}
    assert LoginAttempt.objects.count() == 1 and not PasswordResetRequest.objects.exists()
    assert (
        not Notification.objects.filter(pk=read.pk).exists()
        and Notification.objects.filter(pk=unread.pk).exists()
    )
    assert AuditLog.objects.filter(action="purged").count() == 2
    assert retention_purge() == {"sign-in-records": 0, "letter-checks": 0, "read-notifications": 0}


@pytest.mark.django_db
def test_a_breach_is_recorded_followed_up_and_closed(hr_manager, administrator, make_user):
    manager = signed_in(hr_manager)
    breach = manager.post(
        "/api/v1/privacy/breaches/",
        {
            "discovered_at": "2026-10-01T09:00:00-04:00",
            "summary": "A staff list was emailed to the wrong address.",
            "data_affected": "Names and phone numbers of 12 Mon Repos staff",
            "people_affected": 12,
            "risk": "medium",
        },
        format="json",
    )
    assert breach.status_code == 201, breach.content
    record = breach.json()
    year = timezone.localdate().year
    assert record["reference"] == f"BR-{year}-001" and record["recorded_by"] == "hr.manager"
    assert Notification.objects.filter(
        recipient=administrator, title__startswith="Personal data breach"
    ).exists()

    url = f"/api/v1/privacy/breaches/{record['id']}/"
    early = manager.post(f"{url}close/")
    assert early.status_code == 409 and early.json()["code"] == "not_contained"
    manager.patch(
        url, {"contained_at": "2026-10-01T11:00:00-04:00", "actions": "Recipient deleted it."}, format="json"
    )
    closed = manager.post(f"{url}close/").json()
    assert closed["closed_at"] and manager.post(f"{url}close/").status_code == 409
    assert {"create", "update", "breach_closed"} <= set(
        AuditLog.objects.filter(entity="privacy.breach").values_list("action", flat=True)
    )
    second = manager.post("/api/v1/privacy/breaches/", {**breach.json(), "summary": "Another"}, format="json")
    assert second.json()["reference"] == f"BR-{year}-002"

    auditor = signed_in(make_user("the.auditor", "auditor"))
    assert auditor.get("/api/v1/privacy/breaches/").json()["count"] == 2
    assert auditor.post("/api/v1/privacy/breaches/", {"summary": "x"}, format="json").status_code == 403
