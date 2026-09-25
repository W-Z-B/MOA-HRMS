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
