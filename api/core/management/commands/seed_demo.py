"""Load a fictional demonstration dataset: units, establishment, staff, leave and training.

For staging and development databases only, never for a database that holds real records. Every
person is invented, says so in the address line, and carries identifiers that are plainly not real.
Idempotent: running it again adds nothing. Run `seed` first.
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from leave.models import LeaveLedger, LeaveRequest, LeaveType
from leave.services import debit_for_request, working_days
from org.models import Campus, Grade, OrgUnit, Position, SalaryScale
from people.models import Assignment, Contract, Employee
from training.models import TrainingRecord

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
]
# A contract that ends soon and a probation that is still running, so the daily alerts have work to do.
ENDS = {"E0009": date(2026, 11, 16)}
PROBATION_ENDS = {"E0005": date(2026, 12, 31)}

HEADS = {"AGR": "E0002", "LIV": "E0004", "ADM": "E0006", "ESQ-AGR": "E0008"}

OPENING_BALANCES = [("ANN", Decimal("10")), ("SIC", Decimal("14"))]

LEAVE_REQUESTS = [
    # employee, type, from, to, reason, state
    ("E0002", "ANN", date(2026, 8, 10), date(2026, 8, 14), "Family visit to Berbice", "approved"),
    ("E0005", "ANN", date(2026, 11, 2), date(2026, 11, 6), "Personal matters", "submitted"),
    ("E0007", "SIC", date(2026, 9, 21), date(2026, 9, 22), "Medical certificate to follow", "submitted"),
]

TRAINING = [
    # employee, course, starts, ends
    ("E0004", "Artificial insemination techniques: refresher", date(2026, 6, 8), date(2026, 6, 12)),
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

        vacant = sum(1 for p in Position.objects.filter(number__in=positions) if p.is_vacant)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demonstration data applied: {len(units)} units, {len(positions)} posts ({vacant} vacant), "
                f"{len(staff)} staff, {assigned} new assignments ({skipped} already in place or skipped)."
            )
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
                assignment = Assignment.objects.create(
                    employee=employee,
                    position=position,
                    appointment_type=appointment,
                    start_date=start,
                    end_date=end,
                    probation_end=probation,
                )
        except IntegrityError:
            return False
        if appointment == Assignment.AppointmentType.CONTRACT:
            Contract.objects.create(
                assignment=assignment, contract_type=Contract.ContractType.FIXED_TERM, term_months=12
            )
        return True
