"""F02 Employee records, F03 Contracts and appointments, F04 Documents."""

from pathlib import PurePath

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import Func, Q

from core.fields import EncryptedTextField
from core.models import TimeStampedModel
from core.uploads import stored_name


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
    # Next of kin and other people to call are EmergencyContact rows (people.EmergencyContact).
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
    # The grade and step this person is paid on in the post: an increment moves it up a step. Empty means
    # the post's own grade (item 1.11).
    grade = models.ForeignKey("org.Grade", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    confirmed_on = models.DateField(null=True, blank=True, help_text="Confirmed in the post after probation")

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

    @property
    def pay_grade(self):
        """The grade and step this person is paid on: their own after an increment, else the post's."""
        return self.grade or self.position.grade


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
    # Terms written into the contract. Leave and sick-day entitlements are rows in leave.Entitlement.
    hours_per_week = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="GYD per hour. Leave empty for salaried staff: the rate is then worked out from the grade",
    )
    notice_period_days = models.PositiveSmallIntegerField(null=True, blank=True)
    other_terms = models.TextField(blank=True, help_text="Allowances, duties or conditions particular to it")

    class Meta:
        ordering = [models.F("signed_on").desc(nulls_last=True), "-id"]

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
    # Stored under a random name (core.uploads.stored_name); the name the person chose is kept below.
    file = models.FileField(upload_to=stored_name)
    original_name = models.CharField(max_length=255, blank=True, help_text="File name as uploaded")
    version = models.PositiveSmallIntegerField(default=1)
    classification = models.CharField(
        max_length=20, choices=Classification.choices, default=Classification.INTERNAL
    )
    retention_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"

    def save(self, *args, **kwargs):
        if self.file and not getattr(self.file, "_committed", True) and not self.original_name:
            self.original_name = PurePath(self.file.name).name[:255]
        super().save(*args, **kwargs)

    @property
    def download_name(self) -> str:
        return self.original_name or (self.file.name.rsplit("/", 1)[-1] if self.file else "")


class Qualification(TimeStampedModel):
    """Education and professional qualifications, checked against the original by HR (item 1.06)."""

    class Level(models.TextChoices):
        CERTIFICATE = "certificate", "Certificate"
        DIPLOMA = "diploma", "Diploma"
        ASSOCIATE = "associate", "Associate degree"
        BACHELOR = "bachelor", "Bachelor's degree"
        POSTGRADUATE = "postgraduate", "Postgraduate diploma or certificate"
        MASTER = "master", "Master's degree"
        DOCTORATE = "doctorate", "Doctorate"
        PROFESSIONAL = "professional", "Professional qualification or licence"
        OTHER = "other", "Other"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="qualifications")
    level = models.CharField(max_length=20, choices=Level.choices)
    title = models.CharField(max_length=160, help_text="As on the certificate, for example BSc Agriculture")
    institution = models.CharField(max_length=160)
    country = models.CharField(max_length=80, default="Guyana")
    year_awarded = models.PositiveSmallIntegerField(null=True, blank=True)
    verified_on = models.DateField(null=True, blank=True, help_text="When HR saw the original")
    document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = [models.F("year_awarded").desc(nulls_last=True), "title"]

    def __str__(self) -> str:
        return f"{self.title}, {self.institution}"


class PreviousEmployment(TimeStampedModel):
    """Work before GSA, as declared on appointment (item 1.06)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="previous_employment")
    employer = models.CharField(max_length=160)
    position = models.CharField(max_length=160)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    reason_for_leaving = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="previous_employment_end_after_start",
            )
        ]

    def __str__(self) -> str:
        return f"{self.position}, {self.employer}"


class Dependant(TimeStampedModel):
    """Children and others who depend on the employee. The date of birth is kept only because the
    child tax deduction and medical schemes depend on age (item 1.06)."""

    class Relationship(models.TextChoices):
        CHILD = "child", "Child"
        SPOUSE = "spouse", "Spouse or partner"
        PARENT = "parent", "Parent"
        OTHER = "other", "Other"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="dependants")
    name = models.CharField(max_length=160)
    relationship = models.CharField(max_length=10, choices=Relationship.choices)
    date_of_birth = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["relationship", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_relationship_display()})"


class EmergencyContact(TimeStampedModel):
    """Who to call, in order. Replaces the single next-of-kin pair on the employee (item 1.06)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="emergency_contacts")
    name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=60, blank=True)
    phone = models.CharField(max_length=40)
    alternate_phone = models.CharField(max_length=40, blank=True)
    priority = models.PositiveSmallIntegerField(default=1, help_text="1 is called first")

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self) -> str:
        return f"{self.name}, {self.phone}"


