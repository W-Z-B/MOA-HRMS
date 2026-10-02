"""Career changes (item 1.11): HR records them; anyone who reads staff files sees them, without pay."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.serializers import ErrorSerializer, InScope
from iam.permissions import RolePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from org.models import Position
from org.serializers import grade_name
from people import careers
from people.models import CareerEvent, Employee
from people.views import CONFIDENTIAL_READ, HR_WRITE, STAFF_READ


class CareerEventSerializer(serializers.ModelSerializer):
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    from_post = serializers.SerializerMethodField()
    to_post = serializers.SerializerMethodField()
    from_grade_name = serializers.SerializerMethodField()
    to_grade_name = serializers.SerializerMethodField()
    recorded_by = serializers.SerializerMethodField()
    letter_template = serializers.SerializerMethodField(help_text="The template its letter is written with")
    letter_answers = serializers.SerializerMethodField(
        help_text="What its letter asks, answered from the change: for HR, who write the letters"
    )
    letters = serializers.SerializerMethodField(help_text="Letters issued for it: for those who read them")

    class Meta:
        model = CareerEvent
        fields = (
            "id",
            "employee",
            "kind",
            "kind_name",
            "state",
            "state_name",
            "effective_date",
            "end_date",
            "from_post",
            "to_position",
            "to_post",
            "from_grade_name",
            "to_grade_name",
            "reason",
            "problem",
            "applied_at",
            "recorded_by",
            "created_at",
            "letter_template",
            "letter_answers",
            "letters",
        )
        read_only_fields = fields

    def _may(self, *roles) -> bool:
        request = self.context.get("request")
        return request is not None and has_role(request.user, *roles)

    def get_from_post(self, event) -> str | None:
        old = event.from_assignment
        return f"{old.position.number} {old.position.title}" if old else None

    def get_to_post(self, event) -> str | None:
        return f"{event.to_position.number} {event.to_position.title}" if event.to_position_id else None

    def get_from_grade_name(self, event) -> str | None:
        return grade_name(event.from_grade) if event.from_grade_id else None

    def get_to_grade_name(self, event) -> str | None:
        return grade_name(event.to_grade) if event.to_grade_id else None

    def get_recorded_by(self, event) -> str | None:
        user = event.created_by
        return (user.get_full_name() or user.get_username()) if user else None

    def get_letter_template(self, event) -> str:
        return careers.LETTER_FOR[event.kind]

    def get_letter_answers(self, event) -> dict[str, str] | None:
        return careers.letter_answers(event) if self._may(*HR_WRITE) else None

    def get_letters(self, event) -> list[dict]:
        if not self._may(*CONFIDENTIAL_READ):
            return []
        return [
            {
                "id": letter.id,
                "reference": letter.reference,
                "download_url": f"/api/v1/letters/{letter.id}/download/",
            }
            for letter in event.letters.all()
        ]


class RecordChangeSerializer(serializers.Serializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    kind = serializers.ChoiceField(choices=CareerEvent.Kind.choices)
    effective_date = serializers.DateField()
    to_position = InScope(
        Position,
        campus_field="org_unit__campus",
        required=False,
        allow_null=True,
        help_text="The post moved to, or acted in",
    )
    end_date = serializers.DateField(required=False, allow_null=True, help_text="When acting ends, if known")
    reason = serializers.CharField(
        max_length=300,
        error_messages={"required": "Say why.", "blank": "Say why."},
        help_text="Kept on record",
    )

    def validate(self, attrs):
        end = attrs.get("end_date")
        if end is not None and attrs["kind"] != CareerEvent.Kind.ACTING:
            raise serializers.ValidationError(
                {"end_date": ["Only an acting appointment has an end date here."]}
            )
        if end is not None and end < attrs["effective_date"]:
            raise serializers.ValidationError({"end_date": ["It ends after it begins."]})
        return attrs


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=300, error_messages={"required": "Say why.", "blank": "Say why."}
    )


def _refused(exc: careers.Refused) -> Response:
    code = status.HTTP_409_CONFLICT if exc.code in careers.CONFLICTS else status.HTTP_400_BAD_REQUEST
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


@extend_schema(parameters=[OpenApiParameter("employee", int, description="One member of staff")])
class CareerEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = CareerEvent.objects.none()
    serializer_class = CareerEventSerializer
    permission_classes = [RolePermission]
    read_roles = STAFF_READ
    write_roles = HR_WRITE

    def get_queryset(self):
        qs = CareerEvent.objects.select_related(
            "employee",
            "created_by",
            "from_assignment__position__org_unit__campus",
            "to_position__org_unit__campus",
            "from_grade__scale",
            "to_grade__scale",
        ).prefetch_related("letters")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        employee = self.request.query_params.get("employee")
        return qs.filter(employee_id=employee) if employee else qs

    @extend_schema(
        request=RecordChangeSerializer,
        responses={201: CareerEventSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Record a transfer, promotion, increment, acting appointment or confirmation",
    )
    def create(self, request):
        data = RecordChangeSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        if not campus_in_scope(request.user, data.validated_data["employee"].campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        try:
            event = careers.record_change(request, **data.validated_data)
        except careers.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(self.get_queryset().get(pk=event.pk)).data, status=201)

    @extend_schema(
        request=CancelSerializer,
        responses={200: CareerEventSerializer, 400: ErrorSerializer},
        summary="Cancel a change that has not taken effect",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        event = self.get_object()
        if not campus_in_scope(request.user, event.employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        data = CancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            careers.cancel(request, event, data.validated_data["reason"])
        except careers.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(event).data)
