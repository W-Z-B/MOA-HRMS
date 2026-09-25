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
