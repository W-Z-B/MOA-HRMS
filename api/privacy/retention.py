"""The retention schedule applied (item 1.32): which records each rule says are due, and their disposal.

Records are disposed of only through a run that one person proposes and a second approves, except logs that
no one needs to review (sign-in attempts, notifications already read), which go every night. Each disposal is
written to the audit log with the rule that required it, so the record of what was destroyed outlives it.
"""

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, time

from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from audit.services import record, snapshot

log = logging.getLogger(__name__)

# code, name, months kept, counted from, automatic, note. The periods are the impact assessment's proposals.
RULES = [
    (
        "doctors-notes",
        "Doctor's notes and other medical evidence for leave",
        24,
        "the end of the leave they support",
        False,
        "Proposal in the impact assessment; GSA to confirm",
    ),
    (
        "leave-evidence",
        "Other evidence for leave, such as letters",
        24,
        "the end of the leave it supports",
        False,
        "Proposal; GSA to confirm",
    ),
    (
        "dated-documents",
        "Documents given a date to be kept until",
        None,
        "the date set on each document when it was filed",
        False,
        "The date HR sets when filing a document",
    ),
    (
        "sign-in-records",
        "Sign-in attempts and requests for a password link",
        12,
        "the attempt or the request",
        True,
        "Proposal in the impact assessment; GSA to confirm",
    ),
    (
        "read-notifications",
        "Notifications already read",
        24,
        "when they were read",
        True,
        "Proposal; GSA to confirm",
    ),
]
EVIDENCE_TYPES = {"doctors-notes": "medical", "leave-evidence": "leave_evidence"}


@dataclass
class Due:
    entity: str
    entity_id: int
    employee_id: int | None
    description: str
    due_since: date


def months_before(day: date, months: int) -> date:
    """The same day `months` months earlier, or the last day of that month when it is shorter."""
    month_index = day.year * 12 + day.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def months_after(day: date, months: int) -> date:
    return months_before(day, -months)


def due(rule, today: date | None = None) -> list[Due]:
    """The records that the rule says should go, as of today."""
    from people.models import Document

    today = today or timezone.localdate()
    if rule.code in EVIDENCE_TYPES:
        from leave.models import LeaveRequest

        cut = months_before(today, rule.keep_months)
        requests = (
            LeaveRequest.objects.filter(evidence__doc_type=EVIDENCE_TYPES[rule.code], to_date__lt=cut)
            .select_related("evidence", "employee", "leave_type")
            .order_by("to_date")
        )
        return [
            Due(
                "people.document",
                r.evidence_id,
                r.employee_id,
                f"{r.evidence.title} ({r.employee.employee_no} {r.employee.full_name})",
                months_after(r.to_date, rule.keep_months),
            )
            for r in requests
        ]
    if rule.code == "dated-documents":
        documents = (
            Document.objects.filter(retention_date__lt=today, leaverequest__isnull=True)
            .select_related("employee")
            .order_by("retention_date")
        )
        return [
            Due(
                "people.document",
                d.id,
                d.employee_id,
                f"{d.title}, version {d.version} ({d.employee.employee_no} {d.employee.full_name})",
                d.retention_date,
            )
            for d in documents
        ]
    return []


def still_due(item, rule, today: date) -> bool:
    return any(d.entity == item.entity and d.entity_id == item.entity_id for d in due(rule, today))


def dispose(request, item, rule) -> None:
    """Destroy one record named in an approved run, and record that it was, and why."""
    from people.models import Document

    if item.entity != "people.document":  # pragma: no cover - every reviewed rule names documents for now
        raise ValueError(f"No way to dispose of {item.entity}")
    document = Document.objects.filter(pk=item.entity_id).first()
    if document is not None:
        before = snapshot(document)
        if document.file:
            document.file.delete(save=False)
        document.delete()
        record(
            request,
            "disposed",
            document,
            before=before,
            entity_id=item.entity_id,
            reason=f"Retention schedule: {rule.name}",
        )
    item.disposed_at = timezone.now()
    item.save(update_fields=["disposed_at"])


def purge(today: date | None = None) -> dict[str, int]:
    """Every night: delete the logs that the automatic rules say are old enough. No review needed."""
    from iam.models import LoginAttempt, PasswordResetRequest
    from notifications.models import Notification
    from privacy.models import RetentionRule

    today = today or timezone.localdate()
    removed: dict[str, int] = {}
    for rule in RetentionRule.objects.filter(automatic=True, keep_months__isnull=False):
        cut = timezone.make_aware(datetime.combine(months_before(today, rule.keep_months), time.min))
        with transaction.atomic():
            if rule.code == "sign-in-records":
                count = LoginAttempt.objects.filter(at__lt=cut).delete()[0]
                count += PasswordResetRequest.objects.filter(at__lt=cut).delete()[0]
            elif rule.code == "read-notifications":
                count = Notification.objects.filter(read_at__lt=cut).delete()[0]
            else:  # pragma: no cover - a rule the code does not know is left alone
                continue
            removed[rule.code] = count
            if count:
                AuditLog.objects.create(
                    action="purged",
                    entity="privacy.retentionrule",
                    entity_id=rule.pk,
                    after={"rule": rule.code, "rows": count, "older_than": cut.date().isoformat()},
                    reason=f"Retention schedule: {rule.name}",
                )
    log.info("retention purge removed %s", removed)
    return removed
