"""Report queries keyed by ReportDefinition.key. Each returns a list of dict rows."""

from django.db.models import Count, Q

from org.models import Campus, Position
from people.models import Employee


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


REPORTS = {
    "establishment-vs-actual": establishment_vs_actual,
    "headcount-by-campus": headcount_by_campus,
}
