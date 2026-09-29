from datetime import date

import pytest
from django.core import mail
from rest_framework.test import APIClient

from leave.models import LeaveLedger, LeaveType
from notifications.models import Notification


@pytest.mark.django_db
def test_leave_transitions_notify_the_next_actor(employee, make_user, campus, seeded):
    annual = LeaveType.objects.get(code="ANN")
    LeaveLedger.objects.create(
        employee=employee, leave_type=annual, entry_date=date(2026, 1, 1), days=10, reason="opening"
    )
    owner = make_user("owner", "employee", campus=campus)
    owner.email = "asha@gsa.edu.gy"
    owner.save()
    employee.user = owner
    employee.save()
    supervisor = make_user("sup", "supervisor", campus=campus)
    supervisor.email = "hod@gsa.edu.gy"
    supervisor.save()
    hr = make_user("hr3", "hr_officer", campus=campus)

    client = APIClient()
    client.force_login(owner)
    created = client.post(
        "/api/v1/leave/requests/",
        {
            "employee": employee.id,
            "leave_type": annual.id,
            "from_date": "2026-11-09",
            "to_date": "2026-11-10",
        },
        format="json",
    ).json()
    client.post(f"/api/v1/leave/requests/{created['id']}/transition/", {"action": "submit"})
    note = Notification.objects.get(recipient=supervisor)
    assert note.kind == "approval" and "Leave request from Asha Persaud" in note.title
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["hod@gsa.edu.gy"]

    client.force_login(supervisor)
    client.post(f"/api/v1/leave/requests/{created['id']}/transition/", {"action": "approve"})
    assert Notification.objects.filter(recipient=hr, title__contains="awaits HR approval").exists()

    client.force_login(hr)
    client.post(f"/api/v1/leave/requests/{created['id']}/transition/", {"action": "approve"})
    owner_note = Notification.objects.get(recipient=owner)
    assert owner_note.title == "Your leave request was approved"

    # The owner's inbox through the API: unread count, then mark read.
    client.force_login(owner)
    inbox = client.get("/api/v1/notifications/").json()
    assert inbox["unread"] == 1 and inbox["results"][0]["id"] == owner_note.id
    assert client.post(f"/api/v1/notifications/{owner_note.id}/read/").status_code == 200
    assert client.get("/api/v1/notifications/?unread=1").json()["unread"] == 0
    # Nobody else can read or mark the owner's notification.
    client.force_login(hr)
    assert client.post(f"/api/v1/notifications/{owner_note.id}/read/").status_code == 404
