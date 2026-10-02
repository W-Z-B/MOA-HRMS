"""Item 1.42: the sign-in email address changes only through a step confirmed from the new address.

The address is where links to choose a password go, so whoever reads it can take the account. A change is
asked for by the person, who confirms it with their password, or by HR, who give a reason. It takes effect
only when the link sent to the new address is followed, within EMAIL_CHANGE_HOURS. The old address is told
when the change is asked for and again when it is made, so a change nobody wanted is noticed. Each step is
in the audit log; the staff record's email follows the account when the two were the same.
"""

import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from audit.services import record
from iam.models import EmailChange


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hidden(address: str) -> str:
    """An address as the old one is told it: enough to recognise, not enough to write to."""
    name, _, domain = address.partition("@")
    return f"{name[:2]}…@{domain}" if domain else "another address"


def link(token: str) -> str:
    return f"{settings.PUBLIC_URL}/#/confirm-email/{token}"


def _mail(address: str, subject: str, lines: list[str]) -> bool:
    try:
        sent = send_mail(f"[GSA HRMS] {subject}", "\n\n".join(lines), settings.DEFAULT_FROM_EMAIL, [address])
        return sent == 1
    except Exception:  # noqa: BLE001 - a mail failure is reported to the caller, never raised into the request
        return False


def _taken(address: str, user) -> bool:
    return get_user_model().objects.filter(email__iexact=address).exclude(pk=user.pk).exists()


def pending_for(user) -> EmailChange | None:
    """The change waiting for its confirmation, if one is still within its time."""
    change = user.email_changes.filter(confirmed_at=None, cancelled_at=None).first()
    return change if change is not None and change.pending else None


def ask(request, user, new_email: str, *, reason: str = "") -> tuple[EmailChange, bool]:
    """Send the confirmation link to the new address and tell the old one. Any earlier request lapses.

    Returns the change and whether the link could be sent.
    """
    new_email = get_user_model().objects.normalize_email(new_email.strip())
    if new_email.lower() == (user.email or "").lower():
        raise Refused("same", "That is already the sign-in email address.")
    if _taken(new_email, user):
        raise Refused("taken", "Another account uses that address.")
    token = secrets.token_urlsafe(32)
    by_self = request.user.pk == user.pk
    with transaction.atomic():
        user.email_changes.filter(confirmed_at=None, cancelled_at=None).update(cancelled_at=timezone.now())
        change = EmailChange.objects.create(
            user=user,
            old_email=user.email or "",
            new_email=new_email,
            token_hash=_digest(token),
            asked_by=request.user,
            reason=reason.strip(),
        )
        after = {"new_email": new_email, "asked_by_the_person": by_self}
        record(request, "email_change_asked", user, after=after, reason=reason.strip())
    name = user.first_name or user.get_username()
    sent = _mail(
        new_email,
        "Confirm your new sign-in email address",
        [
            f"Hello {name},",
            f"This address is to become the sign-in email address of your GSA HRMS account "
            f"({user.get_username()}): links to choose a password will come here from now on.",
            f"Confirm it here. The link works once, for {settings.EMAIL_CHANGE_HOURS} hours:\n{link(token)}",
            "If you were not expecting this, ignore this email: nothing changes unless the link is followed.",
        ],
    )
    if user.email:
        who = "You" if by_self else "Human Resources"
        _mail(
            user.email,
            "Your sign-in email address is to change",
            [
                f"Hello {name},",
                f"{who} asked for the sign-in email address of your GSA HRMS account "
                f"({user.get_username()}) to change to {hidden(new_email)}. It changes only when the link "
                "sent there is followed.",
                "If you did not expect this, tell Human Resources at once.",
            ],
        )
    return change, sent


def confirm(request, token: str) -> EmailChange:
    """Make the change, when the link is the latest one asked for and still within its time."""
    change = EmailChange.objects.select_related("user").filter(token_hash=_digest(token)).first()
    if change is None or not change.pending:
        raise Refused(
            "expired",
            "This link has expired, has been used, or was replaced by a newer one. Ask for the change again.",
        )
    user = change.user
    if not user.is_active:
        raise Refused("switched_off", "That account is switched off. Ask Human Resources.")
    if _taken(change.new_email, user):
        raise Refused("taken", "Another account now uses that address. Ask Human Resources.")
    old = user.email or ""
    with transaction.atomic():
        user.email = change.new_email
        user.save(update_fields=["email"])
        employee = getattr(user, "employee", None)
        if employee is not None and (not employee.email or employee.email.lower() == old.lower()):
            employee.email = change.new_email  # the staff record follows when the two were the same
            employee.save(update_fields=["email", "updated_at"])
        change.confirmed_at = timezone.now()
        change.save(update_fields=["confirmed_at"])
        record(
            request, "sign_in_email_changed", user, before={"email": old}, after={"email": change.new_email}
        )
    if old:
        _mail(
            old,
            "Your sign-in email address has changed",
            [
                f"Hello {user.first_name or user.get_username()},",
                f"The sign-in email address of your GSA HRMS account ({user.get_username()}) is now "
                f"{hidden(change.new_email)}. Links to choose a password will no longer come here.",
                "If you did not expect this, tell Human Resources at once.",
            ],
        )
    return change
