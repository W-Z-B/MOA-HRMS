"""Permission matrix: every role against the personnel endpoints (Planning Pack 2.2)."""

import pytest
from rest_framework.test import APIClient

# (role, may read employees, may write employees, may read payroll periods, may write leave types)
MATRIX = [
    ("administrator", True, True, True, True),
    ("hr_manager", True, True, True, True),
    ("hr_officer", True, True, False, False),
    ("finance", True, False, True, False),
    ("principal", True, False, True, False),
    ("supervisor", True, False, False, False),
    ("employee", False, False, False, False),
    ("ministry_liaison", False, False, False, False),
    ("auditor", True, False, True, False),
]


@pytest.mark.django_db
@pytest.mark.parametrize("role,read_emp,write_emp,read_payroll,write_leave_types", MATRIX)
def test_role_matrix(make_user, campus, seeded, role, read_emp, write_emp, read_payroll, write_leave_types):
    user = make_user(f"matrix.{role}", role, campus=campus)
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True  # the matrix tests roles, not the MFA gate (covered elsewhere)
    session.save()

    assert (client.get("/api/v1/employees/").status_code == 200) is read_emp
    payload = {
        "employee_no": f"M-{role}",
        "first_name": "Test",
        "last_name": "Person",
        "date_of_birth": "1990-01-01",
        "campus": campus.id,
    }
    assert (client.post("/api/v1/employees/", payload, format="json").status_code == 201) is write_emp
    assert (client.get("/api/v1/payroll/periods/").status_code == 200) is read_payroll
    status = client.post(
        "/api/v1/leave/types/", {"code": f"T{role[:3]}", "name": "t"}, format="json"
    ).status_code
    assert (status == 201) is write_leave_types


@pytest.mark.django_db
def test_hr_officer_cannot_reach_other_campus_records(make_user, seeded):
    from datetime import date

    from org.models import Campus
    from people.models import Employee

    mrp, esq = Campus.objects.get(code="MRP"), Campus.objects.get(code="ESQ")
    other = Employee.objects.create(
        employee_no="ESQ-1",
        first_name="Only",
        last_name="Essequibo",
        date_of_birth=date(1990, 1, 1),
        campus=esq,
    )
    officer = make_user("mrp.officer", "hr_officer", campus=mrp)
    client = APIClient()
    client.force_login(officer)
    assert client.get(f"/api/v1/employees/{other.id}/").status_code == 404
    assert client.post(f"/api/v1/employees/{other.id}/reveal/").status_code == 404
