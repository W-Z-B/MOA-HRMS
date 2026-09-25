"""F02 Employee records, F03 Contracts and appointments, F04 Documents."""

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import Func, Q

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class Employee(TimeStampedModel):
    class Gender(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"
        OTHER = "X", "Other or not stated"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        SUSPENDED = "suspended", "Suspended"
        SEPARATED = "separated", "Separated"

    employee_no = models.CharField(max_length=20, unique=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee"
    )
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    other_names = models.CharField(max_length=120, blank=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=Gender.choices, default=Gender.OTHER)
    # Sensitive identifiers: encrypted at rest, masked in list responses, reveal is audited.
    national_id = EncryptedTextField(null=True, blank=True)
    nis_no = EncryptedTextField(null=True, blank=True)
    tin = EncryptedTextField(null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    next_of_kin_name = models.CharField(max_length=120, blank=True)
    next_of_kin_phone = models.CharField(max_length=40, blank=True)
    campus = models.ForeignKey("org.Campus", on_delete=models.PROTECT, related_name="employees")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["campus", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee_no} {self.first_name} {self.last_name}"

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.other_names, self.last_name) if p)

    @property
    def current_assignment(self):
        return (
            self.assignments.filter(status=Assignment.Status.ACTIVE, is_acting=False)
            .order_by("-start_date")
            .first()
        )


class DateRange(Func):
    function = "DATERANGE"
    output_field = DateRangeField()


class Assignment(TimeStampedModel):
    """Links an employee to a position for a period. The constraint keeps one substantive holder per post."""

    class AppointmentType(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        CONTRACT = "contract", "Contract"
        TEMPORARY = "temporary", "Temporary"
        SESSIONAL = "sessional", "Sessional lecturer or instructor"
        SEASONAL = "seasonal", "Seasonal farm or estate worker"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="assignments")
    position = models.ForeignKey("org.Position", on_delete=models.PROTECT, related_name="assignments")
    appointment_type = models.CharField(max_length=20, choices=AppointmentType.choices)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    probation_end = models.DateField(null=True, blank=True)
    is_acting = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            ExclusionConstraint(
                name="one_substantive_holder_per_position",
                expressions=[
                    ("position", RangeOperators.EQUAL),
                    (
                        DateRange(
                            "start_date",
                            "end_date",
                            RangeBoundary(inclusive_lower=True, inclusive_upper=True),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(is_acting=False),
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="assignment_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} at {self.position} from {self.start_date:%d/%m/%Y}"


class Contract(TimeStampedModel):
    class ContractType(models.TextChoices):
        FIXED_TERM = "fixed_term", "Fixed term"
        OPEN_ENDED = "open_ended", "Open ended"
        SESSIONAL = "sessional", "Sessional"

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="contracts")
    contract_type = models.CharField(max_length=20, choices=ContractType.choices)
    term_months = models.PositiveSmallIntegerField(null=True, blank=True)
    signed_on = models.DateField(null=True, blank=True)
    document = models.ForeignKey("people.Document", null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self) -> str:
        return f"{self.get_contract_type_display()} for {self.assignment}"


class Document(TimeStampedModel):
    class Classification(models.TextChoices):
        INTERNAL = "internal", "Internal"
        CONFIDENTIAL = "confidential", "Confidential"
        MEDICAL = "medical", "Medical (restricted)"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=40)  # contract, certificate, letter, id_copy, medical, other
    title = models.CharField(max_length=160)
    file = models.FileField(upload_to="employees/%Y/%m/")
    version = models.PositiveSmallIntegerField(default=1)
    classification = models.CharField(
        max_length=20, choices=Classification.choices, default=Classification.INTERNAL
    )
    retention_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"
