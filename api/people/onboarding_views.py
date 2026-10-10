"""Joining (item H-W02): run by HR from an accepted hire; the new hire's own record is self-service for
the steps that are naturally theirs (acknowledging and uploading the documents asked for).
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer, InScope, TimeStampedSerializer
from core.uploads import DOCUMENT, validate_upload
from iam.permissions import RolePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from people import onboarding
from people.models import Assignment, Document, Employee, Onboarding, OnboardingStep
from people.onboarding_workflow import ONBOARDING, WorkflowError
from people.views import CONFIDENTIAL_READ, HR_WRITE
from recruitment.models import Hire

# Held to the same readers as the rest of the confidential staff file (item 1.06): HR, the Principal and
# the auditor. A new hire also sees their own record, through get_queryset, whatever roles they hold.
ONBOARDING_READ = CONFIDENTIAL_READ


class OnboardingStepSerializer(TimeStampedSerializer):
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    cleared_by_name = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = OnboardingStep
        fields = (
            "id",
            "code",
            "label",
            "who",
            "state",
            "state_name",
            "note",
            "cleared_at",
            "cleared_by_name",
        )
        read_only_fields = fields

    def get_cleared_by_name(self, step) -> str | None:
        user = step.cleared_by
        return (user.get_full_name() or user.get_username()) if user else None


class OnboardingSerializer(TimeStampedSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    steps = OnboardingStepSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Onboarding
        fields = (
            "id",
            "hire",
            "employee",
            "employee_name",
            "state",
            "state_name",
            "started_on",
            "completed_at",
            "note",
            "decision_comment",
            "steps",
            "allowed_actions",
            "created_at",
        )
        read_only_fields = fields

    def get_allowed_actions(self, instance) -> list[str]:
        request = self.context.get("request")
        if request is None:
            return []
        return ONBOARDING.allowed_actions(instance, request.user)


class StartOnboardingSerializer(serializers.Serializer):
    hire = InScope(Hire, campus_field="vacancy__position__org_unit__campus")
    employee_no = serializers.CharField(max_length=20)
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=Employee.Gender.choices, default=Employee.Gender.OTHER)
    appointment_type = serializers.ChoiceField(choices=Assignment.AppointmentType.choices)
    start_date = serializers.DateField(required=False, allow_null=True)

    def validate_employee_no(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give an employee number.")
        return value


class TransitionSerializer(serializers.Serializer):
    action = serializers.CharField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class OnboardingClearStepSerializer(serializers.Serializer):
    done = serializers.BooleanField(default=True, help_text="False when the step is not needed")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


# What a new hire is asked for here; named, so ENUM_NAME_OVERRIDES (config.settings) gives it one stable
# schema name instead of colliding with Document's own, differently-scoped doc_type choices.
ONBOARDING_DOC_TYPES = (
    ("contract", "Signed contract"),
    ("id_copy", "Identification"),
    ("certificate", "Certificate"),
    ("other", "Other"),
)


class OnboardingDocumentSerializer(serializers.Serializer):
    """What a new hire (or HR, on their behalf) may upload while the "documents" step is open: a trimmed
    version of ``people.serializers.DocumentSerializer`` that asks for no classification, since one
    uploaded here is always kept confidential (item 1.06)."""

    title = serializers.CharField(max_length=160)
    doc_type = serializers.ChoiceField(choices=ONBOARDING_DOC_TYPES)
    file = serializers.FileField()

    def validate_file(self, value):
        return validate_upload(value, DOCUMENT)


def _refused(exc: onboarding.Refused) -> Response:
    code = status.HTTP_409_CONFLICT if exc.code in onboarding.CONFLICTS else status.HTTP_400_BAD_REQUEST
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


def _workflow_refused(exc: WorkflowError) -> Response:
    code = status.HTTP_403_FORBIDDEN if exc.code == "forbidden_actor" else status.HTTP_409_CONFLICT
    return Response({"code": exc.code, "detail": str(exc)}, status=code)


@extend_schema(parameters=[OpenApiParameter("employee", int, description="One member of staff")])
class OnboardingViewSet(viewsets.ReadOnlyModelViewSet):
    """HR starts and runs onboarding here; a new hire reads their own record through the same endpoint,
    whatever roles they hold (``get_queryset``), to act on the self-service steps that are theirs."""

    queryset = Onboarding.objects.none()
    serializer_class = OnboardingSerializer
    permission_classes = [RolePermission]
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def _may_act_on(self, instance) -> bool:
        """HR on their campus, or the new hire themself: the same split as every action below."""
        user = self.request.user
        if has_role(user, *HR_WRITE):
            return campus_in_scope(user, instance.employee.campus_id)
        employee = getattr(user, "employee", None)
        return employee is not None and employee.pk == instance.employee_id

    def get_queryset(self):
        qs = Onboarding.objects.select_related("employee", "employee__campus", "hire").prefetch_related(
            "steps"
        )
        user = self.request.user
        if has_role(user, *ONBOARDING_READ):
            qs = scope_queryset(user, qs, campus_field="employee__campus")
            employee = self.request.query_params.get("employee")
            return qs.filter(employee_id=employee) if employee else qs
        own = getattr(user, "employee", None)
        return qs.filter(employee=own) if own is not None else qs.none()

    @extend_schema(
        request=StartOnboardingSerializer,
        responses={201: OnboardingSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Start onboarding an accepted hire: the staff record, the first appointment, the checklist",
    )
    @action(detail=False, methods=["post"])
    def start(self, request):
        if not has_role(request.user, *HR_WRITE):
            self.permission_denied(request, message="Only Human Resources may start onboarding.")
        data = StartOnboardingSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        try:
            instance = onboarding.start_onboarding(request, **data.validated_data)
        except onboarding.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=TransitionSerializer,
        responses={
            200: OnboardingSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Move the onboarding record on: submit_documents, confirm_documents, send_back, "
        "complete or cancel",
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        instance = self.get_object()
        body = TransitionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            ONBOARDING.apply(
                instance,
                body.validated_data["action"],
                request=request,
                comment=body.validated_data["comment"],
            )
        except WorkflowError as exc:
            return _workflow_refused(exc)
        # A step may have just been closed by an on_success hook; it was read before that change.
        getattr(instance, "_prefetched_objects_cache", {}).clear()
        return Response(self.get_serializer(instance).data)

    @extend_schema(
        parameters=[
            OpenApiParameter("code", str, OpenApiParameter.PATH, description="The step, such as equipment")
        ],
        request=OnboardingClearStepSerializer,
        responses={200: OnboardingSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Close one step of the checklist: done, or not needed",
    )
    @action(detail=True, methods=["post"], url_path=r"steps/(?P<code>[a-z_]+)/clear")
    def clear(self, request, pk=None, code=None):
        if not has_role(request.user, *HR_WRITE):
            self.permission_denied(request, message="Only Human Resources closes a step.")
        instance = self.get_object()
        if not campus_in_scope(request.user, instance.employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        step = instance.steps.filter(code=code).first()
        if step is None:
            return Response(
                {"code": "not_found", "detail": "No such step."}, status=status.HTTP_404_NOT_FOUND
            )
        data = OnboardingClearStepSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            onboarding.clear_step(
                request, step, done=data.validated_data["done"], note=data.validated_data.get("note", "")
            )
        except onboarding.Refused as exc:
            return _refused(exc)
        getattr(instance, "_prefetched_objects_cache", {}).clear()  # the step just closed was read before
        return Response(self.get_serializer(instance).data)

    @extend_schema(
        request=OnboardingDocumentSerializer,
        responses={
            201: OnboardingSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Upload one of the documents asked for: files it on the employee's record (people.Document)",
    )
    @action(detail=True, methods=["post"], url_path="documents")
    def upload_document(self, request, pk=None):
        """Not ``people.views.DocumentViewSet`` (HR write only): the new hire files their own documents
        here, the same way ``leave.views.LeaveRequestViewSet.evidence`` lets an employee attach their own
        evidence without the general document endpoint's HR-only write role."""
        instance = self.get_object()
        if not self._may_act_on(instance):
            self.permission_denied(request, message="Only this new hire, or Human Resources, uploads here.")
        step = instance.steps.filter(code="documents", state=OnboardingStep.State.OPEN).first()
        if step is None:
            return _refused(onboarding.Refused("documents_step", "That step is already closed."))
        data = OnboardingDocumentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        document = Document.objects.create(
            employee=instance.employee,
            doc_type=data.validated_data["doc_type"],
            title=data.validated_data["title"],
            file=data.validated_data["file"],
            classification=Document.Classification.CONFIDENTIAL,
            created_by=request.user,
            updated_by=request.user,
        )
        record(request, "create", document, before=None, after=snapshot(document))
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: OnboardingSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Open the new hire's sign-in account and send the invitation",
    )
    @action(detail=True, methods=["post"], url_path="open-account")
    def open_account(self, request, pk=None):
        if not has_role(request.user, *HR_WRITE):
            self.permission_denied(request, message="Only Human Resources opens an account.")
        instance = self.get_object()
        if not campus_in_scope(request.user, instance.employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        try:
            onboarding.provision_account(request, instance)
        except onboarding.Refused as exc:
            return _refused(exc)
        getattr(instance, "_prefetched_objects_cache", {}).clear()  # the "account" step just closed
        return Response(self.get_serializer(instance).data)
