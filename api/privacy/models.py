"""Privacy rights under the Data Protection Act 2023 (item 1.31): the notice each person reads and
acknowledges, and requests to correct what the system holds about them."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class PrivacyNotice(models.Model):
    """One version of the privacy notice. A draft can be edited; a published version never changes, so
    every acknowledgement points at exactly the words that were read."""

    version = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Plain text; a blank line starts a new paragraph")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="Empty while it is a draft")
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"Privacy notice {self.version}{'' if self.published_at else ' (draft)'}"


class NoticeAcknowledgement(models.Model):
    """That a person read a version of the notice, and when."""

    notice = models.ForeignKey(PrivacyNotice, on_delete=models.PROTECT, related_name="acknowledgements")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    at = models.DateTimeField(auto_now_add=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]
        constraints = [
            models.UniqueConstraint(fields=["notice", "user"], name="one_acknowledgement_per_notice")
        ]

    def __str__(self) -> str:
        return f"{self.user} read notice {self.notice.version}"


class CorrectionRequest(TimeStampedModel):
    """A person says something held about them is wrong. HR corrects it, or says why not."""

    class Subject(models.TextChoices):
        PERSONAL = "personal", "Personal details"
        CONTACT = "contact", "Contact details"
        EMERGENCY = "emergency", "Emergency contacts"
        DEPENDANTS = "dependants", "Dependants"
        QUALIFICATIONS = "qualifications", "Qualifications"
        PREVIOUS = "previous", "Work before GSA"
        BANK = "bank", "Bank details"
        APPOINTMENT = "appointment", "Appointment or contract"
        LEAVE = "leave", "Leave records"
        OTHER = "other", "Something else"

    class State(models.TextChoices):
        OPEN = "open", "With Human Resources"
        CORRECTED = "corrected", "Corrected"
        DECLINED = "declined", "Not changed"

    employee = models.ForeignKey(
        "people.Employee", on_delete=models.CASCADE, related_name="correction_requests"
    )
    subject = models.CharField(max_length=20, choices=Subject.choices)
    wrong = models.TextField(max_length=1000, help_text="What is wrong")
    should_be = models.TextField(max_length=1000, help_text="What it should say")
    state = models.CharField(max_length=12, choices=State.choices, default=State.OPEN)
    due_by = models.DateField(help_text="When HR should have answered (PRIVACY_RESPONSE_DAYS after asking)")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(max_length=1000, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Correction {self.id} for {self.employee}: {self.get_state_display()}"
