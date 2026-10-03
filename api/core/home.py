"""Home (item 2.30): the figures each person's Home shows first, worked out in one request.

Which Home a person gets follows their roles: Human Resources, the Principal, a head of unit, another
office role, or an employee with no other role. Every figure is counted inside the campuses the person
works with, by the same rules as the list it leads to, so a number on Home never promises more than its
page shows. ?campus= narrows the figures to one of those campuses, as the campus switch does everywhere.
"""

from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from approvals.inbox import waiting_for
from core.serializers import ErrorSerializer
from iam.models import Role
from iam.permissions import SelfServicePermission
from iam.services import campus_limit, has_role, role_codes, scope_queryset
from leave.models import LeaveRequest
from org.chart import build_chart
from org.models import Campus, OrgUnit
from people.models import Assignment, Employee
from people.views import HR_WRITE, STAFF_READ

# Kinds of waiting item that are leave to decide, at the manager's step or Human Resources'.
LEAVE_KINDS = ("leave", "leave_hr")
WAITING_STATES = (LeaveRequest.State.SUBMITTED, LeaveRequest.State.SUPERVISOR_APPROVED)


def persona(user) -> str:
    """Which Home a person sees. A person with several roles gets the one with the widest view."""
    if has_role(user, *HR_WRITE):
        return "hr"
    if has_role(user, Role.PRINCIPAL):
        return "principal"
    if has_role(user, Role.SUPERVISOR):
        return "manager"
    if role_codes(user) - {Role.EMPLOYEE}:
        return "office"
    return "employee"


def _campuses(user, wanted: int | None) -> list[Campus]:
    """The campuses this Home counts: those the person works with, or the one they chose of those."""
    limit = campus_limit(user)
    campuses = Campus.objects.order_by("code")
    if limit is not None:
        campuses = campuses.filter(pk__in=limit)
    if wanted is not None:
        campuses = campuses.filter(pk=wanted)
    return list(campuses)


def _chart(campuses: list[Campus]) -> dict[int, dict]:
    """The organisation chart of each campus counted, by campus id. Only its counts are used here."""
    wanted = {campus.id for campus in campuses}
    return {drawn["id"]: drawn for drawn in build_chart(None)["campuses"] if drawn["id"] in wanted}


def _staff(campuses: list[Campus], chart: dict[int, dict]) -> dict:
    """Active staff and the establishment on each campus counted, and in all of them together."""
    active = dict(
        Employee.objects.filter(status=Employee.Status.ACTIVE, campus__in=campuses)
        .values_list("campus")
        .annotate(n=Count("id"))
    )
    rows = [
        {"id": campus.id, "code": campus.code, "name": campus.name, "active": active.get(campus.id, 0)}
        | chart[campus.id]["totals"]
        for campus in campuses
    ]
    keys = ("active", "posts", "filled", "vacant", "frozen")
    return {"campuses": rows, **{key: sum(row[key] for row in rows) for key in keys}}


def _units(campuses: list[Campus], chart: dict[int, dict]) -> list[dict]:
    """Each unit's own posts (not those of the units under it), for the Principal's establishment view."""
    rows = []

    def walk(unit: dict, campus: str) -> None:
        own = unit["posts"]
        if own:
            rows.append(
                {
                    "id": unit["id"],
                    "name": unit["name"],
                    "campus": campus,
                    "posts": len(own),
                    "filled": sum(p["filled"] for p in own),
                    "vacant": sum(p["vacant"] for p in own),
                    "frozen": sum(p["status"] == "frozen" and not p["filled"] for p in own),
                }
            )
        for child in unit["units"]:
            walk(child, campus)

    for campus in campuses:
        for unit in chart[campus.id]["units"]:
            walk(unit, campus.name)
    return rows


