"""Load a fictional demonstration dataset: units, establishment, staff, contracts, leave and training.

For staging and development databases only, never for a database that holds real records. Every
person is invented, says so in the address line, and carries identifiers that are plainly not real.
Idempotent: running it again adds nothing. Run `seed` first.

Accounts for the invented staff are created only when DEMO_USER_PASSWORD is set, so that a database
reachable from the internet never receives accounts with a password its owner did not choose.
"""

import os
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from iam.models import Role, RoleScope
from incidents.models import Action, Incident, Person
from leave.models import Entitlement, LeaveLedger, LeaveRequest, LeaveType
from leave.services import debit_for_request, working_days
from org.models import Campus, Grade, OrgUnit, Position, SalaryScale
from people.models import Assignment, Contract, Employee, IssuedItem
from people.services import manager_of
from privacy.models import PrivacyNotice
from training.models import TrainingRecord, TrainingRequirement

FICTIONAL = "Demonstration record (fictional person)"
EMAIL_DOMAIN = "gsa.example"
# Dates are fixed so that a second run, in any year, finds the same rows.
SCALE_FROM = date(2026, 1, 1)

# Monthly amounts are placeholders, not GSA's salary scale.
GRADES = [("GS3", 120000), ("GS5", 180000), ("GS7", 250000), ("GS9", 340000)]

UNITS = [
    # code, name, type, campus
    ("AGR", "Department of Agriculture", "department", "MRP"),
    ("LIV", "Livestock Unit", "unit", "MRP"),
    ("ADM", "Administration", "section", "MRP"),
    ("ESQ-AGR", "Department of Agriculture, Essequibo", "department", "ESQ"),
]
# The unit above, so that a head of unit has a manager of their own.
PARENTS = {"LIV": "AGR"}

POSITIONS = [
    # number, title, grade, unit, status
    ("AGR-001", "Head of Department, Agriculture", "GS9", "AGR", "approved"),
    ("AGR-002", "Lecturer, Crop Science", "GS7", "AGR", "approved"),
    ("AGR-003", "Lecturer, Soil Science", "GS7", "AGR", "approved"),
    ("AGR-004", "Laboratory Technician", "GS5", "AGR", "approved"),
    ("LIV-001", "Livestock Instructor", "GS7", "LIV", "approved"),
    ("LIV-002", "Farm Attendant", "GS3", "LIV", "approved"),
    ("LIV-003", "Farm Attendant", "GS3", "LIV", "approved"),
    ("ADM-001", "Human Resources Officer", "GS7", "ADM", "approved"),
    ("ADM-002", "Accounts Clerk", "GS5", "ADM", "approved"),
    ("ADM-003", "Records Clerk", "GS3", "ADM", "frozen"),
    ("ESQ-AGR-001", "Lecturer, Agriculture", "GS7", "ESQ-AGR", "approved"),
    ("ESQ-AGR-002", "Field Instructor", "GS5", "ESQ-AGR", "approved"),
    ("ESQ-AGR-003", "Farm Attendant", "GS3", "ESQ-AGR", "approved"),
]

