"""Item 2.30: each person's Home, and who they are, counted inside the campuses they work with."""

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


def _person(no, first, last, campus, post=None, *, appointment="permanent", start=None, **held):
    from people.models import Assignment, Employee

    employee = Employee.objects.create(
        employee_no=no, first_name=first, last_name=last, date_of_birth=date(1990, 1, 1), campus=campus
    )
    if post is not None:
        Assignment.objects.create(
            employee=employee,
            position=post,
            appointment_type=appointment,
            start_date=start or date(2020, 1, 6),
            **held,
        )
    return employee


@pytest.fixture
def school(campus, unit):
    """Two campuses. Mon Repos: the Livestock Unit (LIV-001 held by its head, LIV-002 held on a contract
    ending in 30 days and a probation ending in 20), with the Dairy Section under it (one post, vacant)
    and a frozen post nobody holds. Essequibo: one unit, its one post held by someone with no account."""
    from org.models import Campus, OrgUnit, Position

    esq = Campus.objects.get(code="ESQ")
    grade = Position.objects.get(number="LIV-001").grade
    dairy = OrgUnit.objects.create(
        code="DAI", name="Dairy Section", unit_type="section", campus=campus, parent=unit
    )
    Position.objects.create(number="DAI-001", title="Dairy Hand", grade=grade, org_unit=dairy)
    Position.objects.create(number="LIV-009", title="Old post", grade=grade, org_unit=unit, status="frozen")
    farm = OrgUnit.objects.create(code="ESQ-F", name="Essequibo Farm", unit_type="farm", campus=esq)
    Position.objects.create(number="ESQ-F-001", title="Field Instructor", grade=grade, org_unit=farm)

    head = _person("E0101", "Kwame", "Adams", campus, Position.objects.get(number="LIV-001"))
    hand = _person(
        "E0102",
        "Roxanne",
        "Williams",
        campus,
        Position.objects.get(number="LIV-002"),
        appointment="contract",
        start=TODAY() - timedelta(days=200),
        end_date=TODAY() + timedelta(days=30),
        probation_end=TODAY() + timedelta(days=20),
    )
    far = _person(
        "E0103", "Troy", "Benjamin", esq, Position.objects.get(number="ESQ-F-001"), start=date(2026, 9, 28)
    )
    unit.head = head
    unit.save()
    return {"head": head, "hand": hand, "far": far, "esq": esq, "unit": unit, "dairy": dairy}


def _account(make_user, username, employee, *roles, campus=None):
    user = make_user(username, *roles, campus=campus)
    employee.user = user
    employee.save()
    return user


@pytest.mark.django_db
def test_hr_on_one_campus_counts_only_that_campus(api, school):
    body = api.get("/api/v1/home/").json()

    assert body["persona"] == "hr" and body["ending_days"] == 90
    staff = body["staff"]
    assert [c["code"] for c in staff["campuses"]] == ["MRP"]
    assert staff["active"] == 2  # Kwame and Roxanne; Troy is on Essequibo, outside this officer's campus
    # LIV-001, LIV-002 and DAI-001 are posts; LIV-009 is frozen and nobody holds it.
    assert (staff["posts"], staff["filled"], staff["vacant"], staff["frozen"]) == (4, 2, 1, 1)
    assert [(e["name"], e["what"]) for e in body["ending"]] == [
        ("Roxanne Williams", "probation"),
        ("Roxanne Williams", "contract"),
    ]
    # Nobody on Mon Repos has an account yet; Troy, on Essequibo, is not this officer's to invite.
    assert body["no_account"]["count"] == 2
    assert {p["name"] for p in body["no_account"]["latest"]} == {"Kwame Adams", "Roxanne Williams"}
    assert body["units"] is None and body["team"] is None


@pytest.mark.django_db
def test_leave_waiting_counts_every_request_and_those_mine_to_decide(api, school, hr_officer):
    from leave.models import LeaveRequest, LeaveType

    annual = LeaveType.objects.get(code="ANN")
    kwargs = {"leave_type": annual, "from_date": date(2026, 11, 2), "to_date": date(2026, 11, 3), "days": 2}
    LeaveRequest.objects.create(employee=school["hand"], state="supervisor_approved", **kwargs)
    LeaveRequest.objects.create(employee=school["head"], state="submitted", **kwargs)
    LeaveRequest.objects.create(employee=school["far"], state="submitted", **kwargs)  # Essequibo
    LeaveRequest.objects.create(employee=school["head"], state="draft", **kwargs)  # not yet asked for

    leave = api.get("/api/v1/home/").json()["leave"]

    # Two wait on Mon Repos; only the one past the manager is this officer's to decide, at HR's step.
    assert leave == {"waiting": 2, "mine": 1}


