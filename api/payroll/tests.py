"""H-M01: the pay calculation engine, the pay-run workflow and the endpoints."""

from datetime import date, time
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from payroll import services
from payroll.models import PayRun, Payslip, StatutoryRate

PERIOD = "2026-11"


@pytest.fixture
def rates_2026(db):
    """The verified 2026 figures (GRA notice 26 Feb 2026; nis.org.gy), so the worked examples check out."""
    rows = [
        (StatutoryRate.Kind.NIS_EMPLOYEE_PCT, "5.6"),
        (StatutoryRate.Kind.NIS_EMPLOYER_PCT, "8.4"),
        (StatutoryRate.Kind.NIS_CEILING_MONTHLY, "280000"),
        (StatutoryRate.Kind.PAYE_ALLOWANCE_MONTHLY, "140000"),
        (StatutoryRate.Kind.PAYE_RATE_PCT, "25"),
        (StatutoryRate.Kind.PAYE_BAND2_THRESHOLD_MONTHLY, "280000"),
        (StatutoryRate.Kind.PAYE_RATE_BAND2_PCT, "35"),
    ]
    for kind, value in rows:
        StatutoryRate.objects.create(kind=kind, value=Decimal(value), effective_from=date(2026, 1, 1))


@pytest.fixture
def placed(employee, unit, make_user, campus):
    """An employee with an assignment and a contract, paid on a grade of 150,000 a month."""
    from org.models import Grade, Position, SalaryScale
    from people.models import Assignment, Contract

    scale = SalaryScale.objects.create(code="DEMO", name="Demonstration scale")
    grade = Grade.objects.create(
        scale=scale, code="D1", step=1, amount=Decimal("150000"), effective_from=date(2026, 1, 1)
    )
    position = Position.objects.create(
        number="DEMO-001", title="Demonstration post", grade=grade, org_unit=unit
    )
    assignment = Assignment.objects.create(
        employee=employee, position=position, appointment_type="permanent", start_date=date(2019, 9, 2)
    )
    Contract.objects.create(assignment=assignment, contract_type="open_ended", hours_per_week=Decimal("40"))
    employee.user = make_user("payee", "employee", campus=campus)
    employee.save()
    return employee


@pytest.fixture
def preparer(make_user, seeded):
    return make_user("finance.preparer", "finance")


@pytest.fixture
def approver(make_user, seeded):
    return make_user("finance.approver", "finance")


def _mfa_client(user) -> APIClient:
    """Finance, HR Manager and Administrator need MFA verified for any action (iam.permissions)."""
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


# -- the calculation engine, reproducing the GRA's own worked examples (ADR 0004, item 4.07) --


@pytest.mark.django_db
def test_nis_employee_is_capped_at_the_ceiling(rates_2026):
    assert services.nis_employee(Decimal("150000"), date(2026, 11, 30)) == Decimal("8400.00")
    assert services.nis_employee(Decimal("420000"), date(2026, 11, 30)) == Decimal("15680.00")


@pytest.mark.django_db
def test_paye_on_150000_a_month_is_400(rates_2026):
    gross = Decimal("150000")
    nis = services.nis_employee(gross, date(2026, 11, 30))
    assert services.paye(gross, nis, date(2026, 11, 30))["tax"] == Decimal("400.00")


@pytest.mark.django_db
def test_paye_on_420000_a_month_is_66080(rates_2026):
    gross = Decimal("420000")
    nis = services.nis_employee(gross, date(2026, 11, 30))
    assert services.paye(gross, nis, date(2026, 11, 30))["tax"] == Decimal("66080.00")


@pytest.mark.django_db
def test_paye_raises_when_a_rate_is_missing(db):
    with pytest.raises(services.RatesMissing):
        services.paye(Decimal("150000"), Decimal("0"), date(2026, 11, 30))


@pytest.mark.django_db
def test_compute_payslip_for_a_salaried_employee(rates_2026, placed):
    figures = services.compute_payslip(placed, PERIOD)
    assert figures["gross"] == Decimal("150000.00")
    assert figures["paye"] == Decimal("400.00")
    assert figures["nis_employee"] == Decimal("8400.00")
    assert figures["net"] == figures["gross"] - figures["nis_employee"] - figures["paye"]
    assert figures["unpaid_days"] == 0


