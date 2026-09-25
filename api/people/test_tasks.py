from datetime import date, timedelta

import pytest
from django.core import mail

from notifications.models import Notification
from people.models import Assignment
from people.tasks import alert_contract_expiry, alert_probation_due


@pytest.fixture
def contract_holder(employee, unit, make_user, campus):
    from org.models import Position

    hr = make_user("hr.alerts", "hr_officer", campus=campus)
    hr.email = "hr.alerts@gsa.edu.gy"
    hr.save()
    assignment = Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="contract",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        probation_end=date(2026, 4, 1),
    )
    return hr, assignment


@pytest.mark.django_db
def test_contract_expiry_alert_is_sent_once_per_horizon(contract_holder):
    hr, assignment = contract_holder
    today = assignment.end_date - timedelta(days=30)
    first = alert_contract_expiry(today)
    assert first >= 1  # every HR officer and supervisor of the campus
    note = Notification.objects.get(recipient=hr)
    assert "30 days" in note.title and note.kind == "alert" and note.emailed
    assert len(mail.outbox) >= 1 and "[GSA HRMS]" in mail.outbox[0].subject
    # Re-running the same day does not duplicate; a different horizon does alert again.
    assert alert_contract_expiry(today) == 0
    assert alert_contract_expiry(assignment.end_date - timedelta(days=60)) == first
    assert alert_contract_expiry(today + timedelta(days=1)) == 0


@pytest.mark.django_db
def test_probation_due_alert(contract_holder):
    hr, assignment = contract_holder
    assert alert_probation_due(assignment.probation_end - timedelta(days=30)) >= 1
    assert alert_probation_due(assignment.probation_end - timedelta(days=30)) == 0
    assert Notification.objects.filter(recipient=hr, title__startswith="Probation review due").exists()
