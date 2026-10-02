"""The incident register (item 1.16): anyone reports; HR keeps the register; injuries are for HR alone.

The register is read by HR, the Principal, supervisors and the auditor, each on the campuses they work with.
What an injury was, its treatment and the time off work are read only by those who keep the register.
"""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.serializers import ErrorSerializer, InScope
from iam.models import Role
from iam.permissions import SelfServicePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from incidents import duties as rules
from incidents import services
from incidents.models import Action, Incident, Notice, Person
from org.models import Campus, OrgUnit
from people.models import Employee
from people.views import HR_WRITE

KEEPERS = HR_WRITE  # keep the register and read injuries
REGISTER_READ = HR_WRITE + (Role.PRINCIPAL, Role.SUPERVISOR, Role.AUDITOR)
HEALTH = (
    "injury",
    "treatment",
    "treatment_name",
    "off_work_from",
    "back_at_work_on",
    "days_off",
    "nis_form_on",
)


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


def _keeper(serializer) -> bool:
    request = serializer.context.get("request")
    return request is not None and has_role(request.user, *KEEPERS)


class IncidentPersonSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name", read_only=True)
    who_name = serializers.CharField(source="get_who_display", read_only=True)
    injury = serializers.CharField(read_only=True, allow_null=True)
    treatment = serializers.CharField(read_only=True, allow_null=True)
    treatment_name = serializers.SerializerMethodField()
    off_work_from = serializers.DateField(read_only=True, allow_null=True)
    back_at_work_on = serializers.DateField(read_only=True, allow_null=True)
    days_off = serializers.SerializerMethodField(help_text="Days kept from full wages so far")
    nis_form_on = serializers.DateField(read_only=True, allow_null=True)

    class Meta:
        model = Person
        fields = (
            "id",
            "who",
            "who_name",
            "employee",
            "name",
            "injury",
            "treatment",
            "treatment_name",
            "off_work_from",
            "back_at_work_on",
            "days_off",
            "died_on",
            "nis_form_on",
        )
        read_only_fields = fields

    def get_treatment_name(self, person) -> str | None:
        return person.get_treatment_display() or None

    def get_days_off(self, person) -> int | None:
        return rules.days_off(person, self.context["today"]) if person.off_work_from else None

    def to_representation(self, person):
        data = super().to_representation(person)
        if not _keeper(self):
            data.update(dict.fromkeys(HEALTH))  # health information: for those who keep the register
        return data


class IncidentNoticeSerializer(serializers.ModelSerializer):
    duty_name = serializers.CharField(source="get_duty_display", read_only=True)
    recipient_name = serializers.CharField(source="get_recipient_display", read_only=True)
    recorded_by = serializers.SerializerMethodField()

    class Meta:
        model = Notice
        fields = (
            "id",
            "duty",
            "duty_name",
            "recipient",
            "recipient_name",
            "person",
            "sent_on",
            "how",
            "their_reference",
            "recorded_by",
        )
        read_only_fields = fields

    def get_recorded_by(self, notice) -> str | None:
        return _name(notice.created_by)


class DueToSerializer(serializers.Serializer):
    recipient = serializers.ChoiceField(choices=Notice.Recipient.choices)
    recipient_name = serializers.CharField()
    sent_on = serializers.DateField(allow_null=True)


class DueSerializer(serializers.Serializer):
    duty = serializers.ChoiceField(choices=Notice.Duty.choices)
    duty_name = serializers.CharField()
    section = serializers.CharField(help_text="The section of the Occupational Safety and Health Act")
    person = serializers.IntegerField(allow_null=True)
    person_name = serializers.CharField(allow_null=True)
    due_on = serializers.DateField()
    overdue = serializers.BooleanField()
    to = DueToSerializer(many=True)


class IncidentActionSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Action
        fields = ("id", "what", "owner", "owner_name", "due_on", "done_on", "done_note", "overdue")
        read_only_fields = fields

    def get_overdue(self, item) -> bool:
        return item.done_on is None and self.context["today"] > item.due_on


class IncidentListSerializer(serializers.ModelSerializer):
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True, allow_null=True)
    people_hurt = serializers.SerializerMethodField()
    notices_overdue = serializers.SerializerMethodField(help_text="A notice the Act requires is late")

    class Meta:
        model = Incident
        fields = (
            "id",
            "reference",
            "kind",
            "kind_name",
            "occurred_at",
            "campus",
            "campus_name",
            "org_unit",
            "org_unit_name",
            "place",
            "state",
            "state_name",
            "people_hurt",
            "notices_overdue",
        )
        read_only_fields = fields

    def get_people_hurt(self, incident) -> int:
        return len(incident.people.all())

    def get_notices_overdue(self, incident) -> bool:
        today = self.context["today"]
        return any(due.overdue(today) for due in rules.duties(incident, today))


