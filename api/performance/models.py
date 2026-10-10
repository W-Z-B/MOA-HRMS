"""H-M03 Performance management: review cycles, goals, and a self-assessment plus manager-assessment
form driven by the approvals engine (item 1.33), replacing the read-only F08 scaffold.

A cycle is annual by default: nothing on ``people.Contract`` or ``people.Assignment`` suggests any other
rhythm (a contract's ``term_months`` is how long the appointment runs, not how often it is reviewed), so
HR opens one cycle a year and opens an ``Appraisal`` within it for whoever is due one. 360-degree or peer
feedback is out of scope (see the pull request).
"""

from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class AppraisalCycle(TimeStampedModel):
    name = models.CharField(max_length=80)
    year = models.PositiveSmallIntegerField()
    starts = models.DateField()
    ends = models.DateField()
    is_open = models.BooleanField(default=False)

    class Meta:
        unique_together = [("name", "year")]
        ordering = ["-year", "name"]

    def __str__(self) -> str:
        return f"{self.name} {self.year}"


class Goal(TimeStampedModel):
    """One objective set for an employee within a cycle: plain enough to weigh and track, nothing more."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        ACHIEVED = "achieved", "Achieved"
        NOT_ACHIEVED = "not_achieved", "Not achieved"

    employee = models.ForeignKey("people.Employee", on_delete=models.CASCADE, related_name="goals")
    cycle = models.ForeignKey(AppraisalCycle, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    weight = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Out of 100, when goals for the cycle are weighted"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["cycle", "employee", "position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(weight__isnull=True) | Q(weight__gte=0, weight__lte=100),
                name="goal_weight_nought_to_hundred",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.employee})"


class Appraisal(TimeStampedModel):
    """One employee's review within one cycle: self-assessment, then the manager's, then signed off.

    States and the actions that move between them are ``performance.workflow.APPRAISAL`` (the shared
    approvals engine, item 1.33), the same way ``leave.LeaveRequest`` and ``recruitment.Application`` are
    driven. ``manager`` is fixed when the appraisal is opened (``people.services.manager_of`` at that
    moment): a later transfer does not retroactively move who rates a cycle already under way.
    """

    class Kind(models.TextChoices):
        PROBATION = "probation", "Probation review"
        ANNUAL = "annual", "Annual appraisal"

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        SELF_ASSESSED = "self_assessed", "Self-assessment done"
        RATED = "rated", "Supervisor rated"
        SIGNED = "signed", "Signed off"

    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="appraisals")
    manager = models.ForeignKey(
        "people.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Who rates it: the employee's manager when the appraisal was opened",
    )
    cycle = models.ForeignKey(AppraisalCycle, on_delete=models.PROTECT, related_name="appraisals")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ANNUAL)
    state = models.CharField(max_length=20, choices=State.choices, default=State.DRAFT)
    previous_state = models.CharField(max_length=20, blank=True)  # read by approvals.engine
    decision_comment = models.TextField(blank=True)
    waiting_since = models.DateTimeField(null=True, blank=True)
    self_assessment = models.TextField(blank=True, help_text="The employee's own account of the cycle")
    self_assessed_at = models.DateTimeField(null=True, blank=True)
    manager_assessment = models.TextField(blank=True, help_text="The manager's assessment and comments")
    overall_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=60, blank=True)  # confirmed, increment, extend_probation, ...
    form_data = models.JSONField(default=dict, blank=True, help_text="Anything else particular to the form")

    class Meta:
        unique_together = [("employee", "cycle", "kind")]
        ordering = ["-cycle__year", "employee"]
        constraints = [
            models.CheckConstraint(
                condition=Q(overall_rating__isnull=True) | Q(overall_rating__gte=1, overall_rating__lte=5),
                name="appraisal_rating_one_to_five",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} {self.cycle} ({self.state})"
