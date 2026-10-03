from datetime import date

import pytest


@pytest.mark.django_db
def test_establishment_vs_actual_counts_filled_and_vacant(api, employee, unit):
    from org.models import Position
    from people.models import Assignment

    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2026, 1, 1),
    )
    listing = api.get("/api/v1/reports/")
    assert listing.status_code == 200 and {r["key"] for r in listing.json()} >= {"establishment-vs-actual"}
    report = api.get("/api/v1/reports/establishment-vs-actual/")
    assert report.status_code == 200
    row = next(r for r in report.json()["rows"] if r["unit"] == "Livestock Unit")
    assert (row["approved"], row["filled"], row["vacant"], row["frozen"]) == (2, 1, 1, 0)
    assert api.get("/api/v1/reports/establishment-vs-actual/?output=pdf").status_code == 501


@pytest.mark.django_db
def test_each_post_counts_once_and_frozen_posts_apart(api, employee, unit, campus):
    """Item 2.30: a post with an ended and a current appointment counted twice; frozen posts were left out."""
    from org.models import Position
    from people.models import Assignment, Employee

    post = Position.objects.get(number="LIV-001")
    Assignment.objects.create(
        employee=employee,
        position=post,
        appointment_type="temporary",
        start_date=date(2020, 1, 6),
        end_date=date(2020, 12, 31),
        status="ended",
    )
    other = Employee.objects.create(
        employee_no="E0002",
        first_name="Kwame",
        last_name="Adams",
        date_of_birth=date(1982, 2, 18),
        campus=campus,
    )
    Assignment.objects.create(
        employee=other, position=post, appointment_type="permanent", start_date=date(2021, 1, 4)
    )
    Position.objects.create(
        number="LIV-009", title="Old post", grade=post.grade, org_unit=unit, status="frozen"
    )

    rows = api.get(f"/api/v1/reports/establishment-vs-actual/?campus={campus.id}").json()["rows"]

    assert rows == [
        {
            "campus": "Mon Repos Campus",
            "unit": "Livestock Unit",
            "approved": 2,
            "filled": 1,
            "vacant": 1,
            "frozen": 1,
        }
    ]


@pytest.mark.django_db
def test_headcount_counts_active_staff_by_their_appointment(api, employee, unit, campus):
    from org.models import Campus, Position
    from people.models import Assignment, Employee

    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="contract",
        start_date=date(2025, 11, 17),
    )
    seasonal = Employee.objects.create(
        employee_no="E0002",
        first_name="Kemal",
        last_name="Bacchus",
        date_of_birth=date(1999, 1, 19),
        campus=campus,
    )
    Assignment.objects.create(
        employee=seasonal,
        position=Position.objects.get(number="LIV-002"),
        appointment_type="seasonal",
        start_date=date(2026, 9, 28),
    )
    Employee.objects.create(
        employee_no="E0003",
        first_name="Former",
        last_name="Member",
        date_of_birth=date(1970, 1, 1),
        campus=campus,
        status="separated",
    )
    esq = Campus.objects.get(code="ESQ")

    every = {r["campus"]: r for r in api.get("/api/v1/reports/headcount-by-campus/").json()["rows"]}
    one = api.get(f"/api/v1/reports/headcount-by-campus/?campus={esq.id}").json()["rows"]

    assert every["Mon Repos Campus"] == {
        "campus": "Mon Repos Campus",
        "permanent": 0,
        "temporary": 0,
        "contract": 1,
        "other": 1,
        "active": 2,
        "total": 3,
    }
    assert [r["campus"] for r in one] == ["Essequibo Campus"] and one[0]["active"] == 0


@pytest.mark.django_db
def test_data_quality_lists_what_hr_should_check(api, employee, campus, seeded):
    from people.models import Employee

    twin = Employee.objects.create(
        employee_no="E0099",
        first_name="Asha",
        last_name="Persaud",
        date_of_birth=employee.date_of_birth,
        nis_no=employee.nis_no.lower(),  # the same number written differently
        campus=campus,
    )
    youngster = Employee.objects.create(
        employee_no="E0100",
        first_name="Too",
        last_name="Young",
        date_of_birth=date(2020, 1, 1),
        campus=campus,
    )
    report = api.get("/api/v1/reports/data-quality/", {"campus": campus.id})
    assert report.status_code == 200
    problems = {(r["employee_no"], r["field"]): r["problem"] for r in report.json()["rows"]}
    assert problems[("E0001", "NIS number")] == "The NIS number is the same as on E0099"
    assert problems[("E0099", "Person")].startswith("Same name and date of birth as E0001")
    assert problems[("E0099", "TIN")] == "No TIN on file"
    assert "gives an age of" in problems[(youngster.employee_no, "Date of birth")]
    assert problems[("E0001", "Emergency contact")] == "No emergency contact"
    assert problems[("E0001", "Contact")] == "No phone number or email address"
    assert employee.nis_no not in report.content.decode()  # identifiers are compared, never shown
    assert twin.pk


@pytest.mark.django_db
def test_a_report_that_names_people_stays_inside_the_campuses_of_whoever_runs_it(
    api, employee, campus, hr_manager
):
    """A Mon Repos officer never sees Essequibo staff in the data-quality report, asked for or not."""
    from rest_framework.test import APIClient

    from org.models import Campus
    from people.models import Employee

    essequibo = Campus.objects.get(code="ESQ")
    Employee.objects.create(
        employee_no="E0200",
        first_name="Ravi",
        last_name="Singh",
        date_of_birth=date(1985, 5, 5),
        campus=essequibo,
    )
    rows = api.get("/api/v1/reports/data-quality/").json()["rows"]
    assert rows and {r["campus"] for r in rows} == {campus.name}
    refused = api.get("/api/v1/reports/data-quality/", {"campus": essequibo.id})
    assert refused.status_code == 403 and refused.json()["code"] == "forbidden"
    assert "E0200" not in refused.content.decode()

    manager = APIClient()
    manager.force_login(hr_manager)
    session = manager.session
    session["mfa_verified"] = True
    session.save()
    everyone = manager.get("/api/v1/reports/data-quality/").json()["rows"]
    assert {"E0001", "E0200"} <= {r["employee_no"] for r in everyone}
    only_essequibo = manager.get("/api/v1/reports/data-quality/", {"campus": essequibo.id}).json()["rows"]
    assert {r["employee_no"] for r in only_essequibo} == {"E0200"}


@pytest.mark.django_db
def test_data_quality_is_for_hr_only(make_user, campus, seeded):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_login(make_user("unit.head", "supervisor", campus=campus))
    assert client.get("/api/v1/reports/data-quality/").status_code == 403
    assert "data-quality" not in {r["key"] for r in client.get("/api/v1/reports/").json()}