class IncidentSerializer(IncidentListSerializer):
    reported_by = serializers.SerializerMethodField()
    investigated_by = serializers.SerializerMethodField()
    closed_by = serializers.SerializerMethodField()
    people = IncidentPersonSerializer(many=True, read_only=True)
    notices = IncidentNoticeSerializer(many=True, read_only=True)
    actions = IncidentActionSerializer(many=True, read_only=True)
    duties = serializers.SerializerMethodField()
    outstanding = serializers.SerializerMethodField(help_text="What is left to do before it is closed")

    class Meta(IncidentListSerializer.Meta):
        fields = IncidentListSerializer.Meta.fields + (
            "industrial",
            "description",
            "immediate_action",
            "reported_by",
            "created_at",
            "cause",
            "investigated_on",
            "investigated_by",
            "closed_on",
            "closed_by",
            "people",
            "notices",
            "duties",
            "actions",
            "outstanding",
        )
        read_only_fields = fields

    def get_reported_by(self, incident) -> str | None:
        return _name(incident.created_by)

    def get_investigated_by(self, incident) -> str | None:
        return _name(incident.investigated_by)

    def get_closed_by(self, incident) -> str | None:
        return _name(incident.closed_by)

    @extend_schema_field(DueSerializer(many=True))
    def get_duties(self, incident) -> list:
        today = self.context["today"]
        return [
            {
                "duty": due.duty,
                "duty_name": Notice.Duty(due.duty).label,
                "section": due.section,
                "person": due.person.pk if due.person else None,
                "person_name": due.person.display_name if due.person else None,
                "due_on": due.due_on,
                "overdue": due.overdue(today),
                "to": [
                    {
                        "recipient": r,
                        "recipient_name": Notice.Recipient(r).label,
                        "sent_on": due.sent[r].sent_on if r in due.sent else None,
                    }
                    for r in due.recipients
                ],
            }
            for due in rules.duties(incident, today)
        ]

    def get_outstanding(self, incident) -> list[str]:
        # Who is still off work, and their NIS claim, are for those who keep the register.
        return rules.outstanding(incident, self.context["today"], health=_keeper(self))


class OwnInjurySerializer(serializers.ModelSerializer):
    treatment_name = serializers.CharField(source="get_treatment_display", read_only=True)

    class Meta:
        model = Person
        fields = ("injury", "treatment_name", "off_work_from", "back_at_work_on", "nis_form_on")
        read_only_fields = fields


class MyIncidentSerializer(serializers.ModelSerializer):
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    reported_by_me = serializers.SerializerMethodField()
    my_injury = serializers.SerializerMethodField(
        help_text="What is recorded of my own injury, if I was hurt"
    )

    class Meta:
        model = Incident
        fields = (
            "id",
            "reference",
            "kind",
            "kind_name",
            "occurred_at",
            "campus_name",
            "place",
            "description",
            "state",
            "state_name",
            "reported_by_me",
            "my_injury",
        )
        read_only_fields = fields

    def get_reported_by_me(self, incident) -> bool:
        return incident.created_by_id == self.context["request"].user.pk

    @extend_schema_field(OwnInjurySerializer(allow_null=True))
    def get_my_injury(self, incident):
        me = self.context["request"].user.pk
        own = [p for p in incident.people.all() if p.employee is not None and p.employee.user_id == me]
        return OwnInjurySerializer(own[0]).data if own else None


class MyActionSerializer(serializers.ModelSerializer):
    reference = serializers.CharField(source="incident.reference", read_only=True)
    place = serializers.CharField(source="incident.place", read_only=True)
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Action
        fields = ("id", "reference", "place", "what", "due_on", "done_on", "overdue")
        read_only_fields = fields

    def get_overdue(self, item) -> bool:
        return item.done_on is None and self.context["today"] > item.due_on


class IncidentReportSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Incident.Kind.choices)
    occurred_at = serializers.DateTimeField()
    campus = serializers.PrimaryKeyRelatedField(queryset=Campus.objects.all())
    org_unit = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.all(), required=False, allow_null=True
    )
    place = serializers.CharField(max_length=120)
    industrial = serializers.BooleanField(required=False, default=False)
    description = serializers.CharField()
    immediate_action = serializers.CharField(required=False, allow_blank=True, default="")
    hurt = serializers.BooleanField(required=False, default=False, help_text="I was hurt myself")
    injury = serializers.CharField(required=False, allow_blank=True, default="", help_text="My injury")


class IncidentCorrectionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Incident.Kind.choices, required=False)
    occurred_at = serializers.DateTimeField(required=False)
    org_unit = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.all(), required=False, allow_null=True
    )
    place = serializers.CharField(max_length=120, required=False)
    industrial = serializers.BooleanField(required=False)
    description = serializers.CharField(required=False)
    immediate_action = serializers.CharField(required=False, allow_blank=True)


class PersonDetailsSerializer(serializers.Serializer):
    injury = serializers.CharField(required=False, allow_blank=True)
    treatment = serializers.ChoiceField(choices=Person.Treatment.choices, required=False, allow_blank=True)
    off_work_from = serializers.DateField(required=False, allow_null=True)
    back_at_work_on = serializers.DateField(required=False, allow_null=True)
    died_on = serializers.DateField(required=False, allow_null=True)
    nis_form_on = serializers.DateField(required=False, allow_null=True)


class PersonInputSerializer(PersonDetailsSerializer):
    who = serializers.ChoiceField(choices=Person.Who.choices)
    employee = InScope(Employee, required=False, allow_null=True, help_text="When a member of staff")
    name = serializers.CharField(max_length=120, required=False, allow_blank=True, help_text="Anyone else")


class NoticeInputSerializer(serializers.Serializer):
    duty = serializers.ChoiceField(choices=Notice.Duty.choices)
    recipient = serializers.ChoiceField(choices=Notice.Recipient.choices)
    person = serializers.IntegerField(required=False, allow_null=True, help_text="Who it is about, if anyone")
    sent_on = serializers.DateField()
    how = serializers.CharField(max_length=80)
    their_reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class InvestigationSerializer(serializers.Serializer):
    cause = serializers.CharField(error_messages={"blank": "Say what the investigation found."})
    investigated_on = serializers.DateField()


class ActionInputSerializer(serializers.Serializer):
    what = serializers.CharField()
    owner = InScope(Employee, help_text="Who does it")
    due_on = serializers.DateField()


class ActionDoneSerializer(serializers.Serializer):
    done_on = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


def _refused(exc: services.Refused) -> Response:
    code = status.HTTP_409_CONFLICT if exc.code in services.CONFLICTS else status.HTTP_400_BAD_REQUEST
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


def _context(request) -> dict:
    return {"request": request, "today": timezone.localdate()}


