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
    "login": "Signed in",
    "logout": "Signed out",
}
FIELD_LABELS = {
    "nis_no": "NIS number",
    "tin": "TIN",
    "national_id": "National ID",
    "employee_no": "Employee number",
    "account_number": "Account number",
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


def changes(before: dict | None, after: dict | None) -> list[dict]:
    if not before or not after:
        return []
    return [
        {"field": field_label(name), "before": shown(before.get(name)), "after": shown(after.get(name))}
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
        "changes": changes(row.before, row.after),
        "reason": row.reason,
        "source_ip": row.source_ip,
    }


def visible(record: dict) -> dict:
    return {name: shown(value) for name, value in record.items() if name not in QUIET}
