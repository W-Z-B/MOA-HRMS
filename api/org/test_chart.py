"""Item 1.10: the organisation chart."""

from datetime import date

import pytest
from rest_framework.test import APIClient


def _hold(employee, number, acting=False):
    from org.models import Position
    from people.models import Assignment

    return Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number=number),
        appointment_type="permanent",
        start_date=date(2026, 1, 1),
        is_acting=acting,
    )


@pytest.fixture
def farm(unit, campus, employee):
    """The Livestock Unit under a farm department headed by Asha; one post held, one acted in."""
    from org.models import OrgUnit, Position
    from people.models import Employee

    farm = OrgUnit.objects.create(
        code="FRM", name="Farm Department", unit_type="department", campus=campus, head=employee
    )
    unit.parent = farm
    unit.save()
    grade = Position.objects.get(number="LIV-001").grade
    Position.objects.create(
        number="FRM-001", title="Farm Manager", grade=grade, org_unit=farm, status="frozen"
    )
    Position.objects.create(
        number="FRM-009", title="Old post", grade=grade, org_unit=farm, status="abolished"
    )
    _hold(employee, "LIV-001")
    deputy = Employee.objects.create(
        employee_no="E0002",
        first_name="Ravi",
        last_name="Singh",
        date_of_birth=date(1985, 5, 5),
        campus=campus,
    )
    _hold(deputy, "LIV-002", acting=True)
    return farm


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_the_chart_nests_units_and_counts_their_posts(api, farm, campus):
    response = api.get("/api/v1/org/chart/", {"campus": campus.id})
    assert response.status_code == 200
    (mrp,) = response.json()["campuses"]
    assert mrp["code"] == "MRP" and mrp["names"] is True
    (top,) = mrp["units"]
    assert top["code"] == "FRM" and top["head"] == "Asha Persaud"
    assert [p["number"] for p in top["posts"]] == ["FRM-001"]  # the abolished post is left out
    assert top["posts"][0]["status_name"] == "Frozen" and top["posts"][0]["vacant"] is False
    (livestock,) = top["units"]
    held, acted = livestock["posts"]
    assert (held["number"], held["holder"], held["filled"]) == ("LIV-001", "Asha Persaud", True)
    assert (acted["vacant"], acted["acting"], acted["has_acting"]) == (True, "Ravi Singh", True)
    assert held["grade_name"] == "GS GS5, step 1" and "amount" not in held
    assert livestock["totals"] == {"posts": 2, "filled": 1, "vacant": 1, "frozen": 0}
    assert top["totals"] == {"posts": 3, "filled": 1, "vacant": 1, "frozen": 1}
    assert mrp["totals"] == top["totals"]


@pytest.mark.django_db
def test_names_on_the_chart_follow_the_staff_directory(farm, make_user, campus):
    from org.models import Campus

    plain = _client(make_user("someone", "employee", campus=campus))
    elsewhere = _client(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    for reader in (plain, elsewhere):
        (mrp,) = reader.get("/api/v1/org/chart/", {"campus": campus.id}).json()["campuses"]
        (top,) = mrp["units"]
        held, acted = top["units"][0]["posts"]
        assert mrp["names"] is False and top["head"] is None
        assert held["holder"] is None and held["filled"] is True
        assert acted["acting"] is None and acted["has_acting"] is True


@pytest.mark.django_db
def test_the_chart_reads_in_a_fixed_number_of_queries(api, farm, django_assert_max_num_queries):
    from org.models import Position

    grade = Position.objects.get(number="LIV-001").grade
    Position.objects.bulk_create(
        Position(number=f"FRM-{n:03}", title="Field Hand", grade=grade, org_unit=farm)
        for n in range(100, 140)
    )
    with django_assert_max_num_queries(10):
        campuses = {c["code"]: c for c in api.get("/api/v1/org/chart/").json()["campuses"]}
    assert campuses["MRP"]["totals"]["vacant"] == 41
    assert campuses["ESQ"]["names"] is False and campuses["ESQ"]["units"] == []  # not the officer's campus


@pytest.mark.django_db
def test_the_chart_refuses_a_campus_that_is_not_an_id(api):
    response = api.get("/api/v1/org/chart/", {"campus": "MRP"})
    assert response.status_code == 400 and response.json()["code"] == "bad_request"
