"""H-W01 (Phase B): vacancies, applications through to a decision, interview scheduling with no
double-booking, the status check open to a candidate, and the bare hire record."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.core import mail
from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from recruitment.models import Application, Candidate, Hire, Interview, Vacancy
from recruitment.reference import plain
from recruitment.workflow import APPLICATION

# Brackets "today" generously, whenever the suite runs, so Vacancy.is_open does not depend on the date.
OPENS = dj_timezone.localdate() - timedelta(days=30)
CLOSES = dj_timezone.localdate() + timedelta(days=60)


@pytest.fixture
def vacancy(unit, hr_officer):
    from org.models import Position

    position = Position.objects.get(number="LIV-001")
    return Vacancy.objects.create(
        position=position, opens_on=OPENS, closes_on=CLOSES, created_by=hr_officer, updated_by=hr_officer
    )


@pytest.fixture
def candidate():
    return Candidate.objects.create(first_name="Keron", last_name="Fraser", email="keron@example.com")


@pytest.fixture
def application(vacancy, candidate):
    return Application.objects.create(vacancy=vacancy, candidate=candidate)


@pytest.fixture
def shortlisted(application, hr_officer, rf):
    request = rf.post("/")
    request.user = hr_officer
    APPLICATION.apply(application, "shortlist", request=request)
    return application


@pytest.fixture
def interviewer(campus):
    from people.models import Employee

    # No email and no linked user: exercises the "no reachable address" branch of send_interview_invite.
    return Employee.objects.create(
        employee_no="E0099",
        first_name="Nadira",
        last_name="Khan",
        date_of_birth=date(1985, 5, 20),
        gender="F",
        campus=campus,
    )


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 10, hour, minute, tzinfo=UTC)


# -- Vacancy --


@pytest.mark.django_db
def test_vacancy_defaults_its_title_from_the_post(unit):
    from org.models import Position

    position = Position.objects.get(number="LIV-002")
    vacancy = Vacancy.objects.create(position=position, opens_on=OPENS, closes_on=CLOSES)
    assert vacancy.title == "Farm Hand"


@pytest.mark.django_db
def test_vacancy_is_open_only_within_its_dates_and_state(unit):
    from org.models import Position

    position = Position.objects.get(number="LIV-001")
    vacancy = Vacancy.objects.create(position=position, opens_on=date(2020, 1, 1), closes_on=date(2020, 2, 1))
    assert vacancy.is_open is False  # closed by date, even though state defaults to "open"


@pytest.mark.django_db
def test_an_employee_may_not_write_a_vacancy(api_employee, unit):
    from org.models import Position

    response = api_employee.post(
        "/api/v1/recruitment/vacancies/",
        {"position": Position.objects.get(number="LIV-001").id, "opens_on": OPENS, "closes_on": CLOSES},
    )
    assert response.status_code == 403


@pytest.fixture
def api_employee(make_user, campus):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_login(make_user("some.employee", "employee", campus=campus))
    return client


# -- Application: submission and the workflow --


@pytest.mark.django_db
def test_submitting_an_application_emails_the_candidate_their_reference_and_code(api, vacancy):
    response = api.post(
        "/api/v1/recruitment/applications/",
        {
            "vacancy": vacancy.id,
            "candidate": {
                "first_name": "Keron",
                "last_name": "Fraser",
                "email": "keron@example.com",
                "phone": "+592 600 1234",
            },
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    body = response.data
    assert body["state"] == "submitted"
    assert body["reference"].startswith("GSA-APP-")
    assert len(mail.outbox) == 1
    assert body["reference"] in mail.outbox[0].body


@pytest.mark.django_db
def test_an_application_cannot_be_made_against_a_closed_vacancy(api, unit):
    from org.models import Position

    closed = Vacancy.objects.create(
        position=Position.objects.get(number="LIV-002"),
        opens_on=OPENS,
        closes_on=CLOSES,
        state=Vacancy.State.CLOSED,
    )
    response = api.post(
        "/api/v1/recruitment/applications/",
        {
            "vacancy": closed.id,
            "candidate": {"first_name": "A", "last_name": "B", "email": "ab@example.com"},
        },
        format="json",
    )
    assert response.status_code == 400
    assert "not open" in str(response.data["vacancy"])


@pytest.mark.django_db
def test_the_application_moves_through_shortlist_offer_and_accept(api, application):
    def act(action: str, **extra):
        url = f"/api/v1/recruitment/applications/{application.id}/transition/"
        return api.post(url, {"action": action, **extra})

    assert act("shortlist").data["state"] == "shortlisted"
    application.refresh_from_db()
    # Interviewing happens through InterviewViewSet in its own tests; jump straight to interviewed here.
    application.state = Application.State.INTERVIEWED
    application.save(update_fields=["state"])
    assert act("offer").data["state"] == "offered"
    response = act("accept")
    assert response.data["state"] == "accepted"
    assert Hire.objects.filter(application=application).exists()


@pytest.mark.django_db
def test_rejecting_an_application_requires_a_comment_and_sets_a_retention_date(api, application):
    refused = api.post(f"/api/v1/recruitment/applications/{application.id}/transition/", {"action": "reject"})
    assert refused.status_code == 409
    assert refused.data["code"] == "comment_required"

    ok = api.post(
        f"/api/v1/recruitment/applications/{application.id}/transition/",
        {"action": "reject", "comment": "Did not meet the minimum qualification."},
    )
    assert ok.status_code == 200
    application.refresh_from_db()
    assert application.state == "rejected"
    assert application.candidate.retention_date is not None


@pytest.mark.django_db
def test_an_illegal_transition_is_refused_with_a_code(api, application):
    response = api.post(f"/api/v1/recruitment/applications/{application.id}/transition/", {"action": "offer"})
    assert response.status_code == 409
    assert response.data["code"] == "invalid_transition"


@pytest.mark.django_db
def test_schedule_interview_cannot_be_taken_as_a_plain_transition(api, shortlisted):
    """It must only ever happen as a side effect of InterviewViewSet.create, so the two never disagree."""
    response = api.post(
        f"/api/v1/recruitment/applications/{shortlisted.id}/transition/", {"action": "schedule_interview"}
    )
    assert response.status_code == 409
    assert response.data["code"] == "use_interview_endpoint"
    shortlisted.refresh_from_db()
    assert shortlisted.state == "shortlisted"


@pytest.mark.django_db
def test_an_application_is_not_deleted(api, application):
    response = api.delete(f"/api/v1/recruitment/applications/{application.id}/")
    assert response.status_code == 409
    assert Application.objects.filter(pk=application.pk).exists()


# -- Interview scheduling: no double-booking --


@pytest.mark.django_db
def test_scheduling_an_interview_moves_the_application_and_sends_invites(api, shortlisted, interviewer):
    response = api.post(
        "/api/v1/recruitment/interviews/",
        {
            "application": shortlisted.id,
            "interviewer": interviewer.id,
            "starts_at": _at(9).isoformat(),
            "location": "HR conference room",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    # The default duration (RECRUITMENT_DEFAULT_INTERVIEW_MINUTES, 45) filled in the end time.
    created = Interview.objects.get(pk=response.data["id"])
    assert created.ends_at - created.starts_at == timedelta(minutes=45)
    shortlisted.refresh_from_db()
    assert shortlisted.state == "interview_scheduled"
    assert len(mail.outbox) == 1  # the candidate; the interviewer in this fixture has no reachable address
    assert mail.outbox[0].attachments[0][0] == "invite.ics"


@pytest.mark.django_db
def test_an_interview_cannot_be_scheduled_before_shortlisting(api, application, interviewer):
    response = api.post(
        "/api/v1/recruitment/interviews/",
        {"application": application.id, "interviewer": interviewer.id, "starts_at": _at(9).isoformat()},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "invalid_transition"


@pytest.mark.django_db
def test_the_same_interviewer_cannot_be_double_booked(interviewer, vacancy):
    first_candidate = Candidate.objects.create(first_name="A", last_name="One", email="a@example.com")
    second_candidate = Candidate.objects.create(first_name="B", last_name="Two", email="b@example.com")
    first = Application.objects.create(vacancy=vacancy, candidate=first_candidate, state="shortlisted")
    second = Application.objects.create(vacancy=vacancy, candidate=second_candidate, state="shortlisted")
    from uuid import uuid4

    Interview.objects.create(
        application=first, interviewer=interviewer, starts_at=_at(9), ends_at=_at(10), ics_uid=uuid4()
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Interview.objects.create(
            application=second, interviewer=interviewer, starts_at=_at(9), ends_at=_at(10), ics_uid=uuid4()
        )
    # A different, non-overlapping time for the same interviewer is fine.
    Interview.objects.create(
        application=second, interviewer=interviewer, starts_at=_at(10), ends_at=_at(11), ics_uid=uuid4()
    )


@pytest.mark.django_db
def test_the_double_booking_refusal_reads_as_a_clean_409_through_the_api(api, interviewer, vacancy):
    first_candidate = Candidate.objects.create(first_name="A", last_name="One", email="a@example.com")
    second_candidate = Candidate.objects.create(first_name="B", last_name="Two", email="b@example.com")
    first = Application.objects.create(vacancy=vacancy, candidate=first_candidate, state="shortlisted")
    second = Application.objects.create(vacancy=vacancy, candidate=second_candidate, state="shortlisted")
    from uuid import uuid4

    Interview.objects.create(
        application=first, interviewer=interviewer, starts_at=_at(9), ends_at=_at(10), ics_uid=uuid4()
    )
    response = api.post(
        "/api/v1/recruitment/interviews/",
        {
            "application": second.id,
            "interviewer": interviewer.id,
            "starts_at": _at(9).isoformat(),
            "ends_at": _at(10).isoformat(),
        },
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "slot_taken"
    second.refresh_from_db()
    assert second.state == "shortlisted"  # the workflow transition never ran


@pytest.mark.django_db
def test_cancelling_and_rescheduling_an_interview_sends_updated_invites(api, shortlisted, interviewer):
    created = api.post(
        "/api/v1/recruitment/interviews/",
        {"application": shortlisted.id, "interviewer": interviewer.id, "starts_at": _at(9).isoformat()},
        format="json",
    )
    interview_id = created.data["id"]
    mail.outbox.clear()

    cancelled = api.post(f"/api/v1/recruitment/interviews/{interview_id}/cancel/")
    assert cancelled.data["state"] == "cancelled"
    assert mail.outbox[0].subject.endswith("cancelled")

    mail.outbox.clear()
    moved = api.post(
        f"/api/v1/recruitment/interviews/{interview_id}/reschedule/", {"starts_at": _at(13).isoformat()}
    )
    assert moved.data["state"] == "scheduled"
    assert Interview.objects.get(pk=interview_id).starts_at == _at(13)
    assert len(mail.outbox) == 1


# -- Checking an application's progress without an account --


@pytest.mark.django_db
def test_a_candidate_can_check_their_own_application_by_reference_and_code(api, application):
    response = api.post(
        "/api/v1/recruitment/check/", {"reference": application.reference, "code": application.check_code}
    )
    assert response.status_code == 200
    assert response.data["found"] is True
    assert response.data["state"] == "submitted"


@pytest.mark.django_db
def test_a_wrong_code_gives_the_same_shape_of_answer_as_an_unknown_reference(api, application):
    wrong = api.post(
        "/api/v1/recruitment/check/", {"reference": application.reference, "code": "0000-0000-0000"}
    )
    unknown = api.post("/api/v1/recruitment/check/", {"reference": "GSA-APP-0000-0000", "code": "x"})
    assert (
        wrong.data
        == unknown.data
        == {
            "found": False,
            "detail": wrong.data["detail"],
            "reference": None,
            "vacancy": None,
            "state": None,
            "state_label": None,
            "submitted_at": None,
        }
    )


@pytest.mark.django_db
def test_checking_is_open_to_anyone_without_signing_in(application):
    from rest_framework.test import APIClient

    anonymous = APIClient()
    response = anonymous.post(
        "/api/v1/recruitment/check/", {"reference": application.reference, "code": application.check_code}
    )
    assert response.status_code == 200
    assert response.data["found"] is True


@pytest.mark.django_db
def test_too_many_wrong_codes_are_refused(settings, application):
    from rest_framework.test import APIClient

    settings.RECRUITMENT_CHECK_FAILURES = 2
    anonymous = APIClient()
    for _ in range(2):
        anonymous.post("/api/v1/recruitment/check/", {"reference": application.reference, "code": "wrong"})
    blocked = anonymous.post(
        "/api/v1/recruitment/check/", {"reference": application.reference, "code": application.check_code}
    )
    assert blocked.status_code == 429
    assert blocked.data["code"] == "too_many_attempts"


@pytest.mark.django_db
def test_the_check_code_normalises_dashes_case_and_look_alike_letters():
    assert plain("ab12-cd34") == plain("AB12CD34")
    assert plain("O1l-I0O1") == plain("011-1001")


# -- Candidate PII --


@pytest.mark.django_db
def test_a_candidates_national_id_is_never_returned_in_the_clear(api, vacancy):
    response = api.post(
        "/api/v1/recruitment/applications/",
        {
            "vacancy": vacancy.id,
            "candidate": {
                "first_name": "Priya",
                "last_name": "Narine",
                "email": "priya@example.com",
                "national_id": "123456789",
            },
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    candidate_body = response.data["candidate"]
    assert "national_id" not in candidate_body
    assert candidate_body["national_id_masked"].endswith("789")
    assert "123456789" not in str(candidate_body)