@pytest.mark.django_db
def test_an_absent_day_is_deducted_from_a_salaried_employees_gross(rates_2026, placed):
    from attendance.models import AttendanceRecord

    # November 2026 has 21 working days (holidays.by_rule and the seeded calendar); one is unpaid absence.
    AttendanceRecord.objects.create(
        employee=placed, date=date(2026, 11, 4), status=AttendanceRecord.Status.ABSENT
    )
    figures = services.compute_payslip(placed, PERIOD)
    from leave.services import working_days

    daily = Decimal("150000") / Decimal(working_days(date(2026, 11, 1), date(2026, 11, 30)))
    assert figures["unpaid_days"] == 1
    assert figures["gross"] == (Decimal("150000") - daily.quantize(Decimal("0.01"))).quantize(Decimal("0.01"))


@pytest.mark.django_db
def test_unpaid_leave_is_also_deducted_but_paid_leave_is_not(rates_2026, placed):
    from attendance.models import AttendanceRecord
    from leave.models import LeaveRequest, LeaveType

    unpaid_type = LeaveType.objects.get(code="NOP")  # seeded: leave without pay
    paid_type = LeaveType.objects.get(code="ANN")  # seeded: annual leave, paid
    unpaid_request = LeaveRequest.objects.create(
        employee=placed,
        leave_type=unpaid_type,
        from_date=date(2026, 11, 4),
        to_date=date(2026, 11, 4),
        days=1,
        state=LeaveRequest.State.APPROVED,
    )
    paid_request = LeaveRequest.objects.create(
        employee=placed,
        leave_type=paid_type,
        from_date=date(2026, 11, 5),
        to_date=date(2026, 11, 5),
        days=1,
        state=LeaveRequest.State.APPROVED,
    )
    AttendanceRecord.objects.create(
        employee=placed,
        date=date(2026, 11, 4),
        status=AttendanceRecord.Status.ON_LEAVE,
        leave_request=unpaid_request,
    )
    AttendanceRecord.objects.create(
        employee=placed,
        date=date(2026, 11, 5),
        status=AttendanceRecord.Status.ON_LEAVE,
        leave_request=paid_request,
    )
    figures = services.compute_payslip(placed, PERIOD)
    assert figures["unpaid_days"] == 1


@pytest.mark.django_db
def test_an_hourly_contract_is_paid_for_the_hours_attendance_recorded(rates_2026, employee, unit, campus):
    from attendance.models import AttendanceRecord
    from org.models import Grade, Position, SalaryScale
    from people.models import Assignment, Contract

    scale = SalaryScale.objects.create(code="HRLY", name="Hourly scale")
    grade = Grade.objects.create(
        scale=scale, code="H1", step=1, amount=Decimal("1"), effective_from=date(2026, 1, 1)
    )
    position = Position.objects.create(number="HRLY-001", title="Hourly post", grade=grade, org_unit=unit)
    assignment = Assignment.objects.create(
        employee=employee, position=position, appointment_type="temporary", start_date=date(2026, 1, 1)
    )
    Contract.objects.create(assignment=assignment, contract_type="fixed_term", hourly_rate=Decimal("750.00"))
    AttendanceRecord.objects.create(
        employee=employee,
        date=date(2026, 11, 4),
        time_in=time(8, 0),
        time_out=time(16, 0),
        hours=Decimal("8"),
    )
    AttendanceRecord.objects.create(
        employee=employee,
        date=date(2026, 11, 5),
        time_in=time(8, 0),
        time_out=time(12, 0),
        hours=Decimal("4"),
    )
    figures = services.compute_payslip(employee, PERIOD)
    assert figures["gross"] == Decimal("9000.00")  # 12 hours at 750
    assert figures["breakdown"]["pay_basis"] == "hourly"


@pytest.mark.django_db
def test_compute_payslip_is_none_without_a_contract(rates_2026, employee):
    assert services.compute_payslip(employee, PERIOD) is None


# -- the pay-run workflow: calculate, approve (never by the preparer), disburse --


@pytest.mark.django_db
def test_calculate_creates_a_payslip_and_totals_it(rates_2026, placed, preparer):
    client = _mfa_client(preparer)
    run = PayRun.objects.create(period=PERIOD)
    request = client.post(
        f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "calculate"}, format="json"
    )
    assert request.status_code == 200, request.content
    run.refresh_from_db()
    assert run.state == "calculated"
    assert run.total_net > 0
    assert Payslip.objects.filter(pay_run=run, employee=placed).exists()


