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
    assert (row["approved"], row["filled"], row["vacant"]) == (2, 1, 1)
    assert api.get("/api/v1/reports/establishment-vs-actual/?output=pdf").status_code == 501


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
def test_data_quality_is_for_hr_only(make_user, campus, seeded):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_login(make_user("unit.head", "supervisor", campus=campus))
    assert client.get("/api/v1/reports/data-quality/").status_code == 403
    assert "data-quality" not in {r["key"] for r in client.get("/api/v1/reports/").json()}
