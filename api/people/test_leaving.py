"""Items 1.12 to 1.14: leaving, the notice the law asks for, and the figures owed on leaving."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from people import leaving

TODAY = timezone.localdate


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def leaver(employee, unit, make_user, campus):
    """Asha in LIV-001 (GS5, G$250,000 a month) since 2 September 2019, confirmed, on a contract with 30 days'
    notice; 7.5 days of annual leave left; an account of her own."""
    from leave.models import LeaveLedger, LeaveType
    from org.models import Position
    from people.models import Assignment, Contract

    employee.user = make_user("asha.persaud", "employee", campus=campus)
    employee.save()
    assignment = Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2019, 9, 2),
        probation_end=date(2020, 3, 1),
        confirmed_on=date(2020, 3, 1),
    )
    Contract.objects.create(
        assignment=assignment, contract_type="open_ended", hours_per_week=Decimal("40"), notice_period_days=30
    )
    annual = LeaveType.objects.get(code="ANN")
    LeaveLedger.objects.create(
        employee=employee, leave_type=annual, entry_date=date(2026, 1, 1), days=10, reason="accrual"
    )
    LeaveLedger.objects.create(
        employee=employee,
        leave_type=annual,
        entry_date=date(2026, 3, 2),
        days=Decimal("-2.5"),
        reason="taken",
    )
    return employee


def _leave(client, employee, reason="resignation", *, last=None, notice=None, note="Taking up a post abroad"):
    body = {
        "employee": employee.id,
        "reason": reason,
        "last_day": (last or TODAY() + timedelta(days=5)).isoformat(),
    }
    if notice is not None:
        body["notice_given_on"] = notice.isoformat()
    body["note"] = note
    return client.post("/api/v1/separations/", body, format="json")


def test_severance_follows_the_statutory_scale():
    years = (0, 1, 3, 5, 6, 7, 10, 11, 12, 22, 23, 40)
    assert [leaving.severance_weeks(y) for y in years] == [0, 1, 3, 5, 7, 9, 15, 18, 21, 51, 52, 52]
    assert leaving.add_month(date(2026, 1, 31)) == date(2026, 2, 28)
    assert leaving.add_month(date(2026, 12, 15)) == date(2027, 1, 15)
    assert leaving.completed_years(date(2019, 9, 2), date(2026, 9, 1)) == 6
    assert leaving.completed_years(date(2019, 9, 2), date(2026, 9, 2)) == 7


@pytest.mark.django_db
def test_the_notice_the_law_and_the_contract_ask_for(leaver):
    from people.models import Assignment
    from people.services import current_contract

    resign = leaving.notice(leaver, "resignation", date(2026, 10, 1), date(2026, 10, 15))
    assert resign == {
        "needed": True,
        "given_by": "employee",
        "given_on": "2026-10-01",
        "rule": "one month, employed a year or more",
        "full_notice_ends": "2026-11-01",
        "short_by_days": 17,
    }
    contract = current_contract(leaver)
    contract.notice_period_days = 60
    contract.save()
    longer = leaving.notice(leaver, "notice", date(2026, 10, 1), date(2026, 11, 30))
    assert longer["rule"] == "60 days, as the contract says (the law asks for one month)"
    assert (longer["given_by"], longer["full_notice_ends"], longer["short_by_days"]) == (
        "school",
        "2026-11-30",
        0,
    )
    assert leaving.notice(leaver, "dismissal", None, date(2026, 10, 15))["needed"] is False

    newcomer = Assignment.objects.get(employee=leaver)
    newcomer.start_date, newcomer.probation_end, newcomer.confirmed_on = (
        date(2026, 6, 1),
        date(2026, 12, 1),
        None,
    )
    newcomer.save()
    in_probation = leaving.notice(leaver, "resignation", date(2026, 10, 1), date(2026, 10, 2))
    assert in_probation == {
        "needed": False,
        "why": "During probation either side may end the employment without notice.",
    }
    newcomer.probation_end = date(2026, 9, 1)
    newcomer.save()
    contract.notice_period_days = None
    contract.save()
    assert leaving.notice(leaver, "resignation", date(2026, 10, 1), date(2026, 10, 10))["rule"] == (
        "two weeks, employed under a year"
    )


@pytest.mark.django_db
def test_the_figures_owed_on_redundancy_and_on_resignation(api, leaver):
    from people.models import Separation

    redundancy = Separation(
        employee=leaver, reason="redundancy", notice_given_on=date(2026, 12, 1), last_day=date(2026, 12, 31)
    )
    figures = leaving.settlement(redundancy)
    assert (figures["monthly"], figures["weekly"], figures["daily"]) == ("250000.00", "57692.31", "11538.46")
    assert figures["completed_years"] == 7 and figures["service_from"] == "2019-09-02"
    assert [(line["key"], line["amount"]) for line in figures["lines"]] == [
        ("leave", "86538.46"),
        ("notice", "8241.76"),
        ("severance", "519230.77"),
    ]
    assert figures["lines"][0]["label"] == "Annual leave not taken: 7.5 days"
    assert figures["lines"][2]["label"] == "Severance: 9 weeks' wages for 7 completed years of service"
    assert figures["total"] == "614010.99"

    resignation = Separation(
        employee=leaver, reason="resignation", notice_given_on=date(2026, 12, 1), last_day=date(2026, 12, 31)
    )
    assert [line["key"] for line in leaving.settlement(resignation)["lines"]] == [
        "leave"
    ]  # nothing else owed

    preview = api.post(
        "/api/v1/separations/preview/",
        {
            "employee": leaver.id,
            "reason": "redundancy",
            "notice_given_on": "2026-12-01",
            "last_day": "2026-12-31",
            "note": "x",
        },
        format="json",
    ).json()
    assert preview["notice"]["short_by_days"] == 1 and preview["settlement"]["total"] == "614010.99"
    assert not Separation.objects.exists()  # a preview records nothing


@pytest.mark.django_db
def test_leaving_completes_the_night_after_the_last_day(api, leaver):
    from notifications.models import Notification
    from people.models import Assignment, CareerEvent, Employee, Separation

    last = TODAY() + timedelta(days=5)
    later = CareerEvent.objects.create(
        employee=leaver,
        kind="confirmation",
        effective_date=last + timedelta(days=10),
        reason="x",
        from_assignment=leaver.current_assignment,
    )
    recorded = _leave(api, leaver, last=last, notice=TODAY() - timedelta(days=10))
    assert recorded.status_code == 201, recorded.content
    body = recorded.json()
    assert body["state"] == "leaving" and body["notice"]["given_by"] == "employee"
    assert body["settlement"]["lines"][0]["key"] == "leave" and body["letter_answers"] == {
        "last_day": last.isoformat()
    }
    assert _leave(api, leaver, notice=TODAY()).json()["code"] == "already_leaving"

    assert leaving.complete_due(last) == 0  # the last day is still a working day
    assert leaving.complete_due(last + timedelta(days=1)) == 1
    leaver.refresh_from_db()
    leaver.user.refresh_from_db()
    assert leaver.status == Employee.Status.SEPARATED and leaver.user.is_active is False
    ended = Assignment.objects.get(employee=leaver)
    assert ended.status == Assignment.Status.ENDED and ended.end_date == last
    later.refresh_from_db()
    assert later.state == CareerEvent.State.CANCELLED
    left = Separation.objects.get(pk=body["id"])
    assert left.state == Separation.State.LEFT and left.settlement["total"] == body["settlement"]["total"]
    assert AuditLog.objects.filter(action="account_deactivated", entity_id=leaver.user.id).exists()
    assert Notification.objects.filter(
        title=f"{leaver.full_name} has left: the settlement figures are ready"
    ).exists()
    assert _leave(api, leaver, notice=TODAY()).json()["code"] == "left"


@pytest.mark.django_db
def test_a_leaving_recorded_after_the_last_day_takes_effect_at_once(api, leaver):
    gone = _leave(
        api, leaver, "dismissal", last=TODAY() - timedelta(days=1), note="Gross misconduct, after a hearing"
    )
    assert gone.status_code == 201 and gone.json()["state"] == "left"
    assert gone.json()["notice"] == {
        "needed": False,
        "why": "No notice is needed when employment ends this way.",
    }


@pytest.mark.django_db
def test_leaving_is_checked_and_kept_to_hr(api, leaver, make_user, campus):
    from org.models import Campus

    assert _leave(api, leaver).json()["code"] == "notice_date"  # a resignation says when notice was given
    after = _leave(api, leaver, notice=TODAY() + timedelta(days=9))
    assert after.json()["code"] == "notice_after"
    assert _leave(api, leaver, "probation", notice=None).json()["code"] == "not_in_probation"
    early = _leave(api, leaver, "contract_end", last=date(2019, 1, 1))
    assert early.json()["code"] == "too_early"
    assert _leave(api, leaver, notice=TODAY(), note="").json()["note"] == ["Say why."]
    elsewhere = _signed_in(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    assert "employee" in _leave(elsewhere, leaver, notice=TODAY()).json()
    supervisor = _signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert supervisor.get("/api/v1/separations/").status_code == 403


@pytest.mark.django_db
def test_a_leaving_can_be_withdrawn_before_it_happens(api, leaver):
    recorded = _leave(api, leaver, notice=TODAY()).json()
    withdrawn = api.post(
        f"/api/v1/separations/{recorded['id']}/withdraw/", {"reason": "Resignation taken back"}, format="json"
    )
    assert withdrawn.json()["state"] == "withdrawn" and withdrawn.json()["settlement"] is None
    again = api.post(f"/api/v1/separations/{recorded['id']}/withdraw/", {"reason": "x"}, format="json")
    assert again.status_code == 400 and again.json()["code"] == "not_leaving"
    assert _leave(api, leaver, notice=TODAY()).status_code == 201  # another may be recorded


@pytest.mark.django_db
def test_a_certificate_of_service_names_the_post_last_held(api, leaver):
    from letters.models import Letter, LetterTemplate

    gone = _leave(api, leaver, "retirement", last=TODAY() - timedelta(days=1), note="Retired at 60").json()
    template = LetterTemplate.objects.get(code="certificate_of_service")
    issued = api.post(
        "/api/v1/letters/",
        {"employee": leaver.id, "template": template.id, "answers": gone["letter_answers"]},
        format="json",
    )
    assert issued.status_code == 201, issued.content
    letter = Letter.objects.get(pk=issued.json()["id"])
    assert letter.values["post_title"] == "Livestock Instructor" and letter.values["last_day"]
