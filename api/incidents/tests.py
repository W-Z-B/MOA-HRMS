"""Item 1.16: the accident and incident register, its notices under the Occupational Safety and Health Act,
and who may read an injury."""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from notifications.models import Notification

TODAY = timezone.localdate()


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


def _at(day) -> str:
    return timezone.make_aware(datetime.combine(day, time(9, 30))).isoformat()


def _report(client, campus, *, kind="accident", day=None, **extra):
    body = {
        "kind": kind,
        "occurred_at": _at(day or TODAY - timedelta(days=6)),
        "campus": campus.id,
        "place": "Feed mill",
        "description": "Slipped on spilt feed by the mixer",
        **extra,
    }
    return client.post("/api/v1/incidents/", body, format="json")


def _person(client, incident_id, **body):
    return client.post(f"/api/v1/incidents/{incident_id}/people/", body, format="json")


def _notice(client, incident_id, duty, recipient, sent_on, person=None):
    body = {"duty": duty, "recipient": recipient, "sent_on": sent_on.isoformat(), "how": "By hand"}
    if person is not None:
        body["person"] = person
    return client.post(f"/api/v1/incidents/{incident_id}/notices/", body, format="json")


def _duties(client, incident_id) -> dict:
    found = client.get(f"/api/v1/incidents/{incident_id}/").json()["duties"]
    return {(d["duty"], d["person"]): d for d in found}


@pytest.fixture
def worker(employee, make_user):
    user = make_user("asha.persaud", "employee")
    employee.user = user
    employee.save()
    return user


@pytest.mark.django_db
def test_anyone_reports_and_hr_is_told(worker, campus, hr_officer, hr_manager):
    client = _signed_in(worker)
    made = _report(client, campus, hurt=True, injury="Sprained left ankle")
    assert made.status_code == 201, made.content
    incident = made.json()
    assert incident["reference"] == f"IN-{(TODAY - timedelta(days=6)).year}-001"
    assert incident["reported_by_me"] and incident["my_injury"]["injury"] == "Sprained left ankle"
    for keeper in (hr_officer, hr_manager):
        assert Notification.objects.filter(recipient=keeper, link=f"/incidents/{incident['id']}").exists()

    assert client.get("/api/v1/incidents/").status_code == 403
    assert client.get(f"/api/v1/incidents/{incident['id']}/").status_code == 404
    assert [i["reference"] for i in client.get("/api/v1/incidents/mine/").json()] == [incident["reference"]]

    rows = AuditLog.objects.filter(entity="incidents.incident")
    assert rows.exists() and not rows.exclude(subject=None).exists()
    assert not any("ankle" in str(row.after) for row in rows)