@pytest.mark.django_db
def test_the_campus_switch_narrows_the_figures_and_a_bad_campus_is_refused(make_user, school, campus):
    principal = make_user("the.principal", "principal")
    client = _signed_in(principal)

    both = client.get("/api/v1/home/").json()["staff"]
    one = client.get(f"/api/v1/home/?campus={school['esq'].id}").json()["staff"]

    assert [c["code"] for c in both["campuses"]] == ["ESQ", "MRP"] and both["active"] == 3
    assert [c["code"] for c in one["campuses"]] == ["ESQ"] and (one["active"], one["posts"]) == (1, 1)
    assert client.get("/api/v1/home/?campus=MRP").status_code == 400


@pytest.mark.django_db
def test_the_principal_sees_each_unit_by_its_own_posts(make_user, school):
    body = _signed_in(make_user("the.principal", "principal")).get("/api/v1/home/").json()

    assert body["persona"] == "principal" and body["no_account"] is None
    units = {u["name"]: (u["posts"], u["filled"], u["vacant"], u["frozen"]) for u in body["units"]}
    # The Livestock Unit counts its own three posts, not the Dairy Section's under it.
    assert units == {
        "Livestock Unit": (3, 2, 0, 1),
        "Dairy Section": (1, 0, 1, 0),
        "Essequibo Farm": (1, 1, 0, 0),
    }


@pytest.mark.django_db
def test_a_head_of_unit_sees_their_team_and_what_ends_in_it(make_user, school, campus):
    user = _account(make_user, "kwame.adams", school["head"], "employee", "supervisor", campus=campus)

    body = _signed_in(user).get("/api/v1/home/").json()

    assert body["persona"] == "manager" and body["staff"] is None and body["units"] is None
    assert [(m["name"], m["is_me"]) for m in body["team"]] == [
        ("Kwame Adams", True),
        ("Roxanne Williams", False),
    ]
    roxanne = body["team"][1]
    assert roxanne["appointment"] == "Contract" and roxanne["probation_end"] is not None
    assert {e["name"] for e in body["ending"]} == {"Roxanne Williams"}


@pytest.mark.django_db
def test_an_employee_and_an_office_role_see_only_what_their_roles_allow(make_user, school, campus):
    employee = _account(make_user, "roxanne.williams", school["hand"], "employee", campus=campus)
    mine = _signed_in(employee).get("/api/v1/home/").json()
    auditor = _signed_in(make_user("audit.reviewer", "auditor")).get("/api/v1/home/").json()
    officer = _signed_in(make_user("privacy.officer", "data_protection_officer")).get("/api/v1/home/").json()

    assert mine["persona"] == "employee"
    assert all(mine[key] is None for key in ("staff", "units", "ending", "no_account", "team"))
    assert mine["leave"] == {"mine": 0, "waiting": None}
    # The auditor reads the staff list, so sees its figures, but invites nobody.
    assert (
        auditor["persona"] == "office" and auditor["staff"]["active"] == 3 and auditor["no_account"] is None
    )
    assert officer["persona"] == "office" and officer["staff"] is None


@pytest.mark.django_db
def test_home_needs_a_signed_in_person(school):
    assert APIClient().get("/api/v1/home/").status_code == 403


@pytest.mark.django_db
def test_me_says_who_the_person_is_and_which_campuses_they_work_with(make_user, school, campus):
    head = _account(make_user, "kwame.adams", school["head"], "employee", "supervisor", campus=campus)

    me = _signed_in(head).get("/api/v1/auth/me/").json()

    assert (me["position"], me["unit"], me["heads"]) == (
        "Livestock Instructor",
        "Livestock Unit",
        ["Livestock Unit"],
    )
    assert me["campus"] == "Mon Repos Campus"
    assert [c["code"] for c in me["campuses"]] == ["MRP"]


@pytest.mark.django_db
def test_a_superuser_is_offered_every_role_the_server_already_allows(make_user, seeded):
    from iam.models import Role

    me = _signed_in(make_user("the.admin", superuser=True)).get("/api/v1/auth/me/").json()

    assert set(me["roles"]) == {code for code, _ in Role.CODES}
    assert (me["position"], me["heads"], me["campus"]) == (None, [], None)
    assert [c["code"] for c in me["campuses"]] == ["ESQ", "MRP"]
