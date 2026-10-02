"""Item 1.20: electronic acknowledgement and signature of documents, with the evidence kept.

The Electronic Communications and Transactions Act 2023 gives electronic records and signatures legal
standing. A signature here is the person, signed in, confirming with their password that they agree to a
stated sentence about one version of one document; what is kept is who, when, from where, on what device,
which version, and the SHA-256 fingerprint of the file as it was, so a later change to the file shows.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel
from people.models import Document, Employee


class SignatureRequest(TimeStampedModel):
    """HR asks a member of staff to read a document and acknowledge it, or accept it."""

    class Kind(models.TextChoices):
        ACKNOWLEDGE = "acknowledge", "Acknowledge receiving it"
        ACCEPT = "accept", "Accept it"

    class State(models.TextChoices):
        WAITING = "waiting", "Waiting"
        SIGNED = "signed", "Signed"
        DECLINED = "declined", "Declined"
        WITHDRAWN = "withdrawn", "Withdrawn"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="signature_requests")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="signature_requests")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    statement = models.CharField(max_length=300, help_text="The sentence they agree to")
    message = models.CharField(max_length=300, blank=True, help_text="A note from HR")
    due_by = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.WAITING)
    decided_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "employee"],
                condition=Q(state="waiting"),
                name="one_waiting_request_per_document",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.document} ({self.get_state_display()})"


class Signature(models.Model):
    """The evidence of one signature. Written once; nothing in the system changes it afterwards."""

    request = models.OneToOneField(SignatureRequest, on_delete=models.CASCADE, related_name="signature")
    signer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    signed_at = models.DateTimeField(default=timezone.now)
    statement = models.CharField(max_length=300, help_text="As it was shown when they signed")
    document_title = models.CharField(max_length=200)
    document_version = models.PositiveSmallIntegerField()
    sha256 = models.CharField(max_length=64, help_text="Fingerprint of the file as it was when signed")
    method = models.CharField(max_length=40, default="password confirmed while signed in")
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-signed_at"]

    def __str__(self) -> str:
        return f"{self.document_title}, signed {self.signed_at:%d/%m/%Y %H:%M}"
