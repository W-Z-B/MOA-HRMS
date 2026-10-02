"""Item 1.16: the accident and incident register for the farms, workshops and the processing unit.

The Occupational Safety and Health Act 1997 (Cap. 99:06) has the employer keep a register of accidents
(section 69(7)) and send written notice to the Occupational Safety and Health Authority, and to the safety and
health committee, representative or trade union if there is one: forthwith when an accident kills a worker,
within four days when it keeps a worker from earning full wages for more than one day (69(1)), forthwith of a
later death (69(2)), within two weeks of the day a disablement ended (69(3)), forthwith of a suspected
occupational disease (section 70), and within two days of a dangerous occurrence at an industrial
establishment that is not otherwise notifiable (section 74). incidents.duties works out which are due.

Anyone may report what happened. Human Resources keeps the register. What someone's injury was, how it was
treated and how long they were off work is health information, read only by Human Resources.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Incident(TimeStampedModel):
    class Kind(models.TextChoices):
        ACCIDENT = "accident", "Accident"
        NEAR_MISS = "near_miss", "Near miss"
        DANGEROUS = "dangerous", "Dangerous occurrence"
        DISEASE = "disease", "Occupational disease"

    class State(models.TextChoices):
        REPORTED = "reported", "Reported"
        INVESTIGATING = "investigating", "Being looked into"
        CLOSED = "closed", "Closed"

    reference = models.CharField(max_length=20, unique=True)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    occurred_at = models.DateTimeField(
        help_text="When it happened; for a disease, when it was first suspected"
    )
    campus = models.ForeignKey("org.Campus", on_delete=models.PROTECT, related_name="incidents")
    org_unit = models.ForeignKey(
        "org.OrgUnit", null=True, blank=True, on_delete=models.PROTECT, related_name="incidents"
    )
    place = models.CharField(max_length=120, help_text="Exactly where, such as the feed mill or pen 3")
    industrial = models.BooleanField(
        default=False, help_text="At an industrial establishment, such as the processing unit or a workshop"
    )
    description = models.TextField(help_text="What happened")
    immediate_action = models.TextField(blank=True, help_text="What was done at once")
    state = models.CharField(max_length=14, choices=State.choices, default=State.REPORTED)
    cause = models.TextField(blank=True, help_text="What the investigation found: why it happened")
    investigated_on = models.DateField(null=True, blank=True)
    investigated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    closed_on = models.DateField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self) -> str:
        return self.reference


class Person(TimeStampedModel):
    """Someone hurt or made ill. Only a member of staff is a worker the Act's notices are about."""

    class Who(models.TextChoices):
        STAFF = "staff", "Member of staff"
        STUDENT = "student", "Student"
        CONTRACTOR = "contractor", "Contractor"
        VISITOR = "visitor", "Visitor"

    class Treatment(models.TextChoices):
        NONE = "none", "None needed"
        FIRST_AID = "first_aid", "First aid"
        DOCTOR = "doctor", "Doctor or clinic"
        HOSPITAL = "hospital", "Hospital"

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="people")
    who = models.CharField(max_length=12, choices=Who.choices)
    employee = models.ForeignKey(
        "people.Employee", null=True, blank=True, on_delete=models.PROTECT, related_name="incident_injuries"
    )
    name = models.CharField(max_length=120, blank=True, help_text="Someone not on the staff")
    injury = models.TextField(blank=True, help_text="The injury or illness, and the part of the body")
    treatment = models.CharField(max_length=10, choices=Treatment.choices, blank=True)
    off_work_from = models.DateField(null=True, blank=True, help_text="First day unable to earn full wages")
    back_at_work_on = models.DateField(null=True, blank=True, help_text="First day back on full wages")
    died_on = models.DateField(null=True, blank=True)
    nis_form_on = models.DateField(
        null=True, blank=True, help_text="When they were given the NIS notice of accident (Form IB1)"
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(who="staff") & Q(employee__isnull=False))
                | (~Q(who="staff") & Q(employee__isnull=True) & ~Q(name="")),
                name="incident_person_named",
            ),
            models.UniqueConstraint(fields=["incident", "employee"], name="incident_staff_once"),
            models.CheckConstraint(
                condition=Q(back_at_work_on__isnull=True)
                | (Q(off_work_from__isnull=False) & Q(back_at_work_on__gt=models.F("off_work_from"))),
                name="incident_back_after_off",
            ),
        ]

    @property
    def display_name(self) -> str:
        return self.employee.full_name if self.employee_id else self.name

    def __str__(self) -> str:
        return f"{self.display_name} ({self.incident})"


class Notice(TimeStampedModel):
    """A written notice the Act requires, as sent: one row for each duty and each body told."""

    class Duty(models.TextChoices):
        DEATH = "death", "A worker killed"
        DISABLEMENT = "disablement", "A worker kept from full wages for more than a day"
        LATER_DEATH = "later_death", "A death after the notice of the accident"
        RECOVERED = "recovered", "The day the disablement ended"
        DISEASE = "disease", "A suspected occupational disease"
        DANGEROUS = "dangerous", "A dangerous occurrence"

    class Recipient(models.TextChoices):
        AUTHORITY = "authority", "The Occupational Safety and Health Authority"
        WORKERS = "workers", "The safety and health committee, representative or trade union"
        SANITARY = "sanitary", "The Local Sanitary Authority"
        MEDICAL = "medical", "The medical inspector for the area"

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="notices")
    person = models.ForeignKey(
        Person, null=True, blank=True, on_delete=models.CASCADE, related_name="notices"
    )
    duty = models.CharField(max_length=12, choices=Duty.choices)
    recipient = models.CharField(max_length=10, choices=Recipient.choices)
    sent_on = models.DateField()
    how = models.CharField(max_length=80, help_text="Such as by hand, by email or by registered post")
    their_reference = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["sent_on", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "person", "duty", "recipient"],
                nulls_distinct=False,
                name="incident_notice_once",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_duty_display()} to {self.get_recipient_display()} on {self.sent_on:%d/%m/%Y}"


class Action(TimeStampedModel):
    """What will be done so it does not happen again, by whom and by when."""

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="actions")
    what = models.TextField()
    owner = models.ForeignKey("people.Employee", on_delete=models.PROTECT, related_name="safety_actions")
    due_on = models.DateField()
    done_on = models.DateField(null=True, blank=True)
    done_note = models.TextField(blank=True)

    class Meta:
        ordering = ["due_on", "id"]

    def __str__(self) -> str:
        return f"{self.what[:40]} ({self.incident})"
