"""Item 1.15: the discipline and grievance case register, open to named officers only.

A dismissal must be for good and sufficient cause (Termination of Employment and Severance Pay Act 1997,
section 7) and never for a reason section 8 forbids. The register keeps the steps that show it was fair: the
allegation put in writing, a chance to answer it, a decision recorded with its reasons, and an appeal heard by
someone who did not make the decision. It is the most restricted record in the system: the HR Manager sees
every case, anyone else only a case they are named on, and nobody a case about themselves. Its audit rows
name the case, never what it says, and stay out of the person's file history.
"""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel
from people.models import Employee


class Case(TimeStampedModel):
    class Kind(models.TextChoices):
        DISCIPLINE = "discipline", "Discipline"
        GRIEVANCE = "grievance", "Grievance"

    class State(models.TextChoices):
        OPEN = "open", "Open"
        DECIDED = "decided", "Decided"
        APPEAL = "appeal", "Under appeal"
        CLOSED = "closed", "Closed"

    class Outcome(models.TextChoices):
        NO_ACTION = "no_action", "No action"
        COUNSELLING = "counselling", "Counselling"
        VERBAL_WARNING = "verbal_warning", "Verbal warning"
        WRITTEN_WARNING = "written_warning", "Written warning"
        FINAL_WARNING = "final_warning", "Final written warning"
        SUSPENSION = "suspension", "Suspension"
        DISMISSAL = "dismissal", "Dismissal"
        UPHELD = "upheld", "Grievance upheld"
        PARTLY_UPHELD = "partly_upheld", "Grievance partly upheld"
        NOT_UPHELD = "not_upheld", "Grievance not upheld"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class AppealOutcome(models.TextChoices):
        CONFIRMED = "confirmed", "Decision confirmed"
        VARIED = "varied", "Decision varied"
        OVERTURNED = "overturned", "Decision overturned"

    reference = models.CharField(max_length=20, unique=True)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="cases")
    summary = models.TextField(help_text="The allegation, or the grievance, in words")
    opened_on = models.DateField()
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    outcome_reasons = models.TextField(blank=True)
    decided_on = models.DateField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    lapses_on = models.DateField(null=True, blank=True, help_text="When a warning stops counting")
    appeal_lodged_on = models.DateField(null=True, blank=True)
    appeal_grounds = models.TextField(blank=True)
    appeal_outcome = models.CharField(max_length=12, choices=AppealOutcome.choices, blank=True)
    appeal_reasons = models.TextField(blank=True)
    appeal_decided_on = models.DateField(null=True, blank=True)
    appeal_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    closed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_on", "-id"]

    def __str__(self) -> str:
        return self.reference


class CaseOfficer(models.Model):
    """Someone named on a case, and so able to see it, with what they do on it."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="officers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="case_roles")
    part = models.CharField(max_length=80, help_text="Such as investigating officer, or chair of the hearing")
    named_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    named_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["named_at"]
        constraints = [models.UniqueConstraint(fields=["case", "user"], name="named_once_on_a_case")]

    def __str__(self) -> str:
        return f"{self.user} on {self.case} ({self.part})"


class CaseEntry(TimeStampedModel):
    """One step in a case, in the order it happened."""

    class Kind(models.TextChoices):
        ALLEGATION = "allegation", "Allegation put in writing"
        RESPONSE = "response", "Response from the employee"
        INVESTIGATION = "investigation", "Investigation"
        MEETING = "meeting", "Meeting"
        HEARING = "hearing", "Hearing"
        NOTE = "note", "Note"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="entries")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    on = models.DateField()
    text = models.TextField()

    class Meta:
        ordering = ["on", "id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} on {self.on:%d/%m/%Y}"
