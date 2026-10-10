"""H-W01 (Phase B): recruitment and hiring, built on top of Phase A (attendance, payroll).

Scope for this phase, narrowed from the earlier scoping pass (``GSA-HRMS-Interview-System-Build-Plan.md``):
a vacancy against an approved post, a candidate's application tracked through to a decision, one interview
per application with no double-booking, and a bare hire record for the next phase's onboarding build
(H-W02) to pick up. Panels, structured scoring, a separate Offer model, the reporting dashboard and the
retention job the build plan also describes are deferred — see the pull request for why.

Candidates are not users of this system (the build plan's own default, repeated here: "Applicants are not
users; only staff authenticate"). A candidate checks their application's progress the way anyone checks a
letter is genuine (item 1.47, ``letters.checking``): a reference and a code, typed in without signing in.
"""

import uuid
from datetime import timedelta
from pathlib import PurePath

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import Func
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


def _candidate_file_name(instance, filename: str) -> str:
    """Like ``core.uploads.stored_name``, but under its own prefix: a candidate is not an employee, and
    this path is never confused with the personnel file volume it shares (the same random-name, no
    original-name-on-disk rule applies: item 1.46's "a file name never carries a person's details")."""
    extension = PurePath(filename).suffix.lower()[:10]
    now = timezone.now()
    return f"recruitment/candidates/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"


class Vacancy(TimeStampedModel):
    """An advertised vacancy against one approved post on the establishment (``org.Position``).

    The post already carries its grade and its unit's campus, so neither is duplicated here (the task's
    "post, grade, campus" is read off ``position.grade`` and ``position.org_unit.campus``).
    """

    class State(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    position = models.ForeignKey("org.Position", on_delete=models.PROTECT, related_name="vacancies")
    title = models.CharField(max_length=160, help_text="As advertised; defaults to the post's title")
    description = models.TextField(blank=True, help_text="Duties, requirements and how to apply")
    opens_on = models.DateField()
    closes_on = models.DateField()
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN)

    class Meta:
        verbose_name_plural = "vacancies"
        ordering = ["-opens_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(closes_on__gte=models.F("opens_on")), name="vacancy_closes_after_opens"
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_state_display()})"

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.position.title
        super().save(*args, **kwargs)

    @property
    def is_open(self) -> bool:
        today = timezone.localdate()
        return self.state == self.State.OPEN and self.opens_on <= today <= self.closes_on


class Candidate(TimeStampedModel):
    """A person applying for a post. Kept apart from ``people.Employee`` until a hire is decided.

    ``national_id`` is encrypted at rest and masked outside the roles in ``recruitment.permissions.SEES_PII``,
    the same treatment ``people.Employee`` gives the same kind of number (decision in the pull request).
    """

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    national_id = EncryptedTextField(null=True, blank=True)
    cv = models.FileField(upload_to=_candidate_file_name, null=True, blank=True)
    cv_original_name = models.CharField(max_length=255, blank=True, help_text="File name as uploaded")
    # Data Protection Act 2023: an unsuccessful candidate's record is not kept indefinitely. The date is
    # set when an application is decided (recruitment.workflow); no job acts on it yet (see pull request).
    retention_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if self.cv and not getattr(self.cv, "_committed", True) and not self.cv_original_name:
            self.cv_original_name = PurePath(self.cv.name).name[:255]
        super().save(*args, **kwargs)

    @property
    def cv_download_name(self) -> str:
        return self.cv_original_name or (self.cv.name.rsplit("/", 1)[-1] if self.cv else "")


def _new_reference() -> str:
    from recruitment.reference import new_reference

    return new_reference()


def _new_check_code() -> str:
    from recruitment.reference import new_code

    return new_code()


