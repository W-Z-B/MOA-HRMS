"""Report queries keyed by ReportDefinition.key. Each returns a list of dict rows.

A query that takes `campus_id` counts, and can be limited to one campus (?campus= on the report API).
A query whose rows name people takes `campus_ids` instead: the API always passes the campuses the
person running it works with (None for every campus), so the report never reaches past their scope.
"""

from collections import defaultdict
from datetime import date

from django.db.models import Count, Q

from org.models import Campus, Position
from people.models import Assignment, Employee


def establishment_vs_actual(campus_id: int | None = None) -> list[dict]:
    """Approved positions against substantive holders, per campus and unit."""
    positions = Position.objects.filter(status=Position.Status.APPROVED)
    if campus_id:
        positions = positions.filter(org_unit__campus_id=campus_id)
    rows = (
        positions.values("org_unit__campus__name", "org_unit__name")
        .annotate(
            approved=Count("id"),
            filled=Count("id", filter=Q(assignments__status="active", assignments__is_acting=False)),
        )
        .order_by("org_unit__campus__name", "org_unit__name")
    )
    return [
        {
            "campus": r["org_unit__campus__name"],
            "unit": r["org_unit__name"],
            "approved": r["approved"],
            "filled": r["filled"],
            "vacant": r["approved"] - r["filled"],
        }
        for r in rows
    ]


def headcount_by_campus() -> list[dict]:
    rows = Campus.objects.annotate(
        active=Count("employees", filter=Q(employees__status=Employee.Status.ACTIVE)),
        total=Count("employees"),
    ).order_by("code")
    return [{"campus": c.name, "active": c.active, "total": c.total} for c in rows]


IDENTIFIERS = (("nis_no", "NIS number"), ("tin", "TIN"), ("national_id", "National ID"))
# Appointments that must have a written contract on file.
NEEDS_CONTRACT = {
    Assignment.AppointmentType.CONTRACT,
    Assignment.AppointmentType.TEMPORARY,
    Assignment.AppointmentType.SESSIONAL,
    Assignment.AppointmentType.SEASONAL,
}


def _age(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _normalised(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def data_quality(campus_ids: set[int] | None = None, today: date | None = None) -> list[dict]:
    """Records HR should check before they are relied on (item 1.09).

    Identifiers are compared after decryption, in memory, and never appear in the rows: a repeated NIS
    number is reported as "the same as on E0007", not by its value.
    """
    today = today or date.today()
    staff = (
        Employee.objects.exclude(status=Employee.Status.SEPARATED)
        .select_related("campus")
        .prefetch_related("emergency_contacts")
        .order_by("employee_no")
    )
    if campus_ids is not None:
        staff = staff.filter(campus_id__in=campus_ids)

    rows: list[dict] = []
    holders: dict[str, dict[str, list[Employee]]] = {field: defaultdict(list) for field, _ in IDENTIFIERS}
    namesakes: dict[tuple, list[Employee]] = defaultdict(list)

    def flag(employee: Employee, field: str, problem: str) -> None:
        rows.append(
            {
                "employee_id": employee.id,
                "employee_no": employee.employee_no,
                "name": employee.full_name,
                "campus": employee.campus.name,
                "field": field,
                "problem": problem,
            }
        )

    for employee in staff:
        for field, label in IDENTIFIERS:
            value = getattr(employee, field)
            if not value:
                flag(employee, label, f"No {label} on file")
            else:
                holders[field][_normalised(value)].append(employee)
        age = _age(employee.date_of_birth, today)
        if age < 16 or age > 75:
            flag(employee, "Date of birth", f"The date of birth gives an age of {age}; check it")
        if not employee.phone and not employee.email:
            flag(employee, "Contact", "No phone number or email address")
        if not employee.emergency_contacts.all():
            flag(employee, "Emergency contact", "No emergency contact")
        current = employee.current_assignment
        if current is None and employee.status == Employee.Status.ACTIVE:
            flag(employee, "Appointment", "Active, but holds no current appointment")
        elif (
            current is not None
            and current.appointment_type in NEEDS_CONTRACT
            and not current.contracts.exists()
        ):
            flag(
                employee,
                "Contract",
                f"A {current.get_appointment_type_display().lower()} appointment with no contract",
            )
        namesakes[(employee.first_name.lower(), employee.last_name.lower(), employee.date_of_birth)].append(
            employee
        )

    for field, label in IDENTIFIERS:
        for group in holders[field].values():
            if len(group) > 1:
                for employee in group:
                    others = ", ".join(e.employee_no for e in group if e.pk != employee.pk)
                    flag(employee, label, f"The {label} is the same as on {others}")
    for group in namesakes.values():
        if len(group) > 1:
            for employee in group:
                others = ", ".join(e.employee_no for e in group if e.pk != employee.pk)
                flag(
                    employee,
                    "Person",
                    f"Same name and date of birth as {others}: possibly one person filed twice",
                )

    return sorted(rows, key=lambda r: (r["campus"], r["employee_no"], r["field"]))


REPORTS = {
    "establishment-vs-actual": establishment_vs_actual,
    "headcount-by-campus": headcount_by_campus,
    "data-quality": data_quality,
}
