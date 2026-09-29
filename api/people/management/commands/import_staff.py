"""Import units, positions, employees, assignments and opening leave balances from a spreadsheet.

Sprint 1 issue #7. Idempotent on natural keys; validates everything before writing anything;
prints a reconciliation table. Uses openpyxl (already a dependency) and nothing else.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import Workbook, load_workbook

from audit.models import AuditLog
from leave.models import LeaveLedger, LeaveType
from org.models import Campus, Grade, OrgUnit, Position, SalaryScale
from people.models import Assignment, Employee

SHEETS = {
    "Units": ["code", "name", "unit_type", "campus_code", "parent_code"],
    "Positions": [
        "number",
        "title",
        "unit_code",
        "scale_code",
        "grade_code",
        "step",
        "amount",
        "effective_from",
        "status",
    ],
    "Employees": [
        "employee_no",
        "first_name",
        "last_name",
        "other_names",
        "date_of_birth",
        "gender",
        "national_id",
        "nis_no",
        "tin",
        "email",
        "phone",
        "address",
        "campus_code",
        "status",
        "position_number",
        "appointment_type",
        "start_date",
        "probation_end",
    ],
    "LeaveBalances": ["employee_no", "leave_type_code", "days", "as_of"],
}
SENSITIVE = {"national_id", "nis_no", "tin"}


@dataclass
class Counts:
    read: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    counts: dict[str, Counts] = field(default_factory=lambda: {name: Counts() for name in SHEETS})

    def error(self, sheet: str, row: int, column: str, message: str) -> None:
        self.errors.append(f"{sheet} row {row}, {column}: {message}")


class Rollback(Exception):
    """Raised inside the transaction to roll a dry run back after counting."""


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _date(value, *, required: bool):
    if value in (None, ""):
        if required:
            raise ValueError("is required")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("must be a date (yyyy-mm-dd or dd/mm/yyyy)")


def _decimal(value, *, required: bool):
    if value in (None, ""):
        if required:
            raise ValueError("is required")
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("must be a number") from exc


def _choice(value, choices, *, required: bool):
    """Case-insensitive match against a Django choices list; returns the stored value."""
    text = _text(value)
    if not text:
        if required:
            raise ValueError("is required")
        return None
    mapping = {str(c[0]).lower(): c[0] for c in choices}
    if text.lower() not in mapping:
        raise ValueError(f"must be one of {sorted(mapping.values())}")
    return mapping[text.lower()]


class Command(BaseCommand):
    help = "Import staff data from the spreadsheet template (idempotent, all-or-nothing)."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Path to the filled-in .xlsx template")
        parser.add_argument("--dry-run", action="store_true", help="Validate and count, write nothing")
        parser.add_argument("--write-template", metavar="PATH", help="Write an empty template and exit")

    def handle(self, *args, **options):
        if options["write_template"]:
            self._write_template(options["write_template"])
            return
        if not options["file"]:
            raise CommandError("--file is required (or use --write-template).")
        report = Report()
        try:
            with transaction.atomic():
                self._import(options["file"], report)
                if report.errors:
                    raise Rollback
                if options["dry_run"]:
                    raise Rollback
        except Rollback:
            pass
        self._print(report, dry_run=options["dry_run"])
        if report.errors:
            raise CommandError(f"{len(report.errors)} validation error(s); nothing was written.")

    # ----- template -------------------------------------------------------------------------------

    def _write_template(self, path: str) -> None:
        wb = Workbook()
        wb.remove(wb.active)
        for name, columns in SHEETS.items():
            ws = wb.create_sheet(name)
            ws.append(columns)
        notes = wb.create_sheet("Notes")
        notes.append(["Sheet", "Guidance"])
        notes.append(["Units", "unit_type: department, farm, unit, section. campus_code: MRP or ESQ."])
        notes.append(
            ["Positions", "status: approved, frozen, abolished. amount is monthly GYD. Dates yyyy-mm-dd."]
        )
        notes.append(
            [
                "Employees",
                "gender: F, M, X. appointment_type: permanent, contract, temporary, sessional, seasonal.",
            ]
        )
        notes.append(
            ["LeaveBalances", "Opening balance in days per leave type code (ANN, SIC, ...) as of a date."]
        )
        wb.save(path)
        self.stdout.write(self.style.SUCCESS(f"Template written to {path}"))

    # ----- import ---------------------------------------------------------------------------------

    def _rows(self, wb, name: str, report: Report):
        if name not in wb.sheetnames:
            report.error(name, 1, "sheet", "sheet is missing")
            return []
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        header = [_text(h) for h in rows[0]]
        missing = [c for c in SHEETS[name] if c not in header]
        if missing:
            report.error(name, 1, "header", f"missing columns {missing}")
            return []
        out = []
        for index, values in enumerate(rows[1:], start=2):
            if all(v in (None, "") for v in values):
                continue
            out.append((index, dict(zip(header, values, strict=False))))
        report.counts[name].read = len(out)
        return out

    def _import(self, path: str, report: Report) -> None:
        try:
            wb = load_workbook(path, data_only=True)
        except Exception as exc:  # noqa: BLE001 - surface any reader failure as a validation error
            report.error("workbook", 0, "file", f"cannot open: {exc}")
            return
        campuses = {c.code: c for c in Campus.objects.all()}
        leave_types = {t.code: t for t in LeaveType.objects.all()}

        units: dict[str, OrgUnit] = {u.code: u for u in OrgUnit.objects.all()}
        for row, data in self._rows(wb, "Units", report):
            code = _text(data["code"])
            campus = campuses.get(_text(data["campus_code"]))
            if not code:
                report.error("Units", row, "code", "is required")
                continue
            if campus is None:
                report.error("Units", row, "campus_code", "unknown campus")
                continue
            try:
                unit_type = _choice(data["unit_type"], OrgUnit.UnitType.choices, required=True)
            except ValueError as exc:
                report.error("Units", row, "unit_type", str(exc))
                continue
            parent_code = _text(data["parent_code"])
            parent = units.get(parent_code) if parent_code else None
            if parent_code and parent is None:
                report.error("Units", row, "parent_code", "unknown unit (parents must appear first)")
                continue
            unit, created = OrgUnit.objects.update_or_create(
                code=code,
                defaults={
                    "name": _text(data["name"]),
                    "unit_type": unit_type,
                    "campus": campus,
                    "parent": parent,
                },
            )
            units[code] = unit
            self._count(report, "Units", created)

        positions: dict[str, Position] = {p.number: p for p in Position.objects.all()}
        for row, data in self._rows(wb, "Positions", report):
            number = _text(data["number"])
            unit = units.get(_text(data["unit_code"]))
            if not number:
                report.error("Positions", row, "number", "is required")
                continue
            if unit is None:
                report.error("Positions", row, "unit_code", "unknown unit")
                continue
            try:
                step = int(data["step"] or 1)
                amount = _decimal(data["amount"], required=True)
                effective_from = _date(data["effective_from"], required=True)
                status = _choice(data["status"] or "approved", Position.Status.choices, required=True)
            except (ValueError, TypeError) as exc:
                report.error("Positions", row, "step/amount/effective_from/status", str(exc))
                continue
            scale, _ = SalaryScale.objects.get_or_create(
                code=_text(data["scale_code"]) or "GS", defaults={"name": _text(data["scale_code"]) or "GS"}
            )
            grade, _ = Grade.objects.get_or_create(
                scale=scale,
                code=_text(data["grade_code"]),
                step=step,
                effective_from=effective_from,
                defaults={"amount": amount},
            )
            position, created = Position.objects.update_or_create(
                number=number,
                defaults={"title": _text(data["title"]), "grade": grade, "org_unit": unit, "status": status},
            )
            positions[number] = position
            self._count(report, "Positions", created)

        employees: dict[str, Employee] = {}
        for row, data in self._rows(wb, "Employees", report):
            employee_no = _text(data["employee_no"])
            campus = campuses.get(_text(data["campus_code"]))
            if not employee_no:
                report.error("Employees", row, "employee_no", "is required")
                continue
            if campus is None:
                report.error("Employees", row, "campus_code", "unknown campus")
                continue
            try:
                dob = _date(data["date_of_birth"], required=True)
                gender = _choice(data["gender"] or "X", Employee.Gender.choices, required=True)
                status = _choice(data["status"] or "active", Employee.Status.choices, required=True)
                start = _date(data["start_date"], required=False)
                probation_end = _date(data["probation_end"], required=False)
                appointment = _choice(
                    data["appointment_type"], Assignment.AppointmentType.choices, required=False
                )
            except ValueError as exc:
                report.error("Employees", row, "dates/gender/status/appointment_type", str(exc))
                continue
            if not _text(data["first_name"]) or not _text(data["last_name"]):
                report.error("Employees", row, "first_name/last_name", "are required")
                continue
            position_number = _text(data["position_number"])
            position = positions.get(position_number) if position_number else None
            if position_number and position is None:
                report.error("Employees", row, "position_number", "unknown position")
                continue
            if position and (start is None or appointment is None):
                report.error(
                    "Employees", row, "start_date/appointment_type", "required when a position is given"
                )
                continue
            defaults = {
                "first_name": _text(data["first_name"]),
                "last_name": _text(data["last_name"]),
                "other_names": _text(data["other_names"]),
                "date_of_birth": dob,
                "gender": gender,
                "email": _text(data["email"]),
                "phone": _text(data["phone"]),
                "address": _text(data["address"]),
                "campus": campus,
                "status": status,
            }
            for key in SENSITIVE:
                if _text(data[key]):
                    defaults[key] = _text(data[key])
            employee, created = Employee.objects.update_or_create(employee_no=employee_no, defaults=defaults)
            employees[employee_no] = employee
            self._count(report, "Employees", created)
            AuditLog.objects.create(
                action="import",
                entity="people.employee",
                entity_id=employee.id,
                after={"employee_no": employee_no, "created": created, "source": "import_staff"},
            )
            if position:
                Assignment.objects.update_or_create(
                    employee=employee,
                    position=position,
                    start_date=start,
                    defaults={"appointment_type": appointment, "probation_end": probation_end},
                )

        for row, data in self._rows(wb, "LeaveBalances", report):
            employee = (
                employees.get(_text(data["employee_no"]))
                or Employee.objects.filter(employee_no=_text(data["employee_no"])).first()
            )
            leave_type = leave_types.get(_text(data["leave_type_code"]))
            if employee is None:
                report.error("LeaveBalances", row, "employee_no", "unknown employee")
                continue
            if leave_type is None:
                report.error("LeaveBalances", row, "leave_type_code", "unknown leave type")
                continue
            try:
                days = _decimal(data["days"], required=True)
                as_of = _date(data["as_of"], required=False) or date.today()
            except ValueError as exc:
                report.error("LeaveBalances", row, "days/as_of", str(exc))
                continue
            exists = LeaveLedger.objects.filter(
                employee=employee, leave_type=leave_type, reason=LeaveLedger.Reason.OPENING
            ).exists()
            if exists:
                report.counts["LeaveBalances"].skipped += 1
                continue
            LeaveLedger.objects.create(
                employee=employee,
                leave_type=leave_type,
                entry_date=as_of,
                days=days,
                reason=LeaveLedger.Reason.OPENING,
                note="opening balance from import",
            )
            report.counts["LeaveBalances"].created += 1

    @staticmethod
    def _count(report: Report, sheet: str, created: bool) -> None:
        if created:
            report.counts[sheet].created += 1
        else:
            report.counts[sheet].updated += 1

    def _print(self, report: Report, *, dry_run: bool) -> None:
        self.stdout.write(f"{'DRY RUN, nothing written' if dry_run else 'Import result'}")
        self.stdout.write(f"{'Sheet':<14}{'read':>6}{'created':>9}{'updated':>9}{'skipped':>9}")
        for name, c in report.counts.items():
            self.stdout.write(f"{name:<14}{c.read:>6}{c.created:>9}{c.updated:>9}{c.skipped:>9}")
        for error in report.errors:
            self.stdout.write(self.style.ERROR(error))
