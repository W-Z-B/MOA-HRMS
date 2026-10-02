"""The privacy notice in force, and a person's own copy of what the system holds about them (item 1.31)."""

from django.utils import timezone

from privacy.models import CorrectionRequest, NoticeAcknowledgement, PrivacyNotice


def current_notice() -> PrivacyNotice | None:
    """The newest published version, or None before GSA publishes one."""
    return PrivacyNotice.objects.filter(published_at__isnull=False).order_by("-version").first()


def notice_due(user) -> int | None:
    """The version this person has still to read, or None."""
    notice = current_notice()
    if notice is None or not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return None
    if NoticeAcknowledgement.objects.filter(notice=notice, user=user).exists():
        return None
    return notice.version


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


def _account(user) -> dict:
    from iam.accounts import where
    from iam.models import RoleScope, UserSession
    from iam.sessions import describe_device

    return {
        "username": user.get_username(),
        "name": _name(user),
        "email": user.email,
        "roles": [
            {
                "role": grant.role.name,
                "where": where(grant),
                "given": grant.created_at,
                "given_by": _name(grant.created_by),
            }
            for grant in RoleScope.objects.filter(user=user).select_related(
                "role", "campus", "org_unit", "created_by"
            )
        ],
        "last_sign_in": user.last_login,
        "signed_in_on": [
            {
                "device": describe_device(s.user_agent),
                "address": s.ip,
                "since": s.created_at,
                "last_active": s.last_seen_at,
            }
            for s in UserSession.objects.filter(user=user)
        ],
        "privacy_notices_read": [
            {"version": a.notice.version, "title": a.notice.title, "read_at": a.at}
            for a in NoticeAcknowledgement.objects.filter(user=user).select_related("notice")
        ],
    }


def _money(value) -> str | None:
    return f"G${value:,.2f}" if value is not None else None


def _terms(terms: dict) -> dict:
    """The appointment and contract in the words a person reads them, without the system's own fields."""
    contract = terms["contract"]
    return {
        "position": terms["position"],
        "unit": terms["unit"],
        "manager": terms["manager"],
        "appointment_type": terms["appointment_type"],
        "start_date": terms["start_date"],
        "end_date": terms["end_date"],
        "probation_end": terms["probation_end"],
        "contract": None
        if contract is None
        else {
            "contract_type": contract["contract_type"],
            "term_months": contract["term_months"],
            "signed_on": contract["signed_on"],
            "hours_per_week": contract["hours_per_week"],
            "hourly_rate": _money(contract["hourly_rate"]),
            "notice_period_days": contract["notice_period_days"],
            "other_terms": contract["other_terms"],
        },
        "leave_entitlements": [
            {
                "leave": row["name"],
                "days_a_year": row["annual_days"],
                "set_by_the_contract": row["from_contract"],
            }
            for row in terms["entitlements"]
        ],
    }


def _staff_record(employee) -> dict:
    from audit.models import AuditLog
    from leave.services import balances_for
    from people import history
    from people.services import terms_for

    assignments = employee.assignments.select_related("position", "position__org_unit").order_by(
        "-start_date"
    )
    return {
        "personal": {
            "employee_no": employee.employee_no,
            "first_name": employee.first_name,
            "other_names": employee.other_names,
            "last_name": employee.last_name,
            "date_of_birth": employee.date_of_birth,
            "gender": employee.get_gender_display(),
            "national_id": employee.national_id,
            "nis_no": employee.nis_no,
            "tin": employee.tin,
            "email": employee.email,
            "phone": employee.phone,
            "address": employee.address,
            "campus": employee.campus.name,
            "status": employee.get_status_display(),
        },
        "appointments": [
            {
                "position": a.position.title,
                "unit": a.position.org_unit.name,
                "appointment_type": a.get_appointment_type_display(),
                "start_date": a.start_date,
                "end_date": a.end_date,
                "probation_end": a.probation_end,
                "acting": a.is_acting,
                "status": a.get_status_display(),
            }
            for a in assignments
        ],
        "contract_and_terms": _terms(terms_for(employee)),
        "leave_balances": [
            {"leave": row["name"], "balance": row["balance"], "waiting_for_a_decision": row["pending"]}
            for row in balances_for(employee)
        ],
        "leave_requests": [
            {
                "leave": r.leave_type.name,
                "from_date": r.from_date,
                "to_date": r.to_date,
                "days": r.days,
                "reason": r.reason,
                "state": r.get_state_display(),
                "decision_comment": r.decision_comment,
            }
            for r in employee.leave_requests.select_related("leave_type")
        ],
        "qualifications": [
            {
                "level": q.get_level_display(),
                "title": q.title,
                "institution": q.institution,
                "country": q.country,
                "year_awarded": q.year_awarded,
                "verified_on": q.verified_on,
            }
            for q in employee.qualifications.all()
        ],
        "work_before_gsa": [
            {
                "employer": p.employer,
                "position": p.position,
                "start_date": p.start_date,
                "end_date": p.end_date,
                "reason_for_leaving": p.reason_for_leaving,
            }
            for p in employee.previous_employment.all()
        ],
        "dependants": [
            {"name": d.name, "relationship": d.get_relationship_display(), "date_of_birth": d.date_of_birth}
            for d in employee.dependants.all()
        ],
        "emergency_contacts": [
            {
                "name": c.name,
                "relationship": c.relationship,
                "phone": c.phone,
                "alternate_phone": c.alternate_phone,
            }
            for c in employee.emergency_contacts.all()
        ],
        # The number is left out of a file that may be saved or sent on: the last four digits identify it.
        "bank_accounts": [
            {
                "bank": b.bank_name,
                "branch": b.branch,
                "account_name": b.account_name,
                "account_ending": b.account_number_last4,
                "state": b.get_state_display(),
                "in_use_from": b.effective_from,
            }
            for b in employee.bank_accounts.all()
        ],
        "documents": [
            {
                "title": d.title,
                "type": d.doc_type,
                "classification": d.get_classification_display(),
                "version": d.version,
                "filed_on": d.created_at,
            }
            for d in employee.documents.all()
        ],
        "correction_requests": [
            {
                "about": c.get_subject_display(),
                "wrong": c.wrong,
                "should_be": c.should_be,
                "state": c.get_state_display(),
                "asked_on": c.created_at,
                "answer": c.decision_note,
            }
            for c in CorrectionRequest.objects.filter(employee=employee)
        ],
        "history_of_changes": [
            {key: entry[key] for key in ("at", "actor", "action_name", "record", "changes", "reason")}
            for entry in (
                history.entry(row)
                for row in AuditLog.objects.filter(subject=employee.pk)
                .exclude(action__in=history.NOT_FILE_HISTORY)
                .select_related("actor")
                .order_by("-at", "-id")[:1000]
            )
        ],
    }


def record_of(user) -> dict:
    """Everything the system holds about this person, for their own copy."""
    employee = getattr(user, "employee", None)
    return {
        "produced_at": timezone.now(),
        "about": "What the GSA HRMS holds about you. Ask Human Resources if anything here is wrong.",
        "account": _account(user),
        "staff_record": _staff_record(employee) if employee is not None else None,
    }


def record_of_employee(employee) -> dict:
    """The same copy for a member of staff who asked HR for it, account included when they have one."""
    data = {
        "produced_at": timezone.now(),
        "about": "What the GSA HRMS holds about this member of staff, produced for their request.",
        "account": _account(employee.user) if employee.user_id else None,
        "staff_record": _staff_record(employee),
    }
    return data
