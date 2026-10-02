"""Item 1.47: anyone shown a letter can check it is genuine, by its reference and the code printed on it.

The answer says only what the letter itself says: whom it is about, what it is, when it was issued, and its
words as issued, to compare with the paper in hand. A wrong code and an unknown reference get the same
answer, so the page never tells which references exist. Failures are limited for each network address and
each reference, every check is logged, and the person the letter is about is told when it has been checked.
"""

import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from audit.services import record_event
from core.net import client_ip
from letters import markup
from letters.models import Letter, LetterCheck
from letters.services import ADDRESS_FIELDS
from notifications.services import notify

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford's: no I, L, O or U, so nothing is misread
LENGTH = 12  # 60 bits: out of reach of guessing at a few tries an hour
READ_AS = str.maketrans("OIL", "011")


class TooMany(Exception):
    """Too many wrong answers lately, from this address or for this reference."""


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return "-".join(raw[i : i + 4] for i in range(0, LENGTH, 4))


def plain(code: str) -> str:
    """A code as it may be typed: any case, with spaces or dashes, O for 0 and I or L for 1."""
    return re.sub(r"[\s-]", "", code.upper()).translate(READ_AS)


def _blocked(address: str | None, reference: str) -> bool:
    since = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    failures = LetterCheck.objects.filter(matched=False, at__gte=since)
    limit = settings.LETTER_CHECK_FAILURES
    if address is not None and failures.filter(source_ip=address).count() >= limit:
        return True
    return failures.filter(reference__iexact=reference).count() >= limit


def check(request, reference: str, code: str) -> Letter | None:
    """The letter, when the reference and code match one; None otherwise. Raises TooMany when blocked."""
    reference = reference.strip()[:40]
    address = client_ip(request)
    if _blocked(address, reference):
        raise TooMany
    letter = (
        Letter.objects.filter(reference__iexact=reference)
        .select_related("employee", "template", "employee__user")
        .first()
    )
    given = plain(code).encode()
    matched = bool(
        letter is not None
        and letter.check_code
        and hmac.compare_digest(plain(letter.check_code).encode(), given)
    )
    LetterCheck.objects.create(
        reference=reference, letter=letter if matched else None, matched=matched, source_ip=address
    )
    if not matched:
        return None
    after = {"letter": letter.pk, "reference": letter.reference}
    record_event(request, "letter_checked", "letters.letter", after=after)
    user = letter.employee.user
    if user is not None and user.is_active:
        today = timezone.localdate()
        notify(
            [user],
            title=f"Your letter {letter.reference} was checked",
            body="Someone you showed it to checked that it is genuine. If you showed it to no one, "
            "tell Human Resources.",
            link="/me",
            email=False,
            dedupe_key=f"letter-checked:{letter.pk}:{today:%Y%m%d}",
        )
    return letter


def as_issued(letter: Letter) -> dict:
    """The letter's words as issued, from the template version and the values it was written with."""
    template = letter.template
    values = letter.values
    return {
        "subject": markup.fill(template.subject, values),
        "addressed": template.addressed,
        "blocks": markup.merge(markup.parse(template.body), values),
        "values": {key: values.get(key, "") for key in ADDRESS_FIELDS} if template.addressed else {},
    }
