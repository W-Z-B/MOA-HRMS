"""Identity and access: roles, campus and unit scopes, multi-factor devices."""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class Role(TimeStampedModel):
    ADMINISTRATOR = "administrator"
    HR_MANAGER = "hr_manager"
    HR_OFFICER = "hr_officer"
    FINANCE = "finance"
    PRINCIPAL = "principal"
    SUPERVISOR = "supervisor"
    EMPLOYEE = "employee"
    MINISTRY_LIAISON = "ministry_liaison"
    AUDITOR = "auditor"
    CODES = (
        (ADMINISTRATOR, "System Administrator"),
        (HR_MANAGER, "HR Manager"),
        (HR_OFFICER, "HR Officer"),
        (FINANCE, "Finance / Payroll Officer"),
        (PRINCIPAL, "Principal / Deputy Principal"),
        (SUPERVISOR, "Supervisor / Head of Department"),
        (EMPLOYEE, "Employee"),
        (MINISTRY_LIAISON, "Ministry of Agriculture Liaison"),
        (AUDITOR, "Auditor"),
    )
    MFA_REQUIRED = frozenset({ADMINISTRATOR, HR_MANAGER, FINANCE})
    # Roles that see pay: rates on contracts and the amounts of the salary scale.
    SEES_PAY = frozenset({HR_OFFICER, HR_MANAGER, ADMINISTRATOR, FINANCE, PRINCIPAL, AUDITOR})

    code = models.CharField(max_length=40, unique=True, choices=CODES)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class RoleScope(TimeStampedModel):
    """Grants a role to a user, optionally limited to one campus or one organisational unit."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_scopes")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="scopes")
    campus = models.ForeignKey("org.Campus", null=True, blank=True, on_delete=models.CASCADE)
    org_unit = models.ForeignKey("org.OrgUnit", null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("user", "role", "campus", "org_unit")]

    def __str__(self) -> str:
        scope = self.org_unit or self.campus or "all campuses"
        return f"{self.user} as {self.role.code} ({scope})"


class TotpDevice(TimeStampedModel):
    """Time-based one-time password enrolment; required for privileged roles (Role.MFA_REQUIRED)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp_device"
    )
    secret = EncryptedTextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class LoginAttempt(models.Model):
    """Every login attempt, used to lock an account after repeated failures (see iam.views.login_view).

    Choosing a password through an emailed link is kept here as a success too: it proves the person, so
    the failures before it no longer count towards a lockout.
    """

    username = models.CharField(max_length=150, db_index=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    success = models.BooleanField(default=False)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["source_ip", "at"], name="loginattempt_ip_at")]

    def __str__(self) -> str:
        return f"{self.username} {'ok' if self.success else 'failed'} at {self.at:%Y-%m-%d %H:%M}"


class PasswordResetRequest(models.Model):
    """A request for a password link, kept to limit how often one address, or one account, may ask.

    What was typed is not kept: only the account it matched, if any, and the address it came from.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["source_ip", "at"], name="resetrequest_ip_at")]

    def __str__(self) -> str:
        return f"Password link asked for at {self.at:%Y-%m-%d %H:%M}"


class AccessReview(models.Model):
    """A sign-off that someone went through the list of who can see what and confirmed it (item 1.27).

    The access-review report is the list; this row is the evidence that it was checked, for the auditor.
    """

    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(auto_now_add=True)
    accounts = models.PositiveIntegerField(help_text="How many accounts the list held when it was signed off")
    notes = models.TextField(blank=True, help_text="What was changed or queried as a result")

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self) -> str:
        return f"Access review {self.reviewed_at:%d/%m/%Y} by {self.reviewed_by}"


class UserSession(models.Model):
    """One signed-in browser or phone, so people can see where they are signed in and end a session.

    Created on sign-in and deleted on sign-out (iam.sessions); the middleware keeps last_seen_at current
    and ends sessions that are idle or too old.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        return f"{self.user} since {self.created_at:%Y-%m-%d %H:%M}"


class EmailChange(models.Model):
    """A change of sign-in email address, waiting for the link sent to the new address (item 1.42).

    The address is where links to choose a password go, so a change takes effect only when the person
    proves they can read mail sent to the new one. Only a fingerprint of the link's token is kept.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_changes")
    old_email = models.EmailField(blank=True)
    new_email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    asked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    asked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reason = models.CharField(max_length=300, blank=True, help_text="Why, when HR asked for it")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-asked_at"]

    @property
    def expires_at(self):
        return self.asked_at + timedelta(hours=settings.EMAIL_CHANGE_HOURS)

    @property
    def pending(self) -> bool:
        return self.confirmed_at is None and self.cancelled_at is None and timezone.now() < self.expires_at

    def __str__(self) -> str:
        return f"{self.user} to {self.new_email}"
