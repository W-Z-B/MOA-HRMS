"""Email the people a candidate and an interview concern. Synchronous, like notifications.services.notify
(no Procrastinate task for this phase: nothing here is a recurring or long-running job)."""

import logging
from uuid import uuid4

from django.conf import settings
from django.core.mail import EmailMessage

from recruitment import ics

log = logging.getLogger(__name__)


def _send(
    *, to: list[str], subject: str, body: str, attachment: tuple[str, bytes, str] | None = None
) -> bool:
    if not to:
        return False
    message = EmailMessage(f"[GSA HRMS] {subject}", body, settings.DEFAULT_FROM_EMAIL, to)
    if attachment:
        message.attach(*attachment)
    try:
        return message.send() > 0
    except Exception:  # noqa: BLE001 - mail failure must never break the business transaction
        log.exception("recruitment email to %s failed", to)
        return False


def send_submission_receipt(application) -> bool:
    """Tells the candidate their reference and check code, the only way they can follow their application."""
    candidate = application.candidate
    body = "\n\n".join(
        [
            f"Dear {candidate.first_name},",
            f"Thank you for your application to the Guyana School of Agriculture for "
            f"{application.vacancy.title}.",
            f"Your reference is {application.reference}.",
            "Keep this email: you will need the reference, and the code below, to check your application's "
            "progress without needing an account.",
            f"Code: {application.check_code}",
            f"Check your status at {settings.PUBLIC_URL}/#/apply-status",
        ]
    )
    sent = _send(to=[candidate.email], subject="Your application", body=body)
    return sent


def send_interview_invite(interview, *, cancelled: bool = False) -> bool:
    """A calendar invite (or cancellation) to the candidate and the interviewer, by email (item H-W01)."""
    application = interview.application
    candidate = application.candidate
    summary = f"Interview: {application.vacancy.title}"
    description = (
        f"Interview for {application.vacancy.title} with {candidate.full_name}."
        if cancelled is False
        else f"Cancelled: interview for {application.vacancy.title} with {candidate.full_name}."
    )
    interviewer = interview.interviewer
    interviewer_email = interviewer.email or (interviewer.user.email if interviewer.user else "")
    attendees = [address for address in (candidate.email, interviewer_email) if address]
    attachment = (
        "invite.ics",
        ics.build_invite(
            uid=interview.ics_uid,
            sequence=interview.sequence,
            summary=summary,
            description=description,
            location=interview.location,
            starts_at=interview.starts_at,
            ends_at=interview.ends_at,
            organizer_email=settings.DEFAULT_FROM_EMAIL,
            attendee_emails=attendees,
            cancelled=cancelled,
        ),
        "text/calendar; method=" + ("CANCEL" if cancelled else "REQUEST"),
    )
    verb = "cancelled" if cancelled else "scheduled"
    when = f"{interview.starts_at:%A %d %B %Y, %H:%M} to {interview.ends_at:%H:%M}"
    candidate_body = "\n\n".join(
        [
            f"Dear {candidate.full_name},",
            f"Your interview for {application.vacancy.title} has been {verb}: {when}"
            + (f" at {interview.location}." if interview.location else "."),
            f"Your application reference is {application.reference}.",
        ]
    )
    interviewer_body = "\n\n".join(
        [
            f"Interview with {candidate.full_name} for {application.vacancy.title} has been {verb}: {when}"
            + (f" at {interview.location}." if interview.location else "."),
        ]
    )
    sent_candidate = _send(
        to=[candidate.email], subject=f"Interview {verb}", body=candidate_body, attachment=attachment
    )
    sent_interviewer = _send(
        to=[interviewer_email] if interviewer_email else [],
        subject=f"Interview {verb}",
        body=interviewer_body,
        attachment=attachment,
    )
    return sent_candidate or sent_interviewer


def new_ics_uid():
    return uuid4()
