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