def _ending(holdings, today: date) -> list[dict]:
    """Appointments whose contract or probation ends inside the alert horizon, soonest first."""
    horizon = today + timedelta(days=settings.HOME_ENDING_DAYS)
    soon = holdings.filter(
        Q(end_date__range=(today, horizon))
        | Q(probation_end__range=(today, horizon), confirmed_on__isnull=True)
    ).select_related("employee__campus", "position")
    rows = []
    for held in soon:
        common = {
            "employee": held.employee_id,
            "name": held.employee.full_name,
            "position": held.position.title,
            "campus": held.employee.campus.name,
        }
        if held.end_date and today <= held.end_date <= horizon:
            rows.append(common | {"what": "contract", "on": held.end_date})
        if held.probation_end and not held.confirmed_on and today <= held.probation_end <= horizon:
            rows.append(common | {"what": "probation", "on": held.probation_end})
    return sorted(rows, key=lambda row: (row["on"], row["name"]))


def _no_account(campuses: list[Campus]) -> dict:
    """Active staff who cannot sign in yet: how many, and the latest five to start."""
    staff = Employee.objects.filter(status=Employee.Status.ACTIVE, user__isnull=True, campus__in=campuses)
    starts = {
        a.employee_id: a
        for a in Assignment.objects.filter(
            employee__in=staff, status=Assignment.Status.ACTIVE, is_acting=False
        ).select_related("position")
    }
    people = sorted(
        staff.select_related("campus"),
        key=lambda e: (starts[e.id].start_date if e.id in starts else date.min, e.employee_no),
        reverse=True,
    )
    return {
        "count": len(people),
        "latest": [
            {
                "employee": e.id,
                "name": e.full_name,
                "position": starts[e.id].position.title if e.id in starts else None,
                "campus": e.campus.name,
                "started": starts[e.id].start_date if e.id in starts else None,
            }
            for e in people[:5]
        ],
    }


def _team(head: Employee) -> list[dict]:
    """The people in the units this person heads, and the units under those, the head first."""
    units = set(OrgUnit.objects.filter(head=head).values_list("id", flat=True))
    frontier = set(units)
    while frontier:  # a loop in old data ends: a unit already counted is never walked again
        frontier = set(OrgUnit.objects.filter(parent__in=frontier).values_list("id", flat=True)) - units
        units |= frontier
    holdings = (
        Assignment.objects.filter(
            position__org_unit__in=units,
            status=Assignment.Status.ACTIVE,
            is_acting=False,
            employee__status=Employee.Status.ACTIVE,
        )
        .select_related("employee", "position")
        .order_by("employee__last_name", "employee__first_name")
    )
    team = [
        {
            "employee": held.employee_id,
            "name": held.employee.full_name,
            "position": held.position.title,
            "appointment": held.get_appointment_type_display(),
            "started": held.start_date,
            "ends": held.end_date,
            "probation_end": None if held.confirmed_on else held.probation_end,
            "is_me": held.employee_id == head.id,
        }
        for held in holdings
    ]
    return sorted(team, key=lambda person: not person["is_me"])


def summary(user, wanted: int | None = None) -> dict:
    today = timezone.localdate()
    kind = persona(user)
    own = getattr(user, "employee", None)
    waiting = [item for item in waiting_for(user) if item["kind"] in LEAVE_KINDS]
    result = {
        "persona": kind,
        "as_at": today,
        "ending_days": settings.HOME_ENDING_DAYS,
        "leave": {"mine": len(waiting), "waiting": None},
        "staff": None,
        "units": None,
        "ending": None,
        "no_account": None,
        "team": None,
    }
    if has_role(user, *STAFF_READ) and kind != "manager":
        campuses = _campuses(user, wanted)
        chart = _chart(campuses)
        result["staff"] = _staff(campuses, chart)
        asked = LeaveRequest.objects.filter(state__in=WAITING_STATES, employee__campus__in=campuses)
        result["leave"]["waiting"] = scope_queryset(user, asked, "employee__campus").count()
        holdings = Assignment.objects.filter(
            status=Assignment.Status.ACTIVE, is_acting=False, employee__status=Employee.Status.ACTIVE
        )
        result["ending"] = _ending(holdings.filter(employee__campus__in=campuses), today)
        if kind == "principal":
            result["units"] = _units(campuses, chart)
        if kind == "hr":
            result["no_account"] = _no_account(campuses)
    if kind == "manager" and own is not None:
        result["team"] = _team(own)
        members = [person["employee"] for person in result["team"]]
        holdings = Assignment.objects.filter(
            employee__in=members, status=Assignment.Status.ACTIVE, is_acting=False
        )
        result["ending"] = _ending(holdings, today)
    return result


