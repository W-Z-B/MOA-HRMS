"""Item 1.21: piles of scanned personnel papers filed into staff records, each found by the employee number at
the start of its name, such as "E0001 Appointment 2014.pdf".

Each file passes the checks every document does (its contents must match its name, and it is no larger than
the limit) and is filed under the batch's type and classification, never below what the type needs. HR files
only for staff on the campuses it works with: a number from anywhere else reads as nobody's, so a refusal
never tells who works where. A file whose name gives no number, or a number HR cannot file for, waits for HR
to choose whose file it belongs in. The same file sent twice for the same person is filed once.
"""

import hashlib
import re
from pathlib import PurePath

from django.db import transaction
from rest_framework import serializers

from audit.services import record, snapshot
from core.uploads import DOCUMENT, validate_upload
from iam.services import scope_queryset
from people.models import Document, Employee, ScanBatch, ScanItem

DOC_TYPES = {
    "contract": "Contract",
    "certificate": "Certificate",
    "letter": "Letter",
    "id_copy": "ID copy",
    "medical": "Medical",
    "other": "Other",
}
# As (value, label) pairs, for ScanItemSerializer.doc_type's ChoiceField and config.settings'
# ENUM_NAME_OVERRIDES: H-W02 added a second, differently-scoped "doc_type" field (people.onboarding_views),
# and the override needs pairs, not the dict above, to hash the same way the field itself does.
DOC_TYPE_CHOICES = tuple(DOC_TYPES.items())
# Up to four letters then up to eight digits, at the very start, followed by a space, _ - . or nothing.
LEADING_NUMBER = re.compile(r"^\s*([A-Za-z]{0,4}\d{1,8})(?=[\s_.\-]|$)")


def number_in(name: str) -> str | None:
    """The employee number a file's name starts with, if any."""
    match = LEADING_NUMBER.match(PurePath(name).stem)
    return match.group(1).upper() if match else None


def title_from(name: str, doc_type: str) -> str:
    """The rest of the file's name, tidied, as the document's title: "E0001_appointment-2014.pdf" gives
    "appointment-2014"; a name that is only the number gives the type, such as "Contract"."""
    rest = LEADING_NUMBER.sub("", PurePath(name).stem, count=1)
    rest = re.sub(r"[_\s]+", " ", rest).strip(" -_.")
    return (rest or DOC_TYPES.get(doc_type, "Scanned paper"))[:160]


def _fingerprint(upload) -> str:
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def _refuse(item: ScanItem, why: str) -> ScanItem:
    item.refused = why[:300]
    item.save()
    return item


def file_one(request, batch: ScanBatch, upload, employee: Employee | None = None) -> ScanItem:
    """File one scanned paper, into the record its name gives or the one HR chose. Always returns the
    item, filed or with the reason it was not."""
    item = ScanItem(batch=batch, name=PurePath(upload.name).name[:255])
    try:
        validate_upload(upload, DOCUMENT)
    except serializers.ValidationError as exc:
        return _refuse(item, " ".join(str(message) for message in exc.detail))
    item.sha256 = _fingerprint(upload)
    if employee is None:
        number = number_in(item.name)
        if number is None:
            return _refuse(item, "The name does not start with an employee number. Choose whose file it is.")
        staff = scope_queryset(request.user, Employee.objects.all(), "campus")
        employee = staff.filter(employee_no__iexact=number).first()
        if employee is None:
            return _refuse(item, f"Nobody on your campuses has the number {number}. Choose whose file it is.")
    item.employee = employee
    earlier = (
        ScanItem.objects.filter(employee=employee, sha256=item.sha256, document__isnull=False)
        .select_related("document")
        .first()
    )
    if earlier is not None:
        return _refuse(item, f"Already filed as “{earlier.document.title}” on {earlier.at:%d/%m/%Y}.")
    with transaction.atomic():
        document = Document.objects.create(
            employee=employee,
            doc_type=batch.doc_type,
            title=title_from(item.name, batch.doc_type),
            file=upload,
            classification=batch.classification,
            created_by=request.user,
            updated_by=request.user,
        )
        record(
            request,
            "create",
            document,
            before=None,
            after=snapshot(document),
            reason=f"Scanned papers, batch {batch.pk}",
        )
        item.document = document
        item.save()
    return item
