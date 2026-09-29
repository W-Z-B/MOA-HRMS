import pytest
from django.core.exceptions import ImproperlyConfigured

from core import crypto


def test_encrypt_decrypt_round_trip():
    token = crypto.encrypt("A1234567")
    assert token != b"A1234567"
    assert crypto.decrypt(token) == "A1234567"


def test_mask_shows_only_last_characters():
    assert crypto.mask("A1234567") == "•••••567"
    assert crypto.mask("") is None
    assert crypto.mask(None) is None


def test_missing_key_is_a_configuration_error(settings):
    settings.FIELD_ENCRYPTION_KEY = ""
    crypto._fernet.cache_clear()
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt("x")
    crypto._fernet.cache_clear()


@pytest.mark.django_db
def test_seed_is_idempotent(seeded):
    from django.core.management import call_command

    from core.models import PublicHoliday
    from org.models import Campus

    before = (Campus.objects.count(), PublicHoliday.objects.count())
    call_command("seed", "--country", "GY", "--year", "2026", verbosity=0)
    assert (Campus.objects.count(), PublicHoliday.objects.count()) == before
    assert Campus.objects.filter(code__in=["MRP", "ESQ"]).count() == 2


@pytest.mark.django_db
def test_demonstration_data_is_fictional_idempotent_and_consistent(seeded):
    from decimal import Decimal

    from django.core.management import CommandError, call_command

    from leave.models import LeaveLedger, LeaveRequest, LeaveType
    from leave.services import balance
    from org.models import OrgUnit, Position
    from people.models import Assignment, Employee

    with pytest.raises(CommandError):
        call_command("seed_demo", verbosity=0)
    assert Employee.objects.count() == 0

    call_command("seed_demo", fictional=True, verbosity=0)
    counts = (
        Employee.objects.count(),
        Position.objects.count(),
        Assignment.objects.count(),
        LeaveLedger.objects.count(),
        LeaveRequest.objects.count(),
    )
    call_command("seed_demo", fictional=True, verbosity=0)
    assert counts == (
        Employee.objects.count(),
        Position.objects.count(),
        Assignment.objects.count(),
        LeaveLedger.objects.count(),
        LeaveRequest.objects.count(),
    )
    assert counts[:3] == (9, 13, 9)

    assert not Employee.objects.exclude(address__icontains="fictional").exists()
    assert not Employee.objects.exclude(email__endswith="@gsa.example").exists()
    assert Employee.objects.get(employee_no="E0001").national_id.startswith("DEMO-")
    assert sorted(p.number for p in Position.objects.all() if p.is_vacant) == [
        "ADM-003",
        "AGR-004",
        "ESQ-AGR-003",
        "LIV-003",
    ]
    assert OrgUnit.objects.get(code="AGR").head.employee_no == "E0002"
    # opening balance of 10 days less the approved week in August
    head = Employee.objects.get(employee_no="E0002")
    assert balance(head, LeaveType.objects.get(code="ANN")) == Decimal("5")


@pytest.mark.django_db
def test_demonstration_staff_have_contracts_and_managers(seeded, monkeypatch):
    from decimal import Decimal

    from django.core.management import call_command

    from leave.models import LeaveRequest, LeaveType
    from leave.services import entitlement_days
    from people.models import Contract, Employee
    from people.services import current_contract, hourly_rate, manager_of

    monkeypatch.delenv("DEMO_USER_PASSWORD", raising=False)
    call_command("seed_demo", fictional=True, verbosity=0)
    call_command("seed_demo", fictional=True, verbosity=0)
    assert Contract.objects.count() == 9

    staff = {e.employee_no: e for e in Employee.objects.all()}
    # Paid by the hour, and paid on grade GS7 at 250,000 a month over 40 hours a week.
    assert hourly_rate(current_contract(staff["E0005"])) == Decimal("750.00")
    assert hourly_rate(current_contract(staff["E0001"])) == Decimal("1442.31")
    # The fixed-term contract carries its own entitlement; the others take the standard.
    annual = LeaveType.objects.get(code="ANN")
    assert entitlement_days(staff["E0009"], annual) == Decimal("14")
    assert entitlement_days(staff["E0001"], annual) == Decimal("21")
    # Without the password variable nobody can sign in, so nobody can be sent a request.
    assert not Employee.objects.filter(user__isnull=False).exists()
    assert manager_of(staff["E0001"]) is None
    assert not LeaveRequest.objects.filter(manager__isnull=False).exists()


@pytest.mark.django_db
def test_demonstration_accounts_need_a_password_from_the_owner(seeded, monkeypatch):
    from django.contrib.auth import get_user_model
    from django.core.management import CommandError, call_command

    from iam.services import role_codes
    from leave.models import LeaveRequest
    from people.models import Employee
    from people.services import manager_of

    monkeypatch.setenv("DEMO_USER_PASSWORD", "short")
    with pytest.raises(CommandError, match="too weak"):
        call_command("seed_demo", fictional=True, verbosity=0)
    assert not get_user_model().objects.exists()

    monkeypatch.setenv("DEMO_USER_PASSWORD", "Correct-Horse-Battery-9")
    call_command("seed_demo", fictional=True, verbosity=0)
    users = get_user_model().objects
    assert users.count() == 9 and users.get(username="asha.persaud").check_password("Correct-Horse-Battery-9")

    staff = {e.employee_no: e for e in Employee.objects.select_related("user")}
    assert role_codes(staff["E0001"].user) == {"employee"}
    assert role_codes(staff["E0002"].user) == {"employee", "supervisor"}
    assert role_codes(staff["E0006"].user) == {"employee", "supervisor", "hr_officer"}
    assert staff["E0006"].user.role_scopes.filter(role__code="hr_officer").count() == 2
    # Lecturer to head of department; head of the livestock unit to the department above.
    assert manager_of(staff["E0001"]) == staff["E0002"]
    assert manager_of(staff["E0004"]) == staff["E0002"]
    assert manager_of(staff["E0002"]) is None
    # The requests already waiting are sent to the managers, now that they can sign in.
    waiting = {r.employee.employee_no: r.manager for r in LeaveRequest.objects.filter(state="submitted")}
    assert waiting == {"E0005": staff["E0004"], "E0007": staff["E0006"]}

    # A second run changes no password and adds nobody.
    staff["E0001"].user.set_password("Changed-By-The-Owner-1")
    staff["E0001"].user.save()
    monkeypatch.setenv("DEMO_USER_PASSWORD", "Another-Password-Entirely-2")
    call_command("seed_demo", fictional=True, verbosity=0)
    assert users.count() == 9 and users.get(username="asha.persaud").check_password("Changed-By-The-Owner-1")