class BankAccount(TimeStampedModel):
    """Where pay goes. A financial record, which the Data Protection Act treats as sensitive.

    A change takes effect only when a second person approves it (item 1.07): proposed (pending), then
    active, which supersedes the account before it. The employee is told every time it changes.
    """

    class State(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        ACTIVE = "active", "In use"
        SUPERSEDED = "superseded", "Replaced"
        REJECTED = "rejected", "Not approved"

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="bank_accounts")
    bank_name = models.CharField(max_length=120)
    branch = models.CharField(max_length=120, blank=True)
    account_name = models.CharField(max_length=160, help_text="As the bank holds it")
    account_number = EncryptedTextField()
    account_number_last4 = models.CharField(max_length=4, help_text="Shown instead of the number")
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    effective_from = models.DateField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"], condition=Q(state="active"), name="one_active_bank_account"
            ),
            models.UniqueConstraint(
                fields=["employee"], condition=Q(state="pending"), name="one_pending_bank_account"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bank_name} ending {self.account_number_last4} ({self.state})"


class CareerEvent(TimeStampedModel):
    """A change in someone's career, recorded as one event with its reason (item 1.11).

    Transfers, promotions, increments, acting appointments and confirmations change appointments only through
    an event, so the file tells the story. An event dated today or earlier takes effect when it is recorded;
    a later one is scheduled and takes effect on its day, or is held up, with the reason, if it no longer can.
    """

    class Kind(models.TextChoices):
        TRANSFER = "transfer", "Transfer"
        PROMOTION = "promotion", "Promotion"
        INCREMENT = "increment", "Increment"
        ACTING = "acting", "Acting appointment"
        CONFIRMATION = "confirmation", "Confirmation in the post"

    class State(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        APPLIED = "applied", "In effect"
        CANCELLED = "cancelled", "Cancelled"
        BLOCKED = "blocked", "Held up"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="career_events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    state = models.CharField(max_length=10, choices=State.choices, default=State.SCHEDULED)
    effective_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="When an acting appointment ends")
    from_assignment = models.ForeignKey(
        Assignment, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_assignment = models.ForeignKey(
        Assignment, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_position = models.ForeignKey(
        "org.Position", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    from_grade = models.ForeignKey(
        "org.Grade", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    to_grade = models.ForeignKey(
        "org.Grade", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.CharField(max_length=300)
    applied_at = models.DateTimeField(null=True, blank=True)
    problem = models.CharField(
        max_length=300, blank=True, help_text="Why a scheduled change could not take effect"
    )

    class Meta:
        ordering = ["-effective_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("effective_date")),
                name="career_event_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} of {self.employee} from {self.effective_date:%d/%m/%Y}"


class Separation(TimeStampedModel):
    """Someone leaving the School (item 1.12): why, when notice was given, the last day, what is owed (1.14).

    Recorded ahead of the last day, it waits as "leaving"; the night after the last day the person is marked
    as having left, their appointments end, changes still scheduled are cancelled and their account is
    switched off (item 1.13). The settlement figures are kept as they stood on completion.
    """

    class Reason(models.TextChoices):
        RESIGNATION = "resignation", "Resignation"
        RETIREMENT = "retirement", "Retirement"
        CONTRACT_END = "contract_end", "End of a fixed-term contract"
        NOTICE = "notice", "Ended by the School with notice"
        REDUNDANCY = "redundancy", "Redundancy"
        DISMISSAL = "dismissal", "Dismissal for good and sufficient cause"
        MUTUAL = "mutual", "Mutual consent"
        PROBATION = "probation", "Ended during probation"
        DEATH = "death", "Death in service"

    class State(models.TextChoices):
        LEAVING = "leaving", "Leaving"
        LEFT = "left", "Left"
        WITHDRAWN = "withdrawn", "Withdrawn"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="separations")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    state = models.CharField(max_length=10, choices=State.choices, default=State.LEAVING)
    notice_given_on = models.DateField(
        null=True, blank=True, help_text="When notice was given, by either side"
    )
    last_day = models.DateField()
    note = models.CharField(max_length=300, help_text="In words: why, and anything agreed")
    completed_at = models.DateTimeField(null=True, blank=True)
    withdrawn_reason = models.CharField(max_length=300, blank=True)
    settlement = models.JSONField(
        null=True, blank=True, help_text="The figures as they stood when the person left"
    )

    class Meta:
        ordering = ["-last_day", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"], condition=Q(state="leaving"), name="one_leaving_at_a_time"
            ),
            models.CheckConstraint(
                condition=Q(notice_given_on__isnull=True) | Q(notice_given_on__lte=models.F("last_day")),
                name="notice_before_last_day",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} leaving on {self.last_day:%d/%m/%Y} ({self.get_reason_display()})"


class IssuedItem(TimeStampedModel):
    """Something the School has handed to a member of staff, to be given back when they leave (item 1.17)."""

    class Kind(models.TextChoices):
        KEY = "key", "Key"
        TOOL = "tool", "Tool or equipment"
        DEVICE = "device", "Computer, phone or other device"
        UNIFORM = "uniform", "Uniform"
        PROTECTIVE = "protective", "Protective clothing or gear"
        CARD = "card", "Identity or access card"
        VEHICLE = "vehicle", "Vehicle"
        BOOK = "book", "Book or manual"
        OTHER = "other", "Other"

    class Condition(models.TextChoices):
        GOOD = "good", "In good order"
        WORN = "worn", "Worn with use"
        DAMAGED = "damaged", "Damaged"
        LOST = "lost", "Lost"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="issued_items")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=160)
    tag = models.CharField(max_length=60, blank=True, help_text="Serial number or asset tag")
    issued_on = models.DateField()
    returned_on = models.DateField(null=True, blank=True)
    condition = models.CharField(max_length=10, choices=Condition.choices, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = [models.F("returned_on").asc(nulls_first=True), "-issued_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(returned_on__isnull=True) | Q(returned_on__gte=models.F("issued_on")),
                name="item_returned_after_issue",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.description} issued to {self.employee} on {self.issued_on:%d/%m/%Y}"


class ClearanceStep(TimeStampedModel):
    """One step in clearing someone who is leaving (item 1.13): done, not needed, or still open."""

    class State(models.TextChoices):
        OPEN = "open", "To do"
        DONE = "done", "Done"
        NOT_NEEDED = "not_needed", "Not needed"

    separation = models.ForeignKey(Separation, on_delete=models.CASCADE, related_name="clearance")
    code = models.SlugField(max_length=30)
    label = models.CharField(max_length=160)
    who = models.CharField(max_length=120, help_text="Who confirms it")
    state = models.CharField(max_length=12, choices=State.choices, default=State.OPEN)
    note = models.CharField(max_length=300, blank=True)
    cleared_at = models.DateTimeField(null=True, blank=True)
    cleared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["separation", "position"]
        constraints = [models.UniqueConstraint(fields=["separation", "code"], name="one_step_of_each_kind")]

    def __str__(self) -> str:
        return f"{self.label} ({self.get_state_display()})"


class ExitInterview(TimeStampedModel):
    """What someone leaving said about their time at the School (item 1.13). Held to HR and the Principal."""

    class MainReason(models.TextChoices):
        PAY = "pay", "Pay and benefits"
        GROWTH = "growth", "Training and promotion"
        WORKLOAD = "workload", "Workload"
        MANAGEMENT = "management", "Supervision and management"
        CONDITIONS = "conditions", "Working conditions"
        MOVING = "moving", "Moving away"
        FAMILY = "family", "Personal or family reasons"
        RETIREMENT = "retirement", "Retirement"
        OTHER = "other", "Something else"

    class Recommend(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        UNSURE = "unsure", "Not sure"

    separation = models.OneToOneField(Separation, on_delete=models.CASCADE, related_name="exit_interview")
    held_on = models.DateField()
    declined = models.BooleanField(default=False, help_text="Offered, and declined")
    main_reason = models.CharField(max_length=20, choices=MainReason.choices, blank=True)
    would_recommend = models.CharField(max_length=10, choices=Recommend.choices, blank=True)
    # Ratings from 1 (poor) to 5 (very good); empty when not answered.
    rating_pay = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_supervision = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_training = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_workload = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_conditions = models.PositiveSmallIntegerField(null=True, blank=True)
    keep = models.TextField(blank=True, help_text="What the School should keep")
    change = models.TextField(blank=True, help_text="What the School should change")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(rating_pay__isnull=True) | Q(rating_pay__gte=1, rating_pay__lte=5))
                    & (
                        Q(rating_supervision__isnull=True)
                        | Q(rating_supervision__gte=1, rating_supervision__lte=5)
                    )
                    & (Q(rating_training__isnull=True) | Q(rating_training__gte=1, rating_training__lte=5))
                    & (Q(rating_workload__isnull=True) | Q(rating_workload__gte=1, rating_workload__lte=5))
                    & (
                        Q(rating_conditions__isnull=True)
                        | Q(rating_conditions__gte=1, rating_conditions__lte=5)
                    )
                ),
                name="exit_ratings_one_to_five",
            ),
        ]

    def __str__(self) -> str:
        return f"Exit interview with {self.separation.employee} on {self.held_on:%d/%m/%Y}"
