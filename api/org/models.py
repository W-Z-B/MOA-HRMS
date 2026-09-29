"""F01 Organisation and establishment: campuses, units, grades, salary scales, positions."""

from django.db import models

from core.models import TimeStampedModel


class Campus(TimeStampedModel):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=80, blank=True)

    class Meta:
        verbose_name_plural = "campuses"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class OrgUnit(TimeStampedModel):
    class UnitType(models.TextChoices):
        DEPARTMENT = "department", "Department"
        FARM = "farm", "Farm"
        UNIT = "unit", "Unit"
        SECTION = "section", "Section"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    unit_type = models.CharField(max_length=20, choices=UnitType.choices, default=UnitType.DEPARTMENT)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name="units")
    head = models.ForeignKey(
        "people.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_units"
    )

    class Meta:
        ordering = ["campus", "code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class SalaryScale(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)

    def __str__(self) -> str:
        return self.code


class Grade(TimeStampedModel):
    """A grade and step with an effective-dated amount, so Finance can revise pay without a release."""

    scale = models.ForeignKey(SalaryScale, on_delete=models.PROTECT, related_name="grades")
    code = models.CharField(max_length=20)
    step = models.PositiveSmallIntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Monthly amount in GYD")
    effective_from = models.DateField()

    class Meta:
        unique_together = [("scale", "code", "step", "effective_from")]
        ordering = ["scale", "code", "step", "-effective_from"]

    def __str__(self) -> str:
        return f"{self.scale.code} {self.code}/{self.step}"


class Position(TimeStampedModel):
    """An approved establishment post. One active non-acting holder at a time (see people.Assignment)."""

    class Status(models.TextChoices):
        APPROVED = "approved", "Approved"
        FROZEN = "frozen", "Frozen"
        ABOLISHED = "abolished", "Abolished"

    number = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=120)
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="positions")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="positions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPROVED)
    fte = models.DecimalField(max_digits=4, decimal_places=2, default=1)

    class Meta:
        ordering = ["org_unit", "number"]

    def __str__(self) -> str:
        return f"{self.number} {self.title}"

    @property
    def is_vacant(self) -> bool:
        return not self.assignments.filter(is_acting=False, status="active").exists()
