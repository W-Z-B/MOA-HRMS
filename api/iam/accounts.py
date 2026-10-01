"""Accounts for staff: invitations, password links, roles and switching off (items 1.25, 1.27, 1.29).

Nobody chooses or sees another person's password. An account is opened for an employee with no usable
password, and the employee chooses their own through a one-use link sent to their email address. The same
kind of link resets a forgotten password. A link stops working once a password is chosen (it is signed
over the password hash and the last sign-in) and after its time limit: INVITATION_DAYS for invitations,
PASSWORD_RESET_MINUTES for resets.

Who may change whose account follows the roles. HR officers look after staff accounts on their campus;
the HR Manager also appoints HR officers; only an administrator gives the roles that see across campuses,
handle money or answer to the Ministry, and only someone who could give every role an account holds may
change that account. Nobody changes their own account here. Together these keep an administrator in
place: an administrator's account can be changed only by another administrator, who remains.
"""

import re
import unicodedata

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_decode, urlsafe_base64_encode

from iam.models import Role, RoleScope, UserSession
from iam.services import campus_limit, role_codes
from iam.sessions import end_sessions

ALL_ROLES = frozenset(code for code, _ in Role.CODES)
# The roles each role may give and take away. Whatever the HR Manager cannot give (seeing every campus,
# money, the Ministry, audit, administration) only an administrator gives.
GIVES = {
    Role.ADMINISTRATOR: ALL_ROLES,
    Role.HR_MANAGER: frozenset({Role.EMPLOYEE, Role.SUPERVISOR, Role.HR_OFFICER}),
    Role.HR_OFFICER: frozenset({Role.EMPLOYEE, Role.SUPERVISOR}),
}
PRIVILEGED = ALL_ROLES - GIVES[Role.HR_MANAGER]
# Roles that work on one campus and mean nothing without it.
CAMPUS_ROLES = frozenset({Role.EMPLOYEE, Role.SUPERVISOR, Role.HR_OFFICER})
# The two kinds of emailed link that choose a password.
LINK_KINDS = (("invitation", "Invitation to a new account"), ("reset", "Reset of a forgotten password"))


class LinkTokens(PasswordResetTokenGenerator):
    """One-use tokens with their own time limit. Django's PASSWORD_RESET_TIMEOUT is set to the longest
    limit in settings, so the stricter limit here is the one that decides."""

    def __init__(self, salt: str, seconds: int):
        super().__init__()
        self.key_salt = salt
        self.seconds = seconds

    def check_token(self, user, token) -> bool:
        if not (user and token) or token.count("-") != 1:
            return False
        try:
            issued = base36_to_int(token.split("-")[0])
        except ValueError:
            return False
        if self._num_seconds(self._now()) - issued > self.seconds:
            return False
        return super().check_token(user, token)


def invitation_tokens() -> LinkTokens:
    return LinkTokens("gsa-hrms.invitation", settings.INVITATION_DAYS * 24 * 3600)


def reset_tokens() -> LinkTokens:
    return LinkTokens("gsa-hrms.password-reset", settings.PASSWORD_RESET_MINUTES * 60)


def password_link(user, tokens: LinkTokens) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f"{settings.PUBLIC_URL}/#/set-password/{uid}/{tokens.make_token(user)}"


def user_from_link(uid: str):
    try:
        pk = int(urlsafe_base64_decode(uid).decode())
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    return get_user_model().objects.filter(pk=pk, is_active=True).first()


def link_kind(user, token: str) -> str | None:
    """ "invitation" or "reset" when the token opens that account, None when it has expired or been used."""
    if user is None:
        return None
    if invitation_tokens().check_token(user, token):
        return "invitation"
    if reset_tokens().check_token(user, token):
        return "reset"
    return None


def accounts_for(login: str) -> list:
    """Active accounts that a username, or an email address, names and that have an address to write to."""
    text = login.strip()
    if not text:
        return []
    users = get_user_model().objects.filter(is_active=True).exclude(email="")
    found = list(users.filter(username=text))
    if not found and "@" in text:
        found = list(users.filter(email__iexact=text))
    return found[:5]


def never_used(user) -> bool:
    """Opened but never signed in to and no password chosen: the invitation is still outstanding."""
    return not user.has_usable_password() and user.last_login is None