STAFF = [
    # number, first name, last name, born, gender, campus, post, appointment, start
    ("E0001", "Asha", "Persaud", date(1990, 3, 14), "F", "MRP", "AGR-002", "permanent", date(2019, 9, 2)),
    ("E0002", "Michael", "Thomas", date(1978, 7, 22), "M", "MRP", "AGR-001", "permanent", date(2012, 1, 16)),
    ("E0003", "Shanta", "Ramdeen", date(1985, 11, 5), "F", "MRP", "AGR-003", "permanent", date(2016, 9, 1)),
    ("E0004", "Kwame", "Adams", date(1982, 2, 18), "M", "MRP", "LIV-001", "permanent", date(2014, 3, 3)),
    ("E0005", "Roxanne", "Williams", date(1995, 6, 30), "F", "MRP", "LIV-002", "temporary", date(2026, 7, 1)),
    ("E0006", "Natasha", "Khan", date(1988, 9, 12), "F", "MRP", "ADM-001", "permanent", date(2017, 5, 15)),
    ("E0007", "Devon", "Charles", date(1992, 12, 1), "M", "MRP", "ADM-002", "permanent", date(2020, 2, 3)),
    (
        "E0008",
        "Indira",
        "Narine",
        date(1980, 4, 25),
        "F",
        "ESQ",
        "ESQ-AGR-001",
        "permanent",
        date(2013, 9, 2),
    ),
    (
        "E0009",
        "Troy",
        "Benjamin",
        date(1997, 8, 8),
        "M",
        "ESQ",
        "ESQ-AGR-002",
        "contract",
        date(2025, 11, 17),
    ),
    ("E0010", "Kemal", "Bacchus", date(1999, 1, 19), "M", "MRP", "LIV-003", "temporary", date(2026, 9, 28)),
    (
        "E0011",
        "Petal",
        "Fredericks",
        date(2001, 4, 3),
        "F",
        "ESQ",
        "ESQ-AGR-003",
        "temporary",
        date(2026, 9, 28),
    ),
]
# Joined this week: HR has yet to open their accounts, so there is someone to invite (item 1.29).
NEW_STARTERS = {"E0010", "E0011"}
# Accounts for people who are not on the staff: username, first name, last name, role (on every campus).
OUTSIDE_ACCOUNTS = [
    ("audit.reviewer", "Audit", "Reviewer", "auditor"),
    ("privacy.officer", "Privacy", "Officer", "data_protection_officer"),
    # The Principal's own Home (item 2.30): the establishment and what ends soon, on every campus.
    ("principal.office", "Office of the", "Principal", "principal"),
]
# A contract that ends soon and a probation that is still running, so the daily alerts have work to do.
ENDS = {"E0009": date(2026, 11, 16)}
PROBATION_ENDS = {"E0005": date(2026, 12, 31)}

HEADS = {"AGR": "E0002", "LIV": "E0004", "ADM": "E0006", "ESQ-AGR": "E0008"}

# Contract by appointment type: contract type, term in months. Hours and notice are the same for
# all. The rate and the entitlements below are placeholders, not the terms GSA gives.
CONTRACTS = {
    "permanent": ("open_ended", None),
    "contract": ("fixed_term", 12),
    "temporary": ("fixed_term", 6),
}
HOURS_PER_WEEK = Decimal("40")
NOTICE_DAYS = 30
HOURLY_RATES = {"E0005": Decimal("750.00")}  # paid by the hour; the others by their grade
ENTITLEMENTS = {"E0009": {"ANN": Decimal("14"), "SIC": Decimal("10")}}

# Things handed out to staff (item 1.17): employee, kind, description, tag, issued on.
ISSUED = [
    ("E0004", "key", "Key to the livestock pens", "", date(2014, 3, 3)),
    ("E0004", "protective", "Rubber boots and overalls", "", date(2026, 1, 12)),
    ("E0003", "device", "Laptop", "GSA-IT-0042", date(2023, 9, 4)),
    ("E0008", "key", "Key to the Essequibo seed store", "", date(2013, 9, 2)),
]

# Accidents and incidents (item 1.16), both closed so that nothing waits on anyone: reference, kind, when,
# unit, where, what happened, what was done at once, the cause found, closed on, who was hurt (employee,
# injury, treatment) and the action taken (owner, what, due, done, what was done).
INCIDENTS = [
    (
        "IN-2026-001",
        "near_miss",
        datetime(2026, 3, 10, 10, 15),
        "LIV",
        "Livestock pens, gate 2",
        "A bull pushed through a gate whose latch had worked loose. Nobody was in the pen.",
        "The gate was tied shut and the bull moved to the far paddock.",
        "The latch was worn, and pen gates were not on any inspection list.",
        date(2026, 3, 28),
        None,
        (
            "E0004",
            "Replace the latches on every pen gate and add them to the monthly check.",
            date(2026, 3, 31),
            date(2026, 3, 27),
            "New latches fitted; the gates are on the monthly checklist.",
        ),
    ),
    (
        "IN-2026-002",
        "accident",
        datetime(2026, 5, 18, 14, 0),
        "AGR",
        "Soil laboratory sink",
        "A beaker cracked while being washed and cut a hand.",
        "First aid from the laboratory kit; the broken glass was cleared away.",
        "Chipped glassware was still in use.",
        date(2026, 6, 15),
        ("E0003", "Cut to the left palm", "first_aid"),
        (
            "E0002",
            "Check the glassware each term and throw away anything chipped.",
            date(2026, 6, 30),
            date(2026, 6, 12),
            "Glassware checked; nine chipped pieces thrown away.",
        ),
    ),
]

