"""A person's file over time, read from the audit log (item 1.08).

Every write to personnel data leaves an audit row with the record before and after the change, who made
it, from where, and why. A person's history is the rows whose subject is that person; the file as it
stood on a day is the state just before the first change after that day.
"""

from audit.services import MASK

HIDDEN = "(hidden)"
RECORDS = {
    "people.employee": "Personal details",
    "people.assignment": "Appointment",
    "people.contract": "Contract",
    "people.document": "Document",
    "people.qualification": "Qualification",
    "people.previousemployment": "Previous employment",
    "people.dependant": "Dependant",
    "people.emergencycontact": "Emergency contact",
    "people.bankaccount": "Bank account",
    "leave.leaverequest": "Leave request",
    "leave.entitlement": "Leave entitlement",
    "auth.user": "Account",
    "iam.accessreview": "Access review",
    "audit.auditlog": "Audit log",
    "audit.auditcheck": "Audit check",
    "integration.serviceclient": "Service key",
    "privacy.correctionrequest": "Correction request",
    "privacy.privacynotice": "Privacy notice",
    "privacy.retentionrule": "Retention rule",
    "privacy.disposalrun": "Disposal run",
    "privacy.breach": "Data breach",
    "letters.lettertemplate": "Letter template",
    "letters.letter": "Letter",
}
ACTIONS = {
    "create": "Added",
    "update": "Changed",
    "delete": "Removed",
    "reveal": "Identifiers revealed",
    "download": "Downloaded",
    "approve": "Approved",
    "reject": "Not approved",
    "attach_evidence": "Note attached",
    "transition:submit": "Sent for approval",
    "transition:approve": "Approved",
    "transition:reject": "Rejected",
    "transition:cancel": "Cancelled",
    "account_opened": "Opened",
    "account_deactivated": "Switched off",
    "account_reactivated": "Switched on again",
    "authenticator_reset": "Authenticator removed",
    "role_granted": "Role given",
    "role_removed": "Role taken away",
    # Account and system events: in the audit viewer, not in a person's file.
    "login": "Signed in",
    "logout": "Signed out",
    "mfa_verified": "Authenticator code accepted",
    "mfa_failed": "Authenticator code refused",
    "session_ended": "Session ended",
    "sessions_ended": "Other sessions ended",
    "password_set": "Password chosen",
    "password_changed": "Password changed",
    "password_change_failed": "Password change refused",
    "password_link_sent": "Password link sent",
    "view_history": "History read",
    "import": "Imported",
    "access_review_signed": "Access review signed off",
    "audit_exported": "Audit log exported",
    "audit_checked": "Audit log checked",
    "correction_requested": "Correction asked for",
    "correction_corrected": "Corrected as asked",
    "correction_declined": "Correction not made",
    "notice_drafted": "Privacy notice drafted",
    "notice_edited": "Privacy notice edited",
    "notice_published": "Privacy notice published",
    "notice_acknowledged": "Privacy notice read",
    "record_viewed": "Own record viewed",
    "record_produced": "Record produced for a request",
    "retention_changed": "Retention period changed",
    "retention_confirmed": "Retention period confirmed",
    "disposal_proposed": "Disposal proposed",
    "disposal_kept": "Kept from disposal",
    "disposal_approved": "Disposal approved",
    "disposal_cancelled": "Disposal cancelled",
    "disposed": "Destroyed under the retention schedule",
    "purged": "Old logs removed",
    "breach_closed": "Breach closed",
    "letter_issued": "Letter issued",
    "template_revised": "Letter template revised",
    "template_retired": "Letter template retired",
    "template_restored": "Letter template back in use",
}
# Account events belong to the audit log, not to the story of a person's file.
NOT_FILE_HISTORY = (
    "view_history",
    "login",
    "logout",
    "mfa_verified",
    "mfa_failed",
    "session_ended",
    "sessions_ended",
    "password_set",
    "password_changed",
    "password_change_failed",
    "password_link_sent",
    "notice_acknowledged",
    "record_viewed",
)
# Stored codes, said in words: (record, field) -> code -> words.
VALUES = {
    ("leave.leaverequest", "state"): {
        "draft": "draft",
        "submitted": "with the manager",
        "supervisor_approved": "with Human Resources",
        "approved": "approved",
        "rejected": "rejected",
        "cancelled": "cancelled",
    },
    ("people.bankaccount", "state"): {
        "pending": "waiting for approval",
        "active": "in use",
        "superseded": "replaced",
        "rejected": "not approved",
    },
    ("people.employee", "status"): {
        "active": "active",
        "on_leave": "on leave",
        "suspended": "suspended",
        "separated": "separated",
    },
}
FIELD_LABELS_BY_RECORD = {("leave.leaverequest", "state"): "Stage", ("people.bankaccount", "state"): "Stage"}
FIELD_LABELS = {
    "nis_no": "NIS number",
    "tin": "TIN",
    "national_id": "National ID",
    "employee_no": "Employee number",
    "account_number": "Account number",
    "roles": "Roles",
}
# Bookkeeping fields that change with every save and say nothing about the person.
QUIET = {"id", "created_at", "updated_at", "created_by", "updated_by"}


def actor_name(row) -> str:
    """Who did it: a person, a linked system, someone not signed in (an emailed link), or the system."""
    if row.actor is not None:
        return row.actor.get_full_name() or row.actor.get_username()
    if row.action.startswith("integration:"):
        return "A linked system"
    return "Someone not signed in" if row.source_ip else "System"


def action_name(code: str) -> str:
    """What was done, in words: integration:staff_list reads as "Integration: staff list"."""
    if code in ACTIONS:
        return ACTIONS[code]
    return ": ".join(part.replace("_", " ") for part in code.split(":")).capitalize()


def field_label(name: str) -> str:
    return FIELD_LABELS.get(name, name.replace("_", " ").capitalize())


def shown(value):
    """Masked values never leave as their fingerprint: the reader learns only that they are set."""
    if isinstance(value, str) and value.startswith(MASK):
        return HIDDEN
    return value


def changes(before: dict | None, after: dict | None, entity: str = "") -> list[dict]:
    if not before or not after:
        return []

    def said(name, value):
        words = VALUES.get((entity, name), {})
        return words.get(value, shown(value)) if isinstance(value, str) else shown(value)

    return [
        {
            "field": FIELD_LABELS_BY_RECORD.get((entity, name), field_label(name)),
            "before": said(name, before.get(name)),
            "after": said(name, after.get(name)),
        }
        for name in after
        if name not in QUIET and before.get(name) != after.get(name)
    ]


def entry(row) -> dict:
    return {
        "id": row.id,
        "at": row.at,
        "actor": actor_name(row),
        "action": row.action,
        "action_name": action_name(row.action),
        "record": RECORDS.get(row.entity, row.entity),
        "record_id": row.entity_id,
        "changes": changes(row.before, row.after, row.entity),
        "reason": row.reason,
        "source_ip": row.source_ip,
    }


def visible(record: dict) -> dict:
    return {name: shown(value) for name, value in record.items() if name not in QUIET}