class Application(TimeStampedModel):
    """One candidate's application to one vacancy, carried through to a decision.

    States and the actions that move between them are ``recruitment.workflow.APPLICATION`` (the shared
    approvals engine, item 1.33). HR records every step: a candidate has no account to act for themself.
    """

    class State(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Interview scheduled"
        INTERVIEWED = "interviewed", "Interviewed"
        OFFERED = "offered", "Offered"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    OPEN_STATES = (
        State.SUBMITTED,
        State.SHORTLISTED,
        State.INTERVIEW_SCHEDULED,
        State.INTERVIEWED,
        State.OFFERED,
    )
    CLOSED_STATES = (State.ACCEPTED, State.DECLINED, State.REJECTED, State.WITHDRAWN)

    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, related_name="applications")
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="applications")
    # How the candidate reached HR, until Open Question 4 (a public form) is revisited: email, paper, etc.
    source = models.CharField(max_length=40, blank=True)
    state = models.CharField(max_length=24, choices=State.choices, default=State.SUBMITTED)
    previous_state = models.CharField(max_length=24, blank=True)  # read by approvals.engine
    decision_comment = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text="Screening and shortlisting notes")
    # A one-use pair a candidate keeps to check progress without an account (mirrors letters.checking).
    reference = models.CharField(max_length=20, unique=True, default=_new_reference)
    check_code = EncryptedTextField(null=True, blank=True, default=_new_check_code)

    class Meta:
        unique_together = [("vacancy", "candidate")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.candidate} for {self.vacancy} ({self.get_state_display()})"


class ApplicationCheckLog(models.Model):
    """One use of the status-check page (mirrors ``letters.LetterCheck``), for its own rate limit."""

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    reference = models.CharField(max_length=40)
    application = models.ForeignKey(
        Application, null=True, blank=True, on_delete=models.CASCADE, related_name="checks"
    )
    matched = models.BooleanField()
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.reference} checked at {self.at:%d/%m/%Y %H:%M}"


class DateTimeRange(Func):
    """``TSTZRANGE(starts_at, ends_at)``, used only by the exclusion constraint below. Same device as
    ``people.models.DateRange``, which keeps one substantive holder per post with a ``DATERANGE``."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Interview(TimeStampedModel):
    """One interview for one application, with one interviewer.

    The task calls for "no double-booking" on interviewer and time range; a panel of several interviewers
    per slot is outside this phase's scope (see the pull request), so the exclusion constraint below is
    enough on its own, with no panel-membership table behind it.
    """

    class State(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="interview")
    interviewer = models.ForeignKey(
        "people.Employee", on_delete=models.PROTECT, related_name="recruitment_interviews"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text="A room, or a link supplied by GSA; no video service is wired up",
    )
    state = models.CharField(max_length=10, choices=State.choices, default=State.SCHEDULED)
    # A stable identity for the .ics VEVENT, so a reschedule updates the same entry in the interviewer's
    # and candidate's calendars instead of leaving a stale one (RFC 5545's UID and SEQUENCE).
    ics_uid = models.UUIDField(unique=True, editable=False)
    sequence = models.PositiveSmallIntegerField(default=0)
    invited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            ExclusionConstraint(
                name="no_double_booking_per_interviewer",
                expressions=[
                    ("interviewer", RangeOperators.EQUAL),
                    (
                        DateTimeRange(
                            "starts_at", "ends_at", RangeBoundary(inclusive_lower=True, inclusive_upper=False)
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=models.Q(state="scheduled"),  # Interview.State.SCHEDULED: not in scope in Meta
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")), name="interview_ends_after_starts"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.application} with {self.interviewer} at {self.starts_at:%d/%m/%Y %H:%M}"

    @staticmethod
    def default_ends_at(starts_at):
        return starts_at + timedelta(minutes=settings.RECRUITMENT_DEFAULT_INTERVIEW_MINUTES)


class Hire(TimeStampedModel):
    """The bare record a decided offer leaves behind (H-W01's end): who, for what post, from when.

    Onboarding itself (H-W02) is a later phase. ``employee`` is left for that build to fill in once it
    turns this hire into a staff record; nothing here creates one.
    """

    application = models.OneToOneField(Application, on_delete=models.PROTECT, related_name="hire")
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, related_name="hires")
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="hires")
    start_date = models.DateField(null=True, blank=True, help_text="Expected or agreed start date")
    employee = models.ForeignKey(
        "people.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Set by onboarding (H-W02) once this hire becomes a staff record",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Hire of {self.candidate} into {self.vacancy}"
