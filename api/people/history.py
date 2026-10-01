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
    actor = row.actor
    return {
        "id": row.id,
        "at": row.at,
        "actor": (actor.get_full_name() or actor.get_username()) if actor else "System",
        "action": row.action,
        "action_name": ACTIONS.get(row.action, row.action.replace("_", " ").capitalize()),
        "record": RECORDS.get(row.entity, row.entity),
        "record_id": row.entity_id,
        "changes": changes(row.before, row.after, row.entity),
        "reason": row.reason,
        "source_ip": row.source_ip,
    }


def visible(record: dict) -> dict:
    return {name: shown(value) for name, value in record.items() if name not in QUIET}
