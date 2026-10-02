import pytest


@pytest.mark.django_db
def test_positions_report_vacancy(api, unit):
    response = api.get("/api/v1/org/positions/", {"org_unit": unit.id})
    assert response.status_code == 200
    rows = response.json()["results"]
    assert {r["number"] for r in rows} == {"LIV-001", "LIV-002"}
    assert all(r["is_vacant"] for r in rows)


@pytest.mark.django_db
def test_hr_officer_cannot_create_campus(api):
    response = api.post("/api/v1/org/campuses/", {"code": "NEW", "name": "New Campus"})
    assert response.status_code == 403


@pytest.mark.django_db
def test_hr_manager_creates_campus_with_audit_row(hr_manager, seeded):
    from rest_framework.test import APIClient

    from audit.models import AuditLog

    client = APIClient()
    client.force_login(hr_manager)
    session = client.session
    session["mfa_verified"] = True  # hr_manager is an MFA role; simulate a verified session
    session.save()
    response = client.post("/api/v1/org/campuses/", {"code": "BER", "name": "Berbice (planned)"})
    assert response.status_code == 201, response.content
    entry = AuditLog.objects.get(entity="org.campus", entity_id=response.json()["id"])
    assert entry.action == "create" and entry.actor == hr_manager and entry.after["code"] == "BER"


@pytest.mark.django_db
def test_mfa_role_is_blocked_until_verified(hr_manager, seeded):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_login(hr_manager)
    response = client.get("/api/v1/org/campuses/")
    assert response.status_code == 403
    assert "Multi-factor" in response.json()["detail"]


def _manager(user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.mark.django_db
def test_grade_amounts_are_for_the_roles_that_see_pay(api, unit, make_user, campus):
    from rest_framework.test import APIClient

    assert api.get("/api/v1/org/grades/").json()["results"][0]["amount"] == "250000.00"  # an HR officer
    supervisor = APIClient()
    supervisor.force_login(make_user("unit.head", "supervisor", campus=campus))
    grades = supervisor.get("/api/v1/org/grades/").json()["results"]
    assert grades[0]["amount"] is None and grades[0]["code"] == "GS5"


@pytest.mark.django_db
def test_posts_and_units_say_who_and_where_in_words(api, unit, employee, make_user, campus):
    from datetime import date

    from rest_framework.test import APIClient

    from org.models import Position
    from people.models import Assignment

    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2026, 1, 1),
    )
    unit.head = employee
    unit.save()
    posts = {
        p["number"]: p for p in api.get("/api/v1/org/positions/", {"org_unit": unit.id}).json()["results"]
    }
    assert posts["LIV-001"]["holder"] == "Asha Persaud" and posts["LIV-002"]["holder"] is None
    assert (
        posts["LIV-001"]["grade_name"] == "GS GS5, step 1" and posts["LIV-001"]["campus_name"] == campus.name
    )
    assert api.get(f"/api/v1/org/units/{unit.id}/").json()["head_name"] == "Asha Persaud"

    plain = APIClient()
    plain.force_login(make_user("someone", "employee", campus=campus))
    assert plain.get("/api/v1/org/positions/").json()["results"][0]["holder"] is None


@pytest.mark.django_db
def test_holders_are_named_only_on_the_campuses_the_reader_works_with(api, unit, employee, make_user):
    from datetime import date

    from rest_framework.test import APIClient

    from org.models import Campus, Position
    from people.models import Assignment

    Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2026, 1, 1),
    )
    unit.head = employee
    unit.save()
    elsewhere = APIClient()
    elsewhere.force_login(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    post = elsewhere.get("/api/v1/org/positions/", {"org_unit": unit.id}).json()["results"][0]
    assert post["number"] == "LIV-001" and post["is_vacant"] is False and post["holder"] is None
    assert elsewhere.get(f"/api/v1/org/units/{unit.id}/").json()["head_name"] is None
    assert api.get(f"/api/v1/org/units/{unit.id}/").json()["head_name"] == "Asha Persaud"


@pytest.mark.django_db
def test_removing_something_still_in_use_is_refused_in_words(hr_manager, unit):
    client = _manager(hr_manager)
    refused = client.delete(f"/api/v1/org/units/{unit.id}/")
    assert refused.status_code == 409
    assert refused.json() == {
        "code": "in_use",
        "detail": "It cannot be removed while 2 positions still refer to it.",
    }


@pytest.mark.django_db
def test_the_refusal_counts_each_kind_of_record_in_words(unit, employee):
    from datetime import date

    from core.exceptions import still_held
    from org.models import Position
    from people.models import Assignment

    posts = list(Position.objects.filter(org_unit=unit))
    held = Assignment.objects.create(
        employee=employee, position=posts[0], appointment_type="permanent", start_date=date(2026, 1, 1)
    )
    assert still_held({held}) == "It cannot be removed while 1 assignment still refers to it."
    assert still_held({*posts, held}) == (
        "It cannot be removed while 1 assignment and 2 positions still refer to it."
    )
    assert still_held(set()) == "It cannot be removed while other records still refer to it."


@pytest.mark.django_db
def test_a_unit_stays_on_its_campus_and_never_under_itself(hr_manager, unit, campus):
    from org.models import Campus, OrgUnit

    client = _manager(hr_manager)
    child = OrgUnit.objects.create(code="LIV-P", name="Pigs", unit_type="section", campus=campus, parent=unit)
    looped = client.patch(f"/api/v1/org/units/{unit.id}/", {"parent": child.id}, format="json")
    assert looped.status_code == 400 and looped.json()["parent"] == ["A unit cannot sit under itself."]
    elsewhere = Campus.objects.get(code="ESQ")
    moved = client.patch(f"/api/v1/org/units/{child.id}/", {"campus": elsewhere.id}, format="json")
    assert moved.status_code == 400 and "same campus" in moved.json()["parent"][0]

    from datetime import date

    from people.models import Employee

    far = Employee.objects.create(
        employee_no="E0900",
        first_name="Far",
        last_name="Away",
        date_of_birth=date(1980, 1, 1),
        campus=elsewhere,
    )
    headed = client.patch(f"/api/v1/org/units/{unit.id}/", {"head": far.id}, format="json")
    assert headed.status_code == 400 and headed.json()["head"] == ["The head of a unit works on its campus."]
