"""Shared test fixtures. Database tests need PostgreSQL (run inside the Compose stack or CI)."""

from datetime import date

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

requires_postgres = pytest.mark.skipif(
    "postgresql" not in settings.DATABASES["default"]["ENGINE"],
    reason="database tests need PostgreSQL; run them in the Compose stack or CI",
)


def pytest_collection_modifyitems(config, items):
    """Skip every database-marked test automatically when the engine is not PostgreSQL."""
    for item in items:
        if item.get_closest_marker("django_db"):
            item.add_marker(requires_postgres)


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    """Uploads in tests go to a temporary directory, never to the shared files volume."""
    settings.MEDIA_ROOT = tmp_path / "files"


@pytest.fixture(autouse=True)
def _encryption_key(settings):
    settings.FIELD_ENCRYPTION_KEY = "test-only-key"
    from core import crypto

    crypto._fernet.cache_clear()


@pytest.fixture
def seeded(db):
    from django.core.management import call_command

    call_command("seed", "--country", "GY", "--year", "2026", verbosity=0)


@pytest.fixture
def campus(seeded):
    from org.models import Campus

    return Campus.objects.get(code="MRP")


@pytest.fixture
def make_user(db):
    def _make(username, *roles, campus=None, superuser=False):
        from iam.models import Role, RoleScope

        user = get_user_model().objects.create_user(username=username, password="Str0ng-Passw0rd-123")
        if superuser:
            user.is_superuser = user.is_staff = True
            user.save()
        for code in roles:
            RoleScope.objects.create(user=user, role=Role.objects.get(code=code), campus=campus)
        return user

    return _make


@pytest.fixture
def hr_officer(make_user, campus):
    return make_user("hr.officer", "hr_officer", campus=campus)


@pytest.fixture
def hr_manager(make_user, seeded):
    return make_user("hr.manager", "hr_manager")


@pytest.fixture
def api(hr_officer):
    """API client logged in as the Mon Repos HR Officer (no MFA needed for that role)."""
    client = APIClient()
    client.force_login(hr_officer)
    return client


@pytest.fixture
def unit(campus, hr_officer):
    from org.models import Grade, OrgUnit, Position, SalaryScale

    unit = OrgUnit.objects.create(code="LIV", name="Livestock Unit", unit_type="unit", campus=campus)
    scale = SalaryScale.objects.create(code="GS", name="General scale")
    grade = Grade.objects.create(
        scale=scale, code="GS5", step=1, amount=250000, effective_from=date(2026, 1, 1)
    )
    Position.objects.create(number="LIV-001", title="Livestock Instructor", grade=grade, org_unit=unit)
    Position.objects.create(number="LIV-002", title="Farm Hand", grade=grade, org_unit=unit)
    return unit


@pytest.fixture
def employee(campus, unit):
    from people.models import Employee

    return Employee.objects.create(
        employee_no="E0001",
        first_name="Asha",
        last_name="Persaud",
        date_of_birth=date(1990, 3, 14),
        gender="F",
        national_id="123456789",
        nis_no="A1234567",
        tin="TIN000123",
        campus=campus,
    )
