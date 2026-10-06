"""Item 1.46: restriction of part of a record, and objections decided by the data protection officer.

The Data Protection Act 2023 gives a person the right to have the processing of their data restricted while
they contest its accuracy (for long enough to check it), while it is processed unlawfully, while data no
longer needed is kept for their own legal claim, and while their objection is decided; and the right to object
in writing at any time, which stands unless GSA shows compelling legitimate grounds that override the person's
interests, rights and freedoms, or needs the data for a legal claim.

A restricted part is kept, and may be corrected, but it is not used to decide anything about the person or
sent out of the system until the restriction is lifted: letters are not issued from it, changes to the
person's appointment wait, and the systems the HRMS feeds do not receive it. The person is told when a
restriction is placed by someone else, and whenever one is lifted.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.services import record
from iam.models import Role
from notifications.services import notify, users_with_role
from privacy.models import CorrectionRequest, Objection, Restriction

Part = CorrectionRequest.Subject
# What each use of a record draws on: the use waits while any of these parts is restricted.
LETTER_PARTS = frozenset({Part.PERSONAL, Part.APPOINTMENT})
CAREER_PARTS = frozenset({Part.APPOINTMENT})
# What the feed to the sibling systems holds back, part by part. The employee number and the name always go:
# the other systems need them to know who is who.
FEED_FIELDS = {
    Part.CONTACT: ("email",),
    Part.APPOINTMENT: (
        "position_title",
        "appointment_type",
        "unit_code",
        "unit_name",
        "supervisor_employee_no",
    ),
    Part.PERSONAL: ("other_names",),
}


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def in_force(employee=None):
    restrictions = Restriction.objects.filter(lifted_at__isnull=True)
    return restrictions.filter(employee=employee) if employee is not None else restrictions


def refusal(employee, parts) -> str | None:
    """Why a use of these parts of someone's record must wait, or None when it need not."""
    held = in_force(employee).filter(part__in=parts).order_by("created_at").first()
    if held is None:
        return None
    return (
        f"{held.get_part_display()} in the record of {employee.full_name} is restricted "
        f"({held.get_ground_display().lower()}), so it cannot be used for this until the restriction is "
        "lifted."
    )


def restricted_parts(employee) -> set[str]:
    return set(in_force(employee).values_list("part", flat=True))


def _tell(employee, title: str, body: str, key: str) -> None:
    if employee.user_id is not None and employee.user.is_active:
        notify([employee.user], title=title, body=body, link="/my-record", dedupe_key=key)


def place(request, employee, *, part: str, ground: str, note: str = "", correction=None, objection=None):
    with transaction.atomic():
        restriction = Restriction.objects.create(
            employee=employee,
            part=part,
            ground=ground,
            note=note.strip(),
            correction=correction,
            objection=objection,
            created_by=request.user,
            updated_by=request.user,
        )
        record(request, "restriction_placed", restriction, after={"part": part, "ground": ground})
    if employee.user_id != request.user.pk:
        _tell(
            employee,
            f"{restriction.get_part_display()} in your record is restricted",
            f"{restriction.get_ground_display()}. It is kept, but not used, until the restriction is lifted.",
            f"restriction:{restriction.pk}:placed",
        )
    return restriction


def lift(request, restriction: Restriction, reason: str) -> Restriction:
    """Lift it, telling the person why. One that waits on an objection or a correction request stays until
    that is decided or answered, so nobody cuts short the time the law gives to check."""
    if restriction.lifted_at is not None:
        raise Refused("lifted", "That restriction is already lifted.")
    if restriction.objection_id and restriction.objection.state == Objection.State.OPEN:
        raise Refused("waiting", "It is held back until the data protection officer decides the objection.")
    if restriction.correction_id and restriction.correction.state == CorrectionRequest.State.OPEN:
        raise Refused("waiting", "It is held back until the correction request is answered.")
    reason = reason.strip()
    with transaction.atomic():
        restriction.lifted_at = timezone.now()
        restriction.lifted_by = request.user
        restriction.lifted_reason = reason
        restriction.updated_by = request.user
        restriction.save()
        record(request, "restriction_lifted", restriction, after={"part": restriction.part}, reason=reason)
    _tell(
        restriction.employee,
        f"The restriction on {restriction.get_part_display().lower()} in your record is lifted",
        reason,
        f"restriction:{restriction.pk}:lifted",
    )
    return restriction


def lodge(request, employee, *, part: str, grounds: str) -> Objection:
    """An objection in writing: the part is restricted at once, until the officer decides."""
    with transaction.atomic():
        objection = Objection.objects.create(
            employee=employee,
            part=part,
            grounds=grounds.strip(),
            due_by=timezone.localdate() + timedelta(days=settings.PRIVACY_RESPONSE_DAYS),
            created_by=request.user,
            updated_by=request.user,
        )
        record(request, "objection_lodged", objection, after={"part": part})
        place(request, employee, part=part, ground=Restriction.Ground.OBJECTION, objection=objection)
    officers = [u for u in users_with_role(Role.DATA_PROTECTION_OFFICER) if u.pk != employee.user_id]
    notify(
        officers,
        title=f"An objection to decide: {employee.full_name}",
        body=f"About {objection.get_part_display().lower()}. Decide by {objection.due_by:%d/%m/%Y}.",
        link="/admin/objections",
        kind="approval",
        dedupe_key=f"objection:{objection.pk}:lodged",
    )
    return objection


def decide(request, objection: Objection, *, upheld: bool, reasons: str) -> Objection:
    """Upheld, that use of the part stops and the restriction stays; not upheld, it is lifted."""
    if objection.state != Objection.State.OPEN:
        raise Refused("decided", "This objection has been decided.")
    if objection.employee.user_id == request.user.pk:
        raise Refused("own", "Someone else decides an objection of yours.")
    reasons = reasons.strip()
    with transaction.atomic():
        objection.state = Objection.State.UPHELD if upheld else Objection.State.NOT_UPHELD
        objection.decided_by = request.user
        objection.decided_at = timezone.now()
        objection.reasons = reasons
        objection.updated_by = request.user
        objection.save()
        record(
            request, f"objection_{objection.state}", objection, after={"part": objection.part}, reason=reasons
        )
        if not upheld:
            for restriction in in_force(objection.employee).filter(objection=objection):
                lift(request, restriction, f"Your objection was not upheld: {reasons}")
    if upheld:
        _tell(
            objection.employee,
            "Your objection is upheld",
            f"{objection.get_part_display()} is no longer used that way. {reasons}",
            f"objection:{objection.pk}:decided",
        )
    return objection
