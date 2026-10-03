"""Item 2.30: the staff list says each person's unit, appointment and start; one file adds its key facts."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

TODAY = timezone.localdate


def _post(number):
    from org.models import Position

    return Position.objects.get(number=number)


def _hold(employee, number, appointment="permanent", **more):
    from people.models import Assignment

    return Assignment.objects.create(
        employee=employee,
        position=_post(number),
        appointment_type=appointment,
        start_date=date(2019, 9, 2),
        **more,
    )


@pytest.fixture
def staffed(employee, unit, make_user, campus):
    """Asha holds LIV-002 on a fixed-term contract ending in 40 days, still on probation; Kwame heads the unit
    from LIV-001 and can sign in, so he decides her leave."""
    from people.models import Contract, Employee

    held = _hold(
        employee,
        "LIV-002",
        "contract",
        end_date=TODAY() + timedelta(days=40),
        probation_end=TODAY() + timedelta(days=10),
    )
    Contract.objects.create(assignment=held, contract_type="fixed_term", hours_per_week=Decimal("40"))
    kwame = Employee.objects.create(
        employee_no="E0004",
        first_name="Kwame",
        last_name="Adams",
        date_of_birth=date(1982, 2, 18),
        campus=campus,
    )
    _hold(kwame, "LIV-001")
    kwame.user = make_user("kwame.adams", "employee", "supervisor", campus=campus)
    kwame.save()
    unit.head = kwame
    unit.save()
    return employee


@pytest.mark.django_db
def test_the_list_says_each_person_s_unit_appointment_and_start(api, staffed):
    rows = {r["employee_no"]: r for r in api.get("/api/v1/employees/").json()["results"]}

    asha = rows["E0001"]
    assert (asha["position_title"], asha["unit_name"], asha["appointment_type"], asha["started"]) == (
        "Farm Hand",
        "Livestock Unit",
        "Contract",
        "2019-09-02",
    )
    # The list stays light: the file's facts are not in it.
    assert "manager_name" not in asha


@pytest.mark.django_db
def test_the_list_costs_the_same_number_of_queries_however_many_staff(
    api, staffed, campus, unit, django_assert_max_num_queries
):
    from org.models import Position
    from people.models import Employee

    for n in range(12):
        person = Employee.objects.create(
            employee_no=f"E01{n:02}",
            first_name="Staff",
            last_name=f"Member {n}",
            date_of_birth=date(1990, 1, 1),
            campus=campus,
        )
        post = Position.objects.create(
            number=f"LIV-1{n:02}", title="Farm Hand", grade=_post("LIV-001").grade, org_unit=unit
        )
        _hold(person, post.number)
    with django_assert_max_num_queries(12):
        page = api.get("/api/v1/employees/").json()
    assert page["count"] == 14 and all(r["unit_name"] for r in page["results"])


@pytest.mark.django_db
def test_one_file_gives_the_facts_above_its_tabs(api, staffed):
    body = api.get(f"/api/v1/employees/{staffed.id}/").json()

    assert body["manager_name"] == "Kwame Adams"
    assert body["contract_type"] == "Fixed term"
    assert body["ends"] == (TODAY() + timedelta(days=40)).isoformat()
    assert body["probation_end"] == (TODAY() + timedelta(days=10)).isoformat()


@pytest.mark.django_db
def test_a_file_with_no_post_and_a_confirmed_one_say_so(api, employee, unit):
    empty = api.get(f"/api/v1/employees/{employee.id}/").json()
    assert [empty[k] for k in ("position_title", "unit_name", "appointment_type", "started")] == [None] * 4
    assert [empty[k] for k in ("manager_name", "contract_type", "ends", "probation_end")] == [None] * 4

    _hold(employee, "LIV-001", probation_end=date(2020, 3, 1), confirmed_on=date(2020, 3, 1))
    confirmed = api.get(f"/api/v1/employees/{employee.id}/").json()
    assert confirmed["probation_end"] is None and confirmed["appointment_type"] == "Permanent"


@pytest.mark.django_db
def test_to_do_opens_the_part_of_the_file_where_the_item_is_decided(staffed, hr_officer, make_user):
    from rest_framework.test import APIClient

    from people.models import BankAccount

    BankAccount.objects.create(
        employee=staffed,
        bank_name="Republic Bank (Guyana)",
        account_name="Asha Persaud",
        account_number="1234567890",
        account_number_last4="7890",
        created_by=hr_officer,
        updated_by=hr_officer,
    )
    finance = APIClient()
    finance.force_login(make_user("finance.officer", "finance"))
    session = finance.session
    session["mfa_verified"] = True
    session.save()

    items = {i["kind"]: i for i in finance.get("/api/v1/approvals/waiting/").json()}

    # New bank details are decided on the Bank tab of the file.
    assert items["bank"]["link"] == f"/people/{staffed.id}/bank"


@pytest.mark.django_db
def test_balances_of_someone_else_are_refused_to_a_role_that_may_not_read_them(staffed, make_user, campus):
    """Found while building item 2.30: the caller's own balances came back, under the other person's name."""
    from rest_framework.test import APIClient

    from people.models import Employee

    auditor = make_user("audit.reviewer", "employee", "auditor", campus=campus)
    own = Employee.objects.create(
        employee_no="E0099",
        first_name="Audit",
        last_name="Reviewer",
        date_of_birth=date(1980, 1, 1),
        campus=campus,
    )
    own.user = auditor
    own.save()
    client = APIClient()
    client.force_login(auditor)

    other = client.get(f"/api/v1/leave/ledger/balances/?employee={staffed.id}")
    mine = client.get(f"/api/v1/leave/ledger/balances/?employee={own.id}")
    plain = client.get("/api/v1/leave/ledger/balances/")

    assert other.status_code == 403
    assert mine.status_code == 200 and mine.json()["employee"] == own.id
    assert plain.status_code == 200 and plain.json()["employee"] == own.id