@extend_schema(
    parameters=[
        OpenApiParameter("state", str, enum=[s.value for s in Incident.State]),
        OpenApiParameter("kind", str, enum=[k.value for k in Incident.Kind]),
        OpenApiParameter("campus", int),
    ]
)
class IncidentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The register, for the roles that read it on their campuses. Anyone may report an incident."""

    queryset = Incident.objects.none()
    serializer_class = IncidentSerializer
    permission_classes = [SelfServicePermission]
    lookup_value_regex = r"\d+"

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **_context(self.request)}

    def get_serializer_class(self):
        return IncidentListSerializer if self.action == "list" else IncidentSerializer

    def get_queryset(self):
        user = self.request.user
        if not has_role(user, *REGISTER_READ):
            return Incident.objects.none()
        qs = scope_queryset(user, Incident.objects.all(), "campus").select_related(
            "campus", "org_unit", "created_by", "investigated_by", "closed_by"
        )
        qs = qs.prefetch_related("people__employee", "notices__created_by", "actions__owner")
        params = self.request.query_params
        for key in ("state", "kind", "campus"):
            if params.get(key):
                qs = qs.filter(**{key: params[key]})
        return qs

    def list(self, request, *args, **kwargs):
        if not has_role(request.user, *REGISTER_READ):
            self.permission_denied(request, message="The register is kept by Human Resources.")
        return super().list(request, *args, **kwargs)

    def _answer(self, incident, code=status.HTTP_200_OK) -> Response:
        fresh = self.get_queryset().get(pk=incident.pk)
        return Response(IncidentSerializer(fresh, context=self.get_serializer_context()).data, status=code)

    def _kept(self, request):
        incident = self.get_object()
        if not has_role(request.user, *KEEPERS) or not campus_in_scope(request.user, incident.campus_id):
            self.permission_denied(request, message="Human Resources keeps the register.")
        return incident

    @extend_schema(
        request=IncidentReportSerializer,
        responses={201: MyIncidentSerializer, 400: ErrorSerializer},
        summary="Report an accident, a near miss, a dangerous occurrence or an occupational disease",
    )
    def create(self, request):
        data = IncidentReportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            incident = services.report(request, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        fresh = services.mine(request.user).prefetch_related("people__employee").get(pk=incident.pk)
        answer = MyIncidentSerializer(fresh, context=_context(request)).data
        return Response(answer, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=IncidentCorrectionSerializer,
        responses={200: IncidentSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Correct the report",
    )
    def partial_update(self, request, pk=None):
        incident = self._kept(request)
        data = IncidentCorrectionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.correct(request, incident, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(incident)

    @extend_schema(responses=MyIncidentSerializer(many=True), summary="What I reported, or was hurt in")
    @action(detail=False, methods=["get"], pagination_class=None)
    def mine(self, request):
        qs = services.mine(request.user).prefetch_related("people__employee")
        return Response(MyIncidentSerializer(qs, many=True, context=_context(request)).data)

    @extend_schema(
        request=PersonInputSerializer,
        responses={200: IncidentSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Record someone hurt or made ill",
    )
    @action(detail=True, methods=["post"])
    def people(self, request, pk=None):
        incident = self._kept(request)
        data = PersonInputSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        try:
            services.add_person(request, incident, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(incident)

    @extend_schema(
        request=PersonDetailsSerializer,
        responses={200: IncidentSerializer, 400: ErrorSerializer},
        summary="Correct what is known of someone hurt; a death or a return to work may need a notice",
    )
    @action(detail=True, methods=["patch"], url_path=r"people/(?P<person_id>\d+)")
    def person(self, request, pk=None, person_id=None):
        incident = self._kept(request)
        person = incident.people.filter(pk=person_id).first()
        if person is None:
            return Response({"code": "not_found", "detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = PersonDetailsSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        try:
            services.change_person(request, incident, person, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(incident)

    @extend_schema(
        request=NoticeInputSerializer,
        responses={200: IncidentSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Record a notice sent under the Occupational Safety and Health Act",
    )
    @action(detail=True, methods=["post"])
    def notices(self, request, pk=None):
        incident = self._kept(request)
        data = NoticeInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        about = values.pop("person", None)
        person = incident.people.filter(pk=about).first() if about is not None else None
        if about is not None and person is None:
            return _refused(services.Refused("not_due", "That notice is not one this incident needs."))
        try:
            services.record_notice(request, incident, person=person, **values)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(incident)

    @extend_schema(
        request=InvestigationSerializer,
        responses={200: IncidentSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Record what the investigation found",
    )
    @action(detail=True, methods=["post"])
    def investigation(self, request, pk=None):
        incident = self._kept(request)
        data = InvestigationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.investigate(request, incident, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(incident)

    @extend_schema(
        request=ActionInputSerializer,
        responses={200: IncidentSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Give someone an action, so it does not happen again",
    )
    @action(detail=True, methods=["post"])
    def actions(self, request, pk=None):
        incident = self._kept(request)
        data = ActionInputSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        try:
            services.add_action(request, incident, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(incident)

    @extend_schema(
        request=None,
        responses={200: IncidentSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Close it, once nothing is left to do",
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        incident = self._kept(request)
        try:
            services.close(request, incident)
        except services.Refused as exc:
            return _refused(exc)
        return self._answer(incident)


class ActionViewSet(viewsets.GenericViewSet):
    """Actions given to me, and marking one done: by its owner, or by HR."""

    queryset = Action.objects.none()
    serializer_class = MyActionSerializer
    permission_classes = [SelfServicePermission]
    lookup_value_regex = r"\d+"

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **_context(self.request)}

    def get_queryset(self):
        return Action.objects.select_related("incident", "owner")

    @extend_schema(responses=MyActionSerializer(many=True), summary="Actions given to me, not yet done")
    @action(detail=False, methods=["get"], pagination_class=None)
    def mine(self, request):
        qs = self.get_queryset().filter(owner__user=request.user, done_on__isnull=True)
        return Response(MyActionSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @extend_schema(
        request=ActionDoneSerializer,
        responses={200: MyActionSerializer, 400: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
        summary="Mark an action done",
    )
    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        item = self.get_queryset().filter(pk=pk).first()
        user = request.user
        allowed = item is not None and (
            item.owner.user_id == user.pk
            or (has_role(user, *KEEPERS) and campus_in_scope(user, item.incident.campus_id))
        )
        if not allowed:
            return Response({"code": "not_found", "detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = ActionDoneSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.finish_action(request, item, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return Response(MyActionSerializer(item, context=self.get_serializer_context()).data)
