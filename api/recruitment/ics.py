"""A minimal RFC 5545 VEVENT, built with the standard library only (the build plan's own instruction:
no third-party calendar package, no Google Calendar integration). Good enough for a mail client to offer
"add to calendar"; nothing here claims full iCalendar coverage.
"""

from datetime import UTC, datetime
from uuid import UUID

FOLD_AT = 73  # RFC 5545 §3.1: lines over 75 octets are folded; stay comfortably under it


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _stamp(value: datetime) -> str:
    """UTC, as Zulu time, which needs no VTIMEZONE block."""
    return value.strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    if len(line) <= FOLD_AT:
        return line
    parts = [line[:FOLD_AT]]
    rest = line[FOLD_AT:]
    while rest:
        parts.append(" " + rest[:FOLD_AT])
        rest = rest[FOLD_AT:]
    return "\r\n".join(parts)


def build_invite(
    *,
    uid: UUID,
    sequence: int,
    summary: str,
    description: str,
    location: str,
    starts_at: datetime,
    ends_at: datetime,
    organizer_email: str,
    attendee_emails: list[str],
    cancelled: bool = False,
) -> bytes:
    """A single-event .ics, UTC throughout. ``uid`` and an incremented ``sequence`` let a reschedule or a
    cancellation update the same entry in a calendar app rather than add a new one."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GSA HRMS//Recruitment//EN",
        "METHOD:CANCEL" if cancelled else "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_stamp(datetime.now(UTC))}",
        f"DTSTART:{_stamp(starts_at)}",
        f"DTEND:{_stamp(ends_at)}",
        f"SEQUENCE:{sequence}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"LOCATION:{_escape(location)}",
        f"ORGANIZER:mailto:{organizer_email}",
        *(f"ATTENDEE:mailto:{address}" for address in attendee_emails),
        "STATUS:CANCELLED" if cancelled else "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode("utf-8")
