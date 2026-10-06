"""F09 Training and development (Release 2). Scaffold: training records with certification expiry."""

from django.db import models

from core.models import TimeStampedModel


class TrainingRecord(TimeStampedModel):
    employee = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="training")
    course = models.CharField(max_length=160)
    provider = models.CharField(max_length=120, blank=True)
    starts = models.DateField()
    ends = models.DateField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    certification = models.CharField(max_length=160, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    bond_months = models.PositiveSmallIntegerField(null=True, blank=True)
    external_ref = models.CharField(
        max_length=120, null=True, blank=True, unique=True, help_text="Set when reported by the LMS"
    )

    class Meta:
        ordering = ["-starts"]

    def __str__(self) -> str:
        return f"{self.employee} {self.course}"


class TrainingRequirement(TimeStampedModel):
    """Training that staff must take, by post, unit and campus (item 5.24; LMS decision D13, ADR 0019).

    The HRMS owns the requirement; the LMS reads it (integration scope training:read), enrols the people,
    reminds them and reports each completion back to the training record. Each condition left empty
    applies to everyone; those filled in must all hold. Retired, not deleted, so the history stays.
    """

    course_code = models.CharField(
        max_length=40, blank=True, help_text="The course's code in the LMS, when it has one"
    )
    title = models.CharField(max_length=160, help_text="The course as staff know it")
    post_title = models.CharField(
        max_length=120,
        blank=True,
        help_text="Staff holding a post with this title (any unit), compared without regard to case",
    )
    org_unit = models.ForeignKey(
        "org.OrgUnit", null=True, blank=True, on_delete=models.PROTECT, related_name="training_requirements"
    )
    campus = models.ForeignKey(
        "org.Campus", null=True, blank=True, on_delete=models.PROTECT, related_name="training_requirements"
    )
    due_days = models.PositiveSmallIntegerField(default=30, help_text="Days from assignment to the due date")
    renewal_months = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Taken again this often; empty means once"
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["title", "id"]

    def __str__(self) -> str:
        return f"{self.title} for {self.describe()}"

    def describe(self) -> str:
        parts = [
            f"post {self.post_title}" if self.post_title else "",
            f"unit {self.org_unit.code}" if self.org_unit_id else "",
            f"campus {self.campus.code}" if self.campus_id else "",
        ]
        return ", ".join(p for p in parts if p) or "all staff"
