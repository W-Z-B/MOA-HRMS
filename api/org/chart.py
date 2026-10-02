"""F01 item 1.10: the organisation chart, drawn from the units, their posts and who holds them today.

One read gives each campus with its units nested as they sit, each unit with its posts, and counts of
filled, vacant and frozen posts for the unit and everything under it. Names follow the staff directory:
the roles that read it, on the campuses it shows them. Abolished posts are left out.
"""

from collections import defaultdict

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core.serializers import ErrorSerializer
from iam.permissions import RolePermission
from iam.services import campus_limit, has_role
from org.models import Campus, OrgUnit, Position
from org.serializers import DIRECTORY_ROLES, grade_name
from people.models import Assignment


class ChartTotalsSerializer(serializers.Serializer):
    posts = serializers.IntegerField(help_text="Posts on the establishment; abolished posts are left out")
    filled = serializers.IntegerField(help_text="Posts with a substantive holder")
    vacant = serializers.IntegerField(help_text="Approved posts with no substantive holder")
    frozen = serializers.IntegerField(help_text="Frozen posts with no substantive holder")


class ChartPostSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    title = serializers.CharField()
    grade_name = serializers.CharField()
    status = serializers.CharField(help_text="approved or frozen")
    status_name = serializers.CharField()
    fte = serializers.DecimalField(max_digits=4, decimal_places=2)
    filled = serializers.BooleanField()
    vacant = serializers.BooleanField()
    holder = serializers.CharField(allow_null=True, help_text="The substantive holder, where names are shown")
    acting = serializers.CharField(
        allow_null=True, help_text="Who is acting in the post, where names are shown"
    )
    has_acting = serializers.BooleanField(help_text="Whether someone is acting in the post")


class ChartUnitSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    unit_type = serializers.CharField()
    unit_type_name = serializers.CharField()
    head = serializers.CharField(allow_null=True, help_text="Who heads the unit, where names are shown")
    totals = ChartTotalsSerializer(help_text="This unit and every unit under it")
    posts = ChartPostSerializer(many=True)

    def get_fields(self):
        fields = super().get_fields()
        fields["units"] = ChartUnitSerializer(many=True, help_text="The units under this one")
        return fields


class ChartCampusSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    names = serializers.BooleanField(help_text="Whether this reader sees who holds posts on this campus")
    totals = ChartTotalsSerializer()
    units = ChartUnitSerializer(many=True)


class ChartSerializer(serializers.Serializer):
    as_at = serializers.DateField(help_text="The day the chart shows: today")
    campuses = ChartCampusSerializer(many=True)


def _count(posts: list[dict]) -> dict:
    return {
        "posts": len(posts),
        "filled": sum(p["filled"] for p in posts),
        "vacant": sum(p["vacant"] for p in posts),
        "frozen": sum(p["status"] == Position.Status.FROZEN and not p["filled"] for p in posts),
    }


def _add(*totals: dict) -> dict:
    return {key: sum(t[key] for t in totals) for key in ("posts", "filled", "vacant", "frozen")}


def build_chart(user, campus_id: int | None = None) -> dict:
    """The chart for one reader, in four queries however large the establishment."""
    campuses = Campus.objects.order_by("code")
    units = OrgUnit.objects.select_related("head").order_by("code")
    posts = (
        Position.objects.exclude(status=Position.Status.ABOLISHED)
        .select_related("grade__scale", "org_unit")
        .order_by("number")
    )
    if campus_id is not None:
        campuses = campuses.filter(pk=campus_id)
        units = units.filter(campus_id=campus_id)
        posts = posts.filter(org_unit__campus_id=campus_id)
    campuses, units, posts = list(campuses), list(units), list(posts)

    holder: dict[int, str] = {}
    acting: dict[int, str] = {}
    holdings = (
        Assignment.objects.filter(status=Assignment.Status.ACTIVE, position_id__in=[p.id for p in posts])
        .select_related("employee")
        .order_by("start_date", "id")
    )
    for holding in holdings:  # oldest first, so the latest appointment is the one kept
        (acting if holding.is_acting else holder)[holding.position_id] = holding.employee.full_name

    directory = has_role(user, *DIRECTORY_ROLES)
    limit = campus_limit(user)

    def names_on(campus: int) -> bool:
        return directory and (limit is None or campus in limit)

    by_unit: dict[int, list[dict]] = defaultdict(list)
    for post in posts:
        names = names_on(post.org_unit.campus_id)
        by_unit[post.org_unit_id].append(
            {
                "id": post.id,
                "number": post.number,
                "title": post.title,
                "grade_name": grade_name(post.grade),
                "status": post.status,
                "status_name": post.get_status_display(),
                "fte": str(post.fte),
                "filled": post.id in holder,
                "vacant": post.status == Position.Status.APPROVED and post.id not in holder,
                "holder": holder.get(post.id) if names else None,
                "acting": acting.get(post.id) if names else None,
                "has_acting": post.id in acting,
            }
        )

    known = {unit.id for unit in units}
    children: dict[int | None, list[OrgUnit]] = defaultdict(list)
    for unit in units:
        children[unit.parent_id if unit.parent_id in known else None].append(unit)

    drawn: set[int] = set()  # a loop in old data cannot hang the chart: each unit is drawn once

    def draw(unit: OrgUnit) -> dict:
        drawn.add(unit.id)
        below = [draw(child) for child in children[unit.id] if child.id not in drawn]
        own = by_unit[unit.id]
        return {
            "id": unit.id,
            "code": unit.code,
            "name": unit.name,
            "unit_type": unit.unit_type,
            "unit_type_name": unit.get_unit_type_display(),
            "head": unit.head.full_name if unit.head_id and names_on(unit.campus_id) else None,
            "totals": _add(_count(own), *(child["totals"] for child in below)),
            "posts": own,
            "units": below,
        }

    drawn_campuses = []
    for campus in campuses:
        tops = [draw(unit) for unit in children[None] if unit.campus_id == campus.id]
        drawn_campuses.append(
            {
                "id": campus.id,
                "code": campus.code,
                "name": campus.name,
                "names": names_on(campus.id),
                "totals": _add(_count([]), *(unit["totals"] for unit in tops)),
                "units": tops,
            }
        )
    return {"as_at": timezone.localdate().isoformat(), "campuses": drawn_campuses}


@extend_schema(
    operation_id="org_chart",
    parameters=[OpenApiParameter("campus", OpenApiTypes.INT, description="One campus only")],
    responses={200: ChartSerializer, 400: ErrorSerializer},
    summary="The organisation chart: units as they nest, their posts, and who holds them",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def chart(request):
    campus = request.query_params.get("campus")
    if campus and not campus.isdigit():
        return Response({"code": "bad_request", "detail": "campus must be a campus id."}, status=400)
    return Response(build_chart(request.user, int(campus) if campus else None))
