"""Role look-ups used by permissions, scoping and workflows."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from iam.models import LoginAttempt, Role, RoleScope

BROAD_READ_ROLES = frozenset(
    {Role.ADMINISTRATOR, Role.HR_MANAGER, Role.PRINCIPAL, Role.FINANCE, Role.AUDITOR}
)


def role_codes(user) -> set[str]:
    """Roles a signed-in person holds. A service key (no pk) is not a person and holds none."""
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return set()
    cached = getattr(user, "_role_codes", None)
    if cached is None:
        cached = set(RoleScope.objects.filter(user=user).values_list("role__code", flat=True))
        user._role_codes = cached
    return cached


def has_role(user, *codes: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return bool(role_codes(user) & set(codes))


def campus_ids(user) -> set[int]:
    """Campuses the user is explicitly scoped to. Empty means unrestricted for broad roles."""
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return set()
    return set(RoleScope.objects.filter(user=user, campus__isnull=False).values_list("campus_id", flat=True))


def requires_mfa(user) -> bool:
    return bool(role_codes(user) & Role.MFA_REQUIRED) or getattr(user, "is_superuser", False)


def campus_in_scope(user, campus_id) -> bool:
    """Whether the user may write records on that campus: broad roles anywhere, others on their own."""
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return False
    if getattr(user, "is_superuser", False) or role_codes(user) & BROAD_READ_ROLES:
        return True
    return campus_id in campus_ids(user)


def campus_limit(user) -> set[int] | None:
    """The campuses a user may read about: None for every campus (broad roles), else their own.

    Fails closed: a caller who is not a signed-in person (anonymous, or a service key) gets no campus.
    """
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return set()
    if getattr(user, "is_superuser", False) or role_codes(user) & BROAD_READ_ROLES:
        return None
    return campus_ids(user)


def scope_queryset(user, queryset, campus_field: str = "campus"):
    """Restrict a queryset to the user's campuses unless the user holds a broad role."""
    ids = campus_limit(user)
    if ids is None:
        return queryset
    if not ids:
        return queryset.none()
    return queryset.filter(**{f"{campus_field}__in": ids})


def account_locked(username: str) -> bool:
    """True when the account has reached the failure limit inside the lockout window."""
    window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    recent = LoginAttempt.objects.filter(username=username, at__gte=window_start).order_by("-at")
    failures = 0
    for attempt in recent[: settings.LOGIN_MAX_FAILURES]:
        if attempt.success:
            break
        failures += 1
    return failures >= settings.LOGIN_MAX_FAILURES


def address_blocked(address: str | None) -> bool:
    """True when one address has failed too often inside the window, whatever the accounts tried.

    The account lockout stops guessing one person's password; this stops one password being tried
    against many accounts. Only failures count, so a campus signing in through one network address is
    not held up by its own successful sign-ins.
    """
    if address is None:
        return False
    window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    failures = LoginAttempt.objects.filter(source_ip=address, success=False, at__gte=window_start).count()
    return failures >= settings.LOGIN_MAX_FAILURES_PER_ADDRESS