@pytest.mark.django_db
def test_the_preparer_cannot_approve_their_own_calculation(rates_2026, placed, preparer):
    client = _mfa_client(preparer)
    run = PayRun.objects.create(period=PERIOD)
    client.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "calculate"}, format="json")
    same = client.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "approve"}, format="json")
    assert same.status_code == 409
    assert same.json()["code"] == "same_preparer"


@pytest.mark.django_db
def test_a_different_finance_user_approves_then_disburses(rates_2026, placed, preparer, approver):
    prep = _mfa_client(preparer)
    app = _mfa_client(approver)

    run = PayRun.objects.create(period=PERIOD)
    prep.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "calculate"}, format="json")
    approved = app.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "approve"}, format="json")
    assert approved.status_code == 200, approved.content
    assert approved.json()["state"] == "approved"

    disbursed = app.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "disburse"}, format="json")
    assert disbursed.status_code == 200, disbursed.content
    assert disbursed.json()["state"] == "disbursed"
    payslip = Payslip.objects.get(pay_run=run, employee=placed)
    assert payslip.document is not None

    mine = APIClient()
    mine.force_login(placed.user)
    own = mine.get("/api/v1/payroll/payslips/")
    assert own.status_code == 200
    assert own.json()["count"] == 1
    download = mine.get(f"/api/v1/payroll/payslips/{payslip.id}/download/")
    assert download.status_code == 200
    assert download["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_an_employee_cannot_see_a_payslip_before_disbursement(rates_2026, placed, preparer):
    client = _mfa_client(preparer)
    run = PayRun.objects.create(period=PERIOD)
    client.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "calculate"}, format="json")

    mine = APIClient()
    mine.force_login(placed.user)
    response = mine.get("/api/v1/payroll/payslips/")
    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_a_plain_employee_cannot_create_or_calculate_a_run(placed):
    client = APIClient()
    client.force_login(placed.user)
    created = client.post("/api/v1/payroll/runs/", {"period": PERIOD}, format="json")
    assert created.status_code == 403


@pytest.mark.django_db
def test_hr_manager_may_read_but_not_create_a_run(seeded, make_user):
    hr_manager_only = make_user("hr.read.only", "hr_manager")
    client = _mfa_client(hr_manager_only)  # HR Manager also needs MFA verified (iam.permissions)
    created = client.post("/api/v1/payroll/runs/", {"period": PERIOD}, format="json")
    assert created.status_code == 403
    listed = client.get("/api/v1/payroll/runs/")
    assert listed.status_code == 200


@pytest.mark.django_db
def test_a_run_for_an_existing_period_is_refused(preparer):
    client = _mfa_client(preparer)
    PayRun.objects.create(period=PERIOD)
    again = client.post("/api/v1/payroll/runs/", {"period": PERIOD}, format="json")
    assert again.status_code == 409


@pytest.mark.django_db
def test_a_calculated_run_can_be_reopened_and_a_draft_one_removed(rates_2026, placed, preparer):
    client = _mfa_client(preparer)
    run = PayRun.objects.create(period=PERIOD)
    client.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "calculate"}, format="json")
    reopened = client.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "reopen"}, format="json")
    assert reopened.status_code == 200
    assert reopened.json()["state"] == "draft"
    assert Payslip.objects.filter(pay_run=run).exists()  # left until the next calculate replaces them

    removed = client.delete(f"/api/v1/payroll/runs/{run.id}/")
    assert removed.status_code == 204


@pytest.mark.django_db
def test_the_inbox_shows_a_calculated_run_to_finance_but_not_to_its_preparer(
    rates_2026, placed, preparer, approver
):
    from approvals.inbox import waiting_for

    client = _mfa_client(preparer)
    run = PayRun.objects.create(period=PERIOD)
    client.post(f"/api/v1/payroll/runs/{run.id}/transition/", {"action": "calculate"}, format="json")

    assert any(item["kind"] == "payroll" for item in waiting_for(approver))
    assert not any(item["kind"] == "payroll" for item in waiting_for(preparer))