# Every invented employee signs in as first.last. Heads of unit are supervisors as well.
HR_OFFICER = "E0006"
PASSWORD_VARIABLE = "DEMO_USER_PASSWORD"  # noqa: S105 - the name of the variable, not a password

OPENING_BALANCES = [("ANN", Decimal("10")), ("SIC", Decimal("14"))]

LEAVE_REQUESTS = [
    # employee, type, from, to, reason, state
    ("E0002", "ANN", date(2026, 8, 10), date(2026, 8, 14), "Family visit to Berbice", "approved"),
    ("E0005", "ANN", date(2026, 11, 2), date(2026, 11, 6), "Personal matters", "submitted"),
    ("E0007", "SIC", date(2026, 9, 21), date(2026, 9, 22), "Medical certificate to follow", "submitted"),
]

# Shown to each person at their first sign-in (item 1.31). GSA's own notice replaces it before real records.
DEMO_NOTICE_TITLE = "Demonstration privacy notice"
DEMO_NOTICE_BODY = "\n\n".join(
    [
        "This is demonstration text for the staging system, not the notice of the Guyana School of "
        "Agriculture. GSA's own notice replaces it before any real record is loaded.",
        "Who holds your data. The Guyana School of Agriculture keeps your staff record in this system to run "
        "your employment: your appointment, contract, leave and the details your pay needs.",
        "Who sees it. You see your own record. Human Resources, and the officers your work reports to, see "
        "what their work needs. Every look at sensitive details, such as identity numbers, is recorded.",
        "How long it is kept. As long as the law and GSA's records rules require, and then it is deleted.",
        "Your rights. You can see everything held about you under My record, ask there for anything wrong to "
        "be corrected, and complain to the Data Protection Commissioner.",
    ]
)

TRAINING = [
    # employee, course, starts, ends
    ("E0004", "Artificial insemination techniques: refresher", date(2026, 6, 8), date(2026, 6, 12)),
]

REQUIRED_TRAINING = [
    # title, LMS course code, post title, campus, due days, renewal months (item 5.24)
    ("First aid at work", "SD-FA-01", "", "MRP", 60, 24),
    ("Safe handling of livestock", "SD-LS-01", "Farm Attendant", "", 30, None),
]


