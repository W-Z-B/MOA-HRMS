"""Asking for a signature, giving it, declining it, and checking it later (item 1.20)."""

import hashlib

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.services import record, snapshot
from core.net import client_ip
from notifications.services import notify
from people.models import Document, Employee
from signing.models import Signature, SignatureRequest

Kind = SignatureRequest.Kind
State = SignatureRequest.State
STATEMENTS = {
    Kind.ACKNOWLEDGE: "I have received this document and read it.",
    Kind.ACCEPT: "I have read this document and I accept it.",
}
CONFLICTS = frozenset({"waiting", "not_waiting"})


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def fingerprint(document: Document) -> str:
    """SHA-256 of the document's file as it is now."""
    digest = hashlib.sha256()
    with document.file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def signer_of(employee: Employee):
    user = employee.user
    return user if user is not None and user.is_active else None


def ask(request, *, document: Document, kind: str, statement: str = "", message: str = "", due_by=None):
    """Ask the person a document is about to acknowledge or accept it; they are told at once."""
    employee = document.employee
    name = employee.full_name
    if employee.status == Employee.Status.SEPARATED:
        raise Refused("left", f"{name} has left the School.")
    if document.classification == Document.Classification.MEDICAL:
        raise Refused("medical", "Medical documents are not sent for signing.")
    user = signer_of(employee)
    if user is None:
        raise Refused(
            "no_account", f"{name} has no account to sign with. Open one for them first, under Admin."
        )
    if SignatureRequest.objects.filter(document=document, employee=employee, state=State.WAITING).exists():
        raise Refused("waiting", f"{name} has already been asked to sign this document.")
    wanted = SignatureRequest(
        document=document,
        employee=employee,
        kind=kind,
        statement=statement.strip() or STATEMENTS[kind],
        message=message.strip(),
        due_by=due_by,
        created_by=request.user,
        updated_by=request.user,
    )
    with transaction.atomic():
        wanted.save()
        record(request, "signature_requested", wanted, after=snapshot(wanted))
    verb = "accept" if kind == Kind.ACCEPT else "acknowledge"
    notify(
        [user],
        title=f"Please read and {verb}: {document.title}",
        body=wanted.message or wanted.statement,
        link="/me",
        kind="approval",
        dedupe_key=f"sign:{wanted.pk}",
    )
    return wanted


def _tell_requester(wanted: SignatureRequest, title: str, body: str = "") -> None:
    requester = wanted.created_by
    if requester is not None and requester.is_active:
        notify(
            [requester],
            title=title,
            body=body,
            link=f"/people/{wanted.employee_id}",
            dedupe_key=f"signed:{wanted.pk}:{wanted.state}",
        )


def sign(request, wanted: SignatureRequest, password: str) -> Signature:
    """Sign: the person's own password, checked as sign-in checks it, then the evidence is kept."""
    from iam.models import LoginAttempt
    from iam.services import account_locked, address_blocked

    user = request.user
    if wanted.state != State.WAITING:
        raise Refused("not_waiting", "This is no longer waiting for a signature.")
    address = client_ip(request)
    if account_locked(user.get_username()) or address_blocked(address):
        minutes = settings.LOGIN_LOCKOUT_MINUTES
        raise Refused("locked", f"Too many wrong passwords. Wait {minutes} minutes and try again.")
    if not user.check_password(password):
        LoginAttempt.objects.create(username=user.get_username(), source_ip=address, success=False)
        record(request, "signature_failed", wanted)
        raise Refused("wrong_password", "That password is not right.")
    LoginAttempt.objects.create(username=user.get_username(), source_ip=address, success=True)
    document = wanted.document
    with transaction.atomic():
        signature = Signature.objects.create(
            request=wanted,
            signer=user,
            statement=wanted.statement,
            document_title=document.title,
            document_version=document.version,
            sha256=fingerprint(document),
            source_ip=address,
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:200],
        )
        before = snapshot(wanted)
        wanted.state = State.SIGNED
        wanted.decided_at = signature.signed_at
        wanted.updated_by = user
        wanted.save(update_fields=["state", "decided_at", "updated_by", "updated_at"])
        record(
            request,
            "document_signed",
            wanted,
            before=before,
            after={
                "statement": signature.statement,
                "document": document.pk,
                "version": signature.document_version,
                "sha256": signature.sha256,
                "method": signature.method,
            },
        )
    _tell_requester(wanted, f"{wanted.employee.full_name} signed: {document.title}")
    return signature


def decline(request, wanted: SignatureRequest, reason: str) -> SignatureRequest:
    if wanted.state != State.WAITING:
        raise Refused("not_waiting", "This is no longer waiting for a signature.")
    with transaction.atomic():
        before = snapshot(wanted)
        wanted.state = State.DECLINED
        wanted.decided_at = timezone.now()
        wanted.decline_reason = reason.strip()
        wanted.updated_by = request.user
        wanted.save(update_fields=["state", "decided_at", "decline_reason", "updated_by", "updated_at"])
        record(request, "signature_declined", wanted, before=before, after=snapshot(wanted), reason=reason)
    _tell_requester(wanted, f"{wanted.employee.full_name} declined to sign: {wanted.document.title}", reason)
    return wanted


def withdraw(request, wanted: SignatureRequest, reason: str) -> SignatureRequest:
    if wanted.state != State.WAITING:
        raise Refused("not_waiting", "Only a request still waiting can be withdrawn.")
    with transaction.atomic():
        before = snapshot(wanted)
        wanted.state = State.WITHDRAWN
        wanted.decided_at = timezone.now()
        wanted.updated_by = request.user
        wanted.save(update_fields=["state", "decided_at", "updated_by", "updated_at"])
        record(request, "signature_withdrawn", wanted, before=before, after=snapshot(wanted), reason=reason)
    return wanted
