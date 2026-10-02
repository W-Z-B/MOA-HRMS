"""Item 1.19: letter templates that draw on the staff record, and the letters issued from them.

Item 1.47: each letter carries a code at its foot, so that whoever it is shown to can check it is genuine.
"""

from django.db import models

from core.fields import EncryptedTextField
from core.models import TimeStampedModel
from people.models import Document, Employee


class LetterTemplate(TimeStampedModel):
    """One version of a letter's wording. A change is saved as the next version; a letter keeps its own."""

    class Kind(models.TextChoices):
        APPOINTMENT = "appointment", "Appointment"
        CONFIRMATION = "confirmation", "Confirmation of appointment"
        JOB_LETTER = "job_letter", "Job letter"
        TRANSFER = "transfer", "Transfer"
        PROMOTION = "promotion", "Promotion"
        ACTING = "acting", "Acting appointment"
        INCREMENT = "increment", "Increment"
        EXIT = "exit", "Leaving"
        OTHER = "other", "Other"

    code = models.SlugField(max_length=40, help_text="The same in every version")
    version = models.PositiveSmallIntegerField(default=1)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=200, help_text="The heading line; it may hold fields")
    body = models.TextField(help_text="Paragraphs apart by a blank line, fields in double braces")
    asks = models.JSONField(default=list, blank=True, help_text="What is asked when a letter is written")
    addressed = models.BooleanField(
        default=True,
        help_text="Starts with the person's name and post; off for to-whom-it-may-concern letters",
    )
    classification = models.CharField(
        max_length=20, choices=Document.Classification.choices, default=Document.Classification.CONFIDENTIAL
    )
    signatory_name = models.CharField(max_length=120, blank=True)
    signatory_title = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="one_letter_template_version")
        ]

    def __str__(self) -> str:
        return f"{self.name}, version {self.version}"


class Letter(TimeStampedModel):
    """A letter issued to a member of staff. Its PDF is a document in their file; what went into it is kept.

    It goes with its document: when the retention schedule destroys the one, the other goes too.
    """

    reference = models.CharField(max_length=30, unique=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="letters")
    template = models.ForeignKey(LetterTemplate, on_delete=models.PROTECT, related_name="letters")
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="letter")
    issued_on = models.DateField()
    values = models.JSONField(help_text="Every field as it went into the letter")
    sha256 = models.CharField(max_length=64, help_text="Fingerprint of the PDF as issued")
    career_event = models.ForeignKey(
        "people.CareerEvent", null=True, blank=True, on_delete=models.SET_NULL, related_name="letters"
    )
    check_code = EncryptedTextField(
        null=True, blank=True, help_text="Printed on the letter for checking it; none before item 1.47"
    )

    class Meta:
        ordering = ["-issued_on", "-id"]

    def __str__(self) -> str:
        return self.reference


class LetterCheck(models.Model):
    """One use of the page that checks a letter: the reference asked about, whether the code matched, and
    the network address it came from. Kept a year, like sign-in attempts (the retention schedule)."""

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    reference = models.CharField(max_length=40)
    letter = models.ForeignKey(Letter, null=True, blank=True, on_delete=models.CASCADE, related_name="checks")
    matched = models.BooleanField()
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.reference} checked at {self.at:%d/%m/%Y %H:%M}"