class LeaveCountsSerializer(serializers.Serializer):
    mine = serializers.IntegerField(help_text="Leave waiting for my decision, as a manager, stand-in or HR")
    waiting = serializers.IntegerField(
        allow_null=True,
        help_text="All leave awaiting a decision on the campuses counted; null when not the person's to see",
    )


class CampusFiguresSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    active = serializers.IntegerField(help_text="Active staff on the campus")
    posts = serializers.IntegerField(help_text="Posts on the establishment, not counting abolished ones")
    filled = serializers.IntegerField()
    vacant = serializers.IntegerField()
    frozen = serializers.IntegerField(help_text="Frozen posts nobody holds")


class StaffFiguresSerializer(serializers.Serializer):
    campuses = CampusFiguresSerializer(many=True)
    active = serializers.IntegerField()
    posts = serializers.IntegerField()
    filled = serializers.IntegerField()
    vacant = serializers.IntegerField()
    frozen = serializers.IntegerField()


class UnitFiguresSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    campus = serializers.CharField()
    posts = serializers.IntegerField(help_text="The unit's own posts, not those of the units under it")
    filled = serializers.IntegerField()
    vacant = serializers.IntegerField()
    frozen = serializers.IntegerField()


class EndingSerializer(serializers.Serializer):
    employee = serializers.IntegerField()
    name = serializers.CharField()
    position = serializers.CharField()
    campus = serializers.CharField()
    what = serializers.ChoiceField(choices=["contract", "probation"])
    on = serializers.DateField(help_text="The day the contract or probation ends")


class StarterSerializer(serializers.Serializer):
    employee = serializers.IntegerField()
    name = serializers.CharField()
    position = serializers.CharField(allow_null=True)
    campus = serializers.CharField()
    started = serializers.DateField(allow_null=True)


class NoAccountSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    latest = StarterSerializer(many=True, help_text="The latest five to start")


class TeamMemberSerializer(serializers.Serializer):
    employee = serializers.IntegerField()
    name = serializers.CharField()
    position = serializers.CharField()
    appointment = serializers.CharField()
    started = serializers.DateField()
    ends = serializers.DateField(allow_null=True)
    probation_end = serializers.DateField(allow_null=True, help_text="Empty once confirmed in the post")
    is_me = serializers.BooleanField()


class HomeSerializer(serializers.Serializer):
    persona = serializers.ChoiceField(
        choices=["hr", "principal", "manager", "office", "employee"], help_text="Which Home to show"
    )
    as_at = serializers.DateField()
    ending_days = serializers.IntegerField(help_text="How far ahead contract and probation ends are listed")
    leave = LeaveCountsSerializer()
    staff = StaffFiguresSerializer(allow_null=True)
    units = UnitFiguresSerializer(many=True, allow_null=True)
    ending = EndingSerializer(many=True, allow_null=True)
    no_account = NoAccountSerializer(allow_null=True)
    team = TeamMemberSerializer(many=True, allow_null=True)


@extend_schema(
    parameters=[OpenApiParameter("campus", OpenApiTypes.INT, description="Count one campus only")],
    responses={200: HomeSerializer, 400: ErrorSerializer},
    summary="What my Home shows: figures for my role, on the campuses I work with",
)
@api_view(["GET"])
@permission_classes([SelfServicePermission])
def home(request):
    campus = request.query_params.get("campus") or ""
    if campus and not campus.isdigit():
        return Response({"code": "bad_request", "detail": "campus must be a campus id."}, status=400)
    return Response(HomeSerializer(summary(request.user, int(campus) if campus else None)).data)