@pytest.mark.django_db
def test_the_register_is_read_on_ones_campuses_and_injuries_only_by_hr(api, employee, campus, make_user):
    from org.models import Campus

    incident = _report(api, campus).json()
    added = _person(
        api,
        incident["id"],
        who="staff",
        employee=employee.id,
        injury="Cut to the right hand",
        treatment="doctor",
        off_work_from=(TODAY - timedelta(days=6)).isoformat(),
    )
    assert added.status_code == 200, added.content
    (seen_by_hr,) = added.json()["people"]
    assert seen_by_hr["injury"] == "Cut to the right hand" and seen_by_hr["days_off"] == 6

    readers = [
        make_user("unit.head", "supervisor", campus=campus),
        make_user("principal", "principal"),
        make_user("auditor", "auditor"),
    ]
    for reader in readers:
        body = _signed_in(reader).get(f"/api/v1/incidents/{incident['id']}/").json()
        (person,) = body["people"]
        assert person["name"] == "Asha Persaud"
        assert all(person[key] is None for key in ("injury", "treatment", "off_work_from", "days_off"))
        assert not any("back at work" in item or "NIS" in item for item in body["outstanding"])

    elsewhere = _signed_in(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    assert elsewhere.get("/api/v1/incidents/").json()["count"] == 0
    assert elsewhere.get(f"/api/v1/incidents/{incident['id']}/").status_code == 404
    supervisor = _signed_in(readers[0])
    assert _person(supervisor, incident["id"], who="visitor", name="A visitor").status_code == 403


@pytest.mark.django_db
def test_an_accident_keeping_a_worker_off_is_notified_in_four_days_then_when_it_ended(api, employee, campus):
    day = TODAY - timedelta(days=6)
    incident = _report(api, campus, day=day).json()
    person = _person(
        api, incident["id"], who="staff", employee=employee.id, off_work_from=day.isoformat()
    ).json()["people"][0]["id"]

    due = _duties(api, incident["id"])[("disablement", person)]
    assert due["section"] == "69(1)(b)" and due["due_on"] == (day + timedelta(days=4)).isoformat()
    assert due["overdue"] and [t["recipient"] for t in due["to"]] == ["authority", "workers"]

    tomorrow = _notice(api, incident["id"], "disablement", "authority", TODAY + timedelta(days=1), person)
    assert tomorrow.json()["code"] == "future"
    early = _notice(api, incident["id"], "disablement", "authority", day - timedelta(days=1), person)
    assert early.json()["code"] == "before"
    assert (
        _notice(api, incident["id"], "disablement", "authority", day + timedelta(days=3), person).status_code
        == 200
    )
    assert (
        _notice(api, incident["id"], "disablement", "workers", day + timedelta(days=5), person).status_code
        == 200
    )
    again = _notice(api, incident["id"], "disablement", "workers", day + timedelta(days=5), person)
    assert again.status_code == 409 and again.json()["code"] == "recorded"
    assert _notice(api, incident["id"], "death", "authority", TODAY, person).json()["code"] == "not_due"
    assert _notice(api, incident["id"], "disablement", "medical", TODAY, person).json()["code"] == "not_due"
    late = AuditLog.objects.filter(action="incident_notice").order_by("id").values_list("after", flat=True)
    assert [row["late"] for row in late] == [False, True]

    back = api.patch(
        f"/api/v1/incidents/{incident['id']}/people/{person}/",
        {"back_at_work_on": (TODAY - timedelta(days=1)).isoformat()},
        format="json",
    )
    assert back.status_code == 200, back.content
    ended = _duties(api, incident["id"])[("recovered", person)]
    assert ended["section"] == "69(3)" and ended["due_on"] == (TODAY + timedelta(days=13)).isoformat()
    assert not ended["overdue"]

    refused = api.post(f"/api/v1/incidents/{incident['id']}/close/")
    assert refused.status_code == 400 and refused.json()["detail"].startswith(
        "Not yet: Send notice of the day"
    )
    assert "NIS notice of accident (Form IB1)" in refused.json()["detail"]
    assert "Record what the investigation found" in refused.json()["detail"]


@pytest.mark.django_db
def test_a_death_is_notified_forthwith_and_a_later_one_as_a_later_death(api, employee, campus, hr_officer):
    from people.models import Employee

    day = TODAY - timedelta(days=5)
    killed = _report(api, campus, day=day).json()
    person = _person(api, killed["id"], who="staff", employee=employee.id, died_on=day.isoformat()).json()
    (due,) = person["duties"]
    assert (due["duty"], due["section"], due["due_on"]) == ("death", "69(1)(a)", day.isoformat())
    assert due["overdue"]

    other = Employee.objects.create(
        employee_no="E0002",
        first_name="Ravi",
        last_name="Singh",
        date_of_birth=date(1985, 5, 1),
        campus=campus,
    )
    hurt = _report(api, campus, day=day).json()
    ravi = _person(api, hurt["id"], who="staff", employee=other.id, off_work_from=day.isoformat()).json()
    ravi_id = ravi["people"][0]["id"]
    for to in ("authority", "workers"):
        _notice(api, hurt["id"], "disablement", to, day + timedelta(days=1), ravi_id)
    died = api.patch(
        f"/api/v1/incidents/{hurt['id']}/people/{ravi_id}/",
        {"died_on": (day + timedelta(days=3)).isoformat()},
        format="json",
    )
    found = {d["duty"]: d for d in died.json()["duties"]}
    assert set(found) == {"disablement", "later_death"} and found["later_death"]["section"] == "69(2)"
    assert Notification.objects.filter(
        recipient=hr_officer, title__startswith="A death to notify forthwith"
    ).exists()


@pytest.mark.django_db
def test_dangerous_occurrences_diseases_and_who_is_told(api, employee, campus, settings):
    day = TODAY - timedelta(days=1)
    fire = _report(api, campus, kind="dangerous", day=day, industrial=True).json()
    (due,) = api.get(f"/api/v1/incidents/{fire['id']}/").json()["duties"]
    assert (due["duty"], due["section"], due["person"]) == ("dangerous", "74", None)
    assert due["due_on"] == (day + timedelta(days=2)).isoformat()
    on_a_farm = _report(api, campus, kind="dangerous", day=day).json()
    assert api.get(f"/api/v1/incidents/{on_a_farm['id']}/").json()["duties"] == []

    ill = _report(api, campus, kind="disease", day=day, industrial=True).json()
    (due,) = _person(api, ill["id"], who="staff", employee=employee.id).json()["duties"]
    assert due["section"] == "70" and due["due_on"] == day.isoformat()
    assert [t["recipient"] for t in due["to"]] == ["authority", "workers", "sanitary", "medical"]

    student = _report(api, campus, day=day).json()
    hurt = _person(api, student["id"], who="student", name="A. Student", off_work_from=day.isoformat())
    assert hurt.status_code == 200 and hurt.json()["duties"] == []

    settings.SAFETY_TELL_WORKERS = False
    (due,) = api.get(f"/api/v1/incidents/{fire['id']}/").json()["duties"]
    assert [t["recipient"] for t in due["to"]] == ["authority"]


@pytest.mark.django_db
def test_actions_are_done_by_their_owner_and_closing_waits_for_everything(
    api, employee, worker, campus, make_user
):
    day = TODAY - timedelta(days=2)
    incident = _report(api, campus, day=day).json()
    person = _person(api, incident["id"], who="staff", employee=employee.id, treatment="first_aid").json()
    assert person["duties"] == [] and person["state"] == "investigating"
    given = api.post(
        f"/api/v1/incidents/{incident['id']}/actions/",
        {"what": "Fit a guard to the mixer", "owner": employee.id, "due_on": TODAY.isoformat()},
        format="json",
    )
    assert given.status_code == 200, given.content
    action_id = given.json()["actions"][0]["id"]
    assert Notification.objects.filter(recipient=worker, link="/incidents").exists()
    owner = _signed_in(worker)
    assert [a["id"] for a in owner.get("/api/v1/incidents/actions/mine/").json()] == [action_id]
    assert "safety_action" in {i["kind"] for i in owner.get("/api/v1/approvals/waiting/").json()}

    stranger = _signed_in(make_user("someone.else", "employee"))
    done = {"done_on": TODAY.isoformat(), "note": "Guard fitted"}
    assert (
        stranger.post(f"/api/v1/incidents/actions/{action_id}/done/", done, format="json").status_code == 404
    )
    assert owner.post(f"/api/v1/incidents/actions/{action_id}/done/", done, format="json").status_code == 200
    again = owner.post(f"/api/v1/incidents/actions/{action_id}/done/", done, format="json")
    assert again.status_code == 409

    assert api.post(f"/api/v1/incidents/{incident['id']}/close/").json()["code"] == "outstanding"
    found = {"cause": "Feed spilt and not swept up", "investigated_on": TODAY.isoformat()}
    assert (
        api.post(f"/api/v1/incidents/{incident['id']}/investigation/", found, format="json").status_code
        == 200
    )
    closed = api.post(f"/api/v1/incidents/{incident['id']}/close/")
    assert closed.status_code == 200 and closed.json()["state"] == "closed"
    late = {"what": "Another", "owner": employee.id, "due_on": TODAY.isoformat()}
    assert api.post(f"/api/v1/incidents/{incident['id']}/actions/", late, format="json").status_code == 409

    person_id = closed.json()["people"][0]["id"]
    reopened = api.patch(
        f"/api/v1/incidents/{incident['id']}/people/{person_id}/",
        {"died_on": TODAY.isoformat()},
        format="json",
    )
    assert reopened.json()["state"] == "investigating"
    assert [d["duty"] for d in reopened.json()["duties"]] == ["death"]


@pytest.mark.django_db
def test_hr_has_reports_and_notices_in_to_do_and_a_morning_reminder(api, employee, campus, hr_officer):
    from incidents.tasks import chase

    day = TODAY - timedelta(days=6)
    reported = _report(_signed_in(hr_officer), campus, day=day).json()
    kinds = {i["kind"]: i for i in api.get("/api/v1/approvals/waiting/").json()}
    assert kinds["incident"]["link"] == f"/incidents/{reported['id']}"

    _person(api, reported["id"], who="staff", employee=employee.id, off_work_from=day.isoformat())
    items = [i for i in api.get("/api/v1/approvals/waiting/").json() if i["kind"] == "safety_notice"]
    assert len(items) == 1 and items[0]["overdue"]

    assert chase(TODAY)["reminders"] >= 1
    assert chase(TODAY)["reminders"] == 0  # once a day
    assert Notification.objects.filter(recipient=hr_officer, title__startswith="Late: notice").exists()


@pytest.mark.django_db
def test_what_a_report_and_a_record_may_say(api, employee, campus, unit, make_user):
    from org.models import Campus, OrgUnit
    from privacy.services import record_of_employee

    esq = Campus.objects.get(code="ESQ")
    elsewhere = OrgUnit.objects.create(code="ESQF", name="Farm", unit_type="farm", campus=esq)
    assert _report(api, campus, org_unit=elsewhere.id).json()["code"] == "other_campus"
    assert _report(api, campus, org_unit=unit.id).status_code == 201
    future = timezone.now() + timedelta(hours=2)
    assert _report(api, campus, occurred_at=future.isoformat()).json()["code"] == "future"
    no_record = _signed_in(make_user("visiting.officer", "auditor"))
    assert _report(no_record, campus, hurt=True).json()["code"] == "no_record"

    incident = _report(api, campus).json()
    assert _person(api, incident["id"], who="visitor").json()["code"] == "who"
    assert _person(api, incident["id"], who="staff", employee=employee.id).status_code == 200
    assert _person(api, incident["id"], who="staff", employee=employee.id).status_code == 409
    backwards = {
        "who": "contractor",
        "name": "B. Contractor",
        "off_work_from": TODAY.isoformat(),
        "back_at_work_on": (TODAY - timedelta(days=1)).isoformat(),
    }
    assert _person(api, incident["id"], **backwards).json()["code"] == "dates"

    copy = record_of_employee(employee)["staff_record"]["work_accidents"]
    assert [row["reference"] for row in copy] == [incident["reference"]]
