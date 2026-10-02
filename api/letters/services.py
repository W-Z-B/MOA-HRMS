"""Writing letters (item 1.19): what a letter would say, and issuing it into the staff file."""

import hashlib
from datetime import date

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from audit.services import record, snapshot
from letters import markup, pdf
from letters.fields import RECORD_FIELDS, long_date, record_values
from letters.models import Letter, LetterTemplate
from notifications.services import notify
from people.models import Document

REFERENCE_LOCK = 1_019_001  # one reference at a time (the audit chain holds its own lock)
ADDRESS_FIELDS = ("full_name", "post_title", "unit", "campus")  # on an addressed letter, under the date


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def current(code: str) -> LetterTemplate | None:
    """The newest version of a template, whether or not it is in use."""
    return LetterTemplate.objects.filter(code=code).order_by("-version").first()


def _asked(template: LetterTemplate, given: dict) -> dict[str, str]:
    """The answers to what the template asks, as words; a date that is not one reads as blank."""
    answers = {}
    for ask in template.asks:
        raw = str(given.get(ask["key"], "") or "").strip()
        if ask["type"] == "date":
            day = parse_date(raw) if raw else None
            answers[ask["key"]] = long_date(day) if day else ""
        else:
            answers[ask["key"]] = " ".join(raw.split())[:300]
    return answers


def draft(template: LetterTemplate, employee, given: dict, *, on: date, reference: str) -> dict:
    """What the letter would say: its subject, its blocks, the values it uses, and what is missing."""
    values = {**record_values(employee, on), **_asked(template, given), "reference": reference}
    used = markup.fields_in(template.subject, template.body)
    shown = used + [key for key in ADDRESS_FIELDS if template.addressed and key not in used]
    labels = {**RECORD_FIELDS, **{ask["key"]: ask["label"] for ask in template.asks}}
    asked = {ask["key"] for ask in template.asks}
    missing = [
        {"key": key, "label": labels.get(key, key), "asked": key in asked}
        for key in shown
        if not values.get(key)
    ]
    return {
        "subject": markup.fill(template.subject, values),
        "blocks": markup.merge(markup.parse(template.body), values),
        "values": {key: values[key] for key in shown},
        "missing": missing,
        "all_values": values,
    }


def _next_reference(year: int) -> str:
    prefix = f"{settings.LETTER_REFERENCE_PREFIX}/{year}/"
    last = (
        Letter.objects.filter(reference__startswith=prefix)
        .order_by("-id")
        .values_list("reference", flat=True)
        .first()
    )
    number = int(last.rsplit("/", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:04d}"


def _listed(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def missing_in_words(missing: list[dict]) -> str:
    """The refusal in words: what the staff record lacks, and what is still to answer."""
    lower = [m["label"][:1].lower() + m["label"][1:] for m in missing]
    from_record = [label for label, m in zip(lower, missing, strict=True) if not m["asked"]]
    asked = [label for label, m in zip(lower, missing, strict=True) if m["asked"]]
    parts = []
    if from_record:
        parts.append(f"the staff record has no {_listed(from_record)}")
    if asked:
        parts.append(f"still to answer: {_listed(asked)}")
    return f"The letter cannot be issued yet: {'; '.join(parts)}."


def issue(request, template: LetterTemplate, employee, given: dict, *, career_event=None, ask=None) -> Letter:
    """Issue the letter: a reference, the PDF in the staff file, its fingerprint, and word to the person."""
    from letters import checking
    from signing import services as signing

    if not template.is_active:
        raise Refused("retired", "That template is no longer in use.")
    if ask and signing.signer_of(employee) is None:
        raise Refused(
            "no_account",
            f"{employee.full_name} has no account to sign with. Issue the letter without asking, "
            "or open an account for them first.",
        )
    newest = current(template.code)
    if newest is not None and newest.pk != template.pk:
        raise Refused(
            "changed", "The template was changed since the letter was begun. Look at the letter again."
        )
    today = timezone.localdate()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [REFERENCE_LOCK])
        reference = _next_reference(today.year)
        letter = draft(template, employee, given, on=today, reference=reference)
        if letter["missing"]:
            raise Refused("missing", missing_in_words(letter["missing"]))
        code = checking.new_code()
        html_page = pdf.page(
            template=template,
            values=letter["all_values"],
            body_html=markup.to_html(letter["blocks"]),
            subject=letter["subject"],
            check_code=code,
        )
        content = pdf.render(html_page)
        document = Document.objects.create(
            employee=employee,
            doc_type="letter",
            title=f"{template.name}, {reference}",
            file=ContentFile(content, name=f"{reference.replace('/', '-')}.pdf"),
            classification=template.classification,
            created_by=request.user,
            updated_by=request.user,
        )
        record(request, "create", document, before=None, after=snapshot(document))
        issued = Letter.objects.create(
            reference=reference,
            employee=employee,
            template=template,
            document=document,
            issued_on=today,
            values=letter["values"],
            sha256=hashlib.sha256(content).hexdigest(),
            career_event=career_event,
            check_code=code,
            created_by=request.user,
            updated_by=request.user,
        )
        record(
            request,
            "letter_issued",
            issued,
            after={
                "reference": reference,
                "template": template.code,
                "version": template.version,
                "document": document.pk,
                "sha256": issued.sha256,
            },
        )
    user = employee.user
    if user is not None and user.is_active and not ask:  # when asked to sign, that notice says it all
        notify(
            [user],
            title=f"A letter for you: {template.name}",
            body=f"Reference {reference}. Read or download it under My contract.",
            link="/me",
            dedupe_key=f"letter:{issued.pk}",
        )
    if ask:
        signing.ask(request, document=issued.document, kind=ask)
    return issued
