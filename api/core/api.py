"""Public holidays (item 1.25): the days leave does not count, kept by the HR Manager and administrators.

Leave already approved keeps the days it was approved with; a changed holiday counts from the next request.
"""

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from core import holidays
from core.models import PublicHoliday
from core.serializers import TimeStampedSerializer
from core.views import AuditedModelViewSet
from iam.models import Role

YEAR = OpenApiParameter("year", OpenApiTypes.INT, description="Calendar year; this year when left out")


class HolidaySerializer(TimeStampedSerializer):
    weekday = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = PublicHoliday
        fields = ("id", "date", "weekday", "name", "created_at", "updated_at")

    def get_weekday(self, holiday) -> str:
        return f"{holiday.date:%A}"


class ExpectedSerializer(serializers.Serializer):
    name = serializers.CharField()
    rule = serializers.CharField()
    date = serializers.DateField(allow_null=True, help_text="Empty when the gazette names the date")
    on_file = HolidaySerializer(allow_null=True)


class CalendarSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    expected = ExpectedSerializer(many=True)
    others = HolidaySerializer(
        many=True, help_text="Holidays on file that no rule names, such as substitute days"
    )
    sundays = HolidaySerializer(
        many=True, help_text="Holidays on a Sunday: the gazette may name a substitute day"
    )


def _year(request) -> int:
    raw = request.query_params.get("year") or ""
    if raw and not (raw.isdigit() and 2000 <= int(raw) <= 2100):
        raise serializers.ValidationError({"year": ["Give a year such as 2027."]})
    return int(raw) if raw else timezone.localdate().year


@extend_schema(parameters=[YEAR])
class HolidayViewSet(AuditedModelViewSet):
    """Everyone signed in reads the holidays; the HR Manager and administrators keep them."""

    serializer_class = HolidaySerializer
    queryset = PublicHoliday.objects.none()
    write_roles = (Role.HR_MANAGER, Role.ADMINISTRATOR)
    pagination_class = None

    def get_queryset(self):
        holidays_ = PublicHoliday.objects.order_by("date")
        return holidays_.filter(date__year=_year(self.request)) if self.action == "list" else holidays_

    @extend_schema(
        parameters=[YEAR], responses=CalendarSerializer, summary="The year checked against Guyana's holidays"
    )
    @action(detail=False, methods=["get"])
    def calendar(self, request):
        year = _year(request)
        on_file = list(PublicHoliday.objects.filter(date__year=year).order_by("date"))
        by_date = {h.date: h for h in on_file}
        matched: set[int] = set()
        rows = []
        for item in holidays.expected(year):
            found = by_date.get(item.day) if item.day else None
            if item.day is None:
                words = dict(holidays.FROM_THE_GAZETTE)[item.name]
                found = next((h for h in on_file if any(w in h.name.lower() for w in words)), None)
            if found is not None:
                matched.add(found.pk)
            rows.append({"name": item.name, "rule": item.rule, "date": item.day, "on_file": found})
        payload = {
            "year": year,
            "expected": rows,
            "others": [h for h in on_file if h.pk not in matched],
            "sundays": [h for h in on_file if h.date.weekday() == 6],
        }
        return Response(CalendarSerializer(payload).data)


router = SimpleRouter()
router.register("holidays", HolidayViewSet, basename="holiday")
urlpatterns = router.urls