class Command(BaseCommand):
    help = "Load fictional demonstration data (staging and development only). Requires --fictional."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fictional",
            action="store_true",
            help="Required: confirms this database is for demonstration, never for real records",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["fictional"]:
            raise CommandError(
                "This loads invented people. Pass --fictional to confirm the database holds no real records."
            )
        campuses = {c.code: c for c in Campus.objects.all()}
        leave_types = {t.code: t for t in LeaveType.objects.all()}
        if not {"MRP", "ESQ"} <= set(campuses) or not {"ANN", "SIC"} <= set(leave_types):
            raise CommandError("Reference data is missing. Run `manage.py seed` first.")

        grades = self._grades()
        units = {
            code: OrgUnit.objects.update_or_create(
                code=code, defaults={"name": name, "unit_type": kind, "campus": campuses[campus]}
            )[0]
            for code, name, kind, campus in UNITS
        }
        for code, parent in PARENTS.items():
            OrgUnit.objects.filter(code=code, parent__isnull=True).update(parent=units[parent])
        positions = {
            number: Position.objects.update_or_create(
                number=number,
                defaults={"title": title, "grade": grades[grade], "org_unit": units[unit], "status": status},
            )[0]
            for number, title, grade, unit, status in POSITIONS
        }

        staff, assigned, skipped = {}, 0, 0
        for index, row in enumerate(STAFF, start=1):
            number, first, last, born, gender, campus, post, appointment, start = row
            end, probation = ENDS.get(number), PROBATION_ENDS.get(number)
            staff[number], _ = Employee.objects.update_or_create(
                employee_no=number,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "date_of_birth": born,
                    "gender": gender,
                    "campus": campuses[campus],
                    "email": f"{first}.{last}@{EMAIL_DOMAIN}".lower(),
                    "address": FICTIONAL,
                    "national_id": f"DEMO-ID-{index:04d}",
                    "nis_no": f"DEMO-NIS-{index:04d}",
                    "tin": f"DEMO-TIN-{index:04d}",
                },
            )
            if self._assign(staff[number], positions[post], appointment, start, end, probation):
                assigned += 1
            else:
                skipped += 1
        for unit_code, number in HEADS.items():
            OrgUnit.objects.filter(code=unit_code, head__isnull=True).update(head=staff[number])
        for number, employee in staff.items():
            self._contract(number, employee, leave_types)
        accounts = self._accounts(staff, campuses)
        if not PrivacyNotice.objects.exists():
            PrivacyNotice.objects.create(
                version=1, title=DEMO_NOTICE_TITLE, body=DEMO_NOTICE_BODY, published_at=timezone.now()
            )

        for employee in staff.values():
            for code, days in OPENING_BALANCES:
                LeaveLedger.objects.get_or_create(
                    employee=employee,
                    leave_type=leave_types[code],
                    reason=LeaveLedger.Reason.OPENING,
                    entry_date=SCALE_FROM,
                    defaults={"days": days, "note": "Demonstration opening balance"},
                )
        for number, code, start, end, reason, state in LEAVE_REQUESTS:
            request, created = LeaveRequest.objects.get_or_create(
                employee=staff[number],
                leave_type=leave_types[code],
                from_date=start,
                defaults={"to_date": end, "days": working_days(start, end), "reason": reason, "state": state},
            )
            if created and state == LeaveRequest.State.APPROVED:
                debit_for_request(request)
            if request.state == LeaveRequest.State.SUBMITTED and request.manager is None:
                # Waiting for a decision: send it to the manager, who may only now have an account.
                request.manager = manager_of(staff[number])
                request.save(update_fields=["manager"])
        for number, course, starts, ends in TRAINING:
            TrainingRecord.objects.get_or_create(
                employee=staff[number],
                course=course,
                starts=starts,
                defaults={
                    "provider": "External provider (fictional)",
                    "ends": ends,
                    "certification": "Certificate of attendance",
                },
            )

        for title, code, post_title, campus, due_days, renewal in REQUIRED_TRAINING:
            TrainingRequirement.objects.get_or_create(
                title=title,
                defaults={
                    "course_code": code,
                    "post_title": post_title,
                    "campus": campuses.get(campus),
                    "due_days": due_days,
                    "renewal_months": renewal,
                    "notes": FICTIONAL,
                },
            )

        for number, kind, description, tag, issued_on in ISSUED:
            IssuedItem.objects.get_or_create(
                employee=staff[number],
                description=description,
                defaults={"kind": kind, "tag": tag, "issued_on": issued_on, "note": FICTIONAL},
            )

        self._incidents(staff, units)

        vacant = sum(1 for p in Position.objects.filter(number__in=positions) if p.is_vacant)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demonstration data applied: {len(units)} units, {len(positions)} posts ({vacant} vacant), "
                f"{len(staff)} staff, {assigned} new assignments ({skipped} already in place or skipped)."
            )
        )
        if accounts is None:
            self.stdout.write(f"No accounts created: {PASSWORD_VARIABLE} is not set.")
        else:
            self.stdout.write(
                f"Accounts: {accounts} created. {len(NEW_STARTERS)} new starters have none, for HR to invite."
            )

    def _incidents(self, staff, units) -> None:
        keeper = staff[HR_OFFICER].user  # None when no accounts were created
        for reference, kind, when, unit, place, what, at_once, cause, closed_on, hurt, action in INCIDENTS:
            incident, created = Incident.objects.get_or_create(
                reference=reference,
                defaults={
                    "kind": kind,
                    "occurred_at": timezone.make_aware(when),
                    "campus": units[unit].campus,
                    "org_unit": units[unit],
                    "place": place,
                    "description": what,
                    "immediate_action": at_once,
                    "cause": cause,
                    "investigated_on": closed_on,
                    "investigated_by": keeper,
                    "state": Incident.State.CLOSED,
                    "closed_on": closed_on,
                    "closed_by": keeper,
                    "created_by": keeper,
                },
            )
            if not created:
                continue
            if hurt:
                number, injury, treatment = hurt
                Person.objects.create(
                    incident=incident,
                    who=Person.Who.STAFF,
                    employee=staff[number],
                    injury=injury,
                    treatment=treatment,
                )
            owner, task, due_on, done_on, done_note = action
            Action.objects.create(
                incident=incident,
                what=task,
                owner=staff[owner],
                due_on=due_on,
                done_on=done_on,
                done_note=done_note,
            )

    def _grades(self) -> dict[str, Grade]:
        scale, _ = SalaryScale.objects.get_or_create(code="GS", defaults={"name": "General scale"})
        return {
            code: Grade.objects.get_or_create(
                scale=scale, code=code, step=1, effective_from=SCALE_FROM, defaults={"amount": amount}
            )[0]
            for code, amount in GRADES
        }

    def _assign(self, employee, position, appointment, start, end, probation) -> bool:
        """Place the employee in the post unless either side already has a substantive appointment."""
        substantive = {"is_acting": False, "status": Assignment.Status.ACTIVE}
        if (
            employee.assignments.filter(**substantive).exists()
            or position.assignments.filter(**substantive).exists()
        ):
            return False
        try:
            with transaction.atomic():
                Assignment.objects.create(
                    employee=employee,
                    position=position,
                    appointment_type=appointment,
                    start_date=start,
                    end_date=end,
                    probation_end=probation,
                )
        except IntegrityError:
            return False
        return True

    def _contract(self, number, employee, leave_types) -> None:
        """Give the current appointment a contract with terms; fill the terms of one made earlier."""
        assignment = employee.current_assignment
        if assignment is None or assignment.appointment_type not in CONTRACTS:
            return
        kind, months = CONTRACTS[assignment.appointment_type]
        contract = assignment.contracts.first()
        if contract is None:
            contract = Contract.objects.create(
                assignment=assignment, contract_type=kind, term_months=months, signed_on=assignment.start_date
            )
        if contract.hours_per_week is None:
            contract.hours_per_week = HOURS_PER_WEEK
            contract.notice_period_days = NOTICE_DAYS
            contract.hourly_rate = HOURLY_RATES.get(number)
            contract.save()
        for code, days in ENTITLEMENTS.get(number, {}).items():
            Entitlement.objects.get_or_create(
                contract=contract, leave_type=leave_types[code], defaults={"annual_days": days}
            )

    def _accounts(self, staff, campuses) -> int | None:
        """Accounts named first.last, linked to the employee, with roles on their campus.

        An account that already exists keeps its password; only a missing link or role is added.
        """
        password = os.environ.get(PASSWORD_VARIABLE, "")
        if not password:
            return None
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(f"{PASSWORD_VARIABLE} is too weak: {' '.join(exc.messages)}") from exc
        users = get_user_model()
        roles = {code: Role.objects.get(code=code) for code in ("employee", "supervisor", "hr_officer")}
        heads = set(HEADS.values())
        created = 0
        for number, employee in staff.items():
            if number in NEW_STARTERS:
                continue
            username = f"{employee.first_name}.{employee.last_name}".lower()
            user = employee.user or users.objects.filter(username=username).first()
            if user is None:
                user = users.objects.create_user(
                    username=username,
                    password=password,
                    email=employee.email,
                    first_name=employee.first_name,
                    last_name=employee.last_name,
                )
                created += 1
            if employee.user_id != user.id:
                employee.user = user
                employee.save(update_fields=["user"])
            grants = [("employee", employee.campus)]
            if number in heads:
                grants.append(("supervisor", employee.campus))
            if number == HR_OFFICER:
                grants += [("hr_officer", campus) for campus in campuses.values()]
            for code, campus in grants:
                RoleScope.objects.get_or_create(user=user, role=roles[code], campus=campus, org_unit=None)
        for username, first, last, code in OUTSIDE_ACCOUNTS:
            user, made = users.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "email": f"{username}@{EMAIL_DOMAIN}"},
            )
            if made:
                user.set_password(password)
                user.save(update_fields=["password"])
                created += 1
            RoleScope.objects.get_or_create(
                user=user, role=Role.objects.get(code=code), campus=None, org_unit=None
            )
        return created