def suggest_username(first_name: str, last_name: str) -> str:
    """first.last in plain letters ("Asha Persaud" becomes asha.persaud), numbered if already taken."""

    def plain(text: str) -> str:
        ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "", ascii_text.lower())

    base = ".".join(part for part in (plain(first_name), plain(last_name)) if part) or "staff"
    users = get_user_model().objects
    candidate, number = base, 1
    while users.filter(username=candidate).exists():
        number += 1
        candidate = f"{base}{number}"
    return candidate


def _send(user, subject: str, lines: list[str]) -> bool:
    try:
        return (
            send_mail(f"[GSA HRMS] {subject}", "\n\n".join(lines), settings.DEFAULT_FROM_EMAIL, [user.email])
            == 1
        )
    except Exception:  # noqa: BLE001 - mail failure is reported to the caller, never raised into the request
        return False


def send_invitation(user) -> bool:
    return _send(
        user,
        "Your account",
        [
            f"Hello {user.first_name or user.get_username()},",
            f"An account has been opened for you on the GSA HRMS. Your username is {user.get_username()}.",
            f"Choose your password here. The link works once, for {settings.INVITATION_DAYS} days:\n"
            f"{password_link(user, invitation_tokens())}",
            "If you were not expecting this, tell Human Resources.",
        ],
    )


def send_reset(user) -> bool:
    return _send(
        user,
        "Choose a new password",
        [
            f"Hello {user.first_name or user.get_username()},",
            f"Someone asked for a new password for your GSA HRMS account ({user.get_username()}).",
            f"Choose it here. The link works once, for {settings.PASSWORD_RESET_MINUTES} minutes:\n"
            f"{password_link(user, reset_tokens())}",
            "If it was not you, ignore this email: your password has not changed.",
        ],
    )


@transaction.atomic
def open_account(employee, *, granted_by):
    """An account for the employee with the employee role on their campus. They choose their own password."""
    user = get_user_model().objects.create_user(
        username=suggest_username(employee.first_name, employee.last_name),
        email=employee.email,
        first_name=employee.first_name,
        last_name=employee.last_name,
        password=None,  # unusable until the employee chooses one through the invitation
    )
    employee.user = user
    employee.save(update_fields=["user", "updated_at"])
    RoleScope.objects.create(
        user=user, role=Role.objects.get(code=Role.EMPLOYEE), campus=employee.campus, created_by=granted_by
    )
    return user


def open_external_account(*, first_name: str, last_name: str, email: str):
    """An account for someone not on the staff (an auditor, the Ministry liaison), with no role yet."""
    return get_user_model().objects.create_user(
        username=suggest_username(first_name, last_name),
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=None,
    )


def close_sessions(user) -> int:
    """Sign the person out everywhere."""
    return end_sessions(UserSession.objects.filter(user=user))


def gives(user) -> frozenset[str]:
    """The roles this person may give and take away."""
    if getattr(user, "is_superuser", False):
        return ALL_ROLES
    return frozenset().union(*(GIVES.get(code, frozenset()) for code in role_codes(user)))


def refusal(actor, target) -> str | None:
    """Why the actor may not change the target's account, or None when they may."""
    if target.pk == actor.pk:
        return "You cannot change your own account here: ask another administrator or HR officer."
    if target.is_superuser and not actor.is_superuser:
        return "This is a system account. Only a superuser changes it."
    held = set(RoleScope.objects.filter(user=target).values_list("role__code", flat=True))
    if not held <= gives(actor):
        return "This person holds a role you cannot give, so only an administrator can change their account."
    return None


def grant_refusal(actor, role_code: str, campus) -> str | None:
    """Why the actor may not give that role on that campus, or None when they may."""
    if role_code not in gives(actor):
        return "Only an administrator gives that role."
    if campus is None and role_code in CAMPUS_ROLES:
        return "Choose the campus this role covers."
    limit = campus_limit(actor)
    if limit is not None and (campus is None or campus.pk not in limit):
        return "That campus is not one you work with."
    return None


def where(grant) -> str:
    """The campus or unit a role covers, in words."""
    if grant.org_unit_id:
        return grant.org_unit.name
    return grant.campus.name if grant.campus_id else "All campuses"


def describe_roles(user) -> str:
    """The roles an account holds, in words, for the audit log and the person's history."""
    grants = RoleScope.objects.filter(user=user).select_related("role", "campus", "org_unit")
    return "; ".join(sorted(f"{grant.role.name} ({where(grant)})" for grant in grants)) or "No role"
