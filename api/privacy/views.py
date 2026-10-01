"""Privacy rights (item 1.31): the notice and its acknowledgement, a person's own record, and corrections.

Everyone signed in reads the notice in force, acknowledges it and fetches their own record. The HR Manager
and administrators write and publish the notice and produce a record for a request made on paper. HR
officers answer correction requests for staff on their campus, never one about themselves.
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from audit.services import record
from core.net import client_ip
from core.serializers import ErrorSerializer, InScope
from iam.models import Role
from iam.permissions import RolePermission, SelfServicePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from notifications.models import Notification
from notifications.services import notify, users_with_role
from people.models import Employee
from privacy import services
from privacy.models import CorrectionRequest, NoticeAcknowledgement, PrivacyNotice

NOTICE_WRITE = (Role.ADMINISTRATOR, Role.HR_MANAGER)
CORRECTION_DECIDE = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)
RECORD_FOR_REQUEST = (Role.ADMINISTRATOR, Role.HR_MANAGER)


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


class NoticeSerializer(serializers.ModelSerializer):
    published_by = serializers.SerializerMethodField()

    class Meta:
        model = PrivacyNotice
        fields = ("id", "version", "title", "body", "created_at", "published_at", "published_by")
        read_only_fields = ("id", "version", "created_at", "published_at", "published_by")

    def get_published_by(self, notice) -> str | None:
        return _name(notice.published_by)

    def validate(self, attrs):
        if self.instance is not None and self.instance.published_at is not None:
            raise serializers.ValidationError(
                "A published notice never changes: write a new version instead."
            )
        return attrs


class CurrentNoticeSerializer(serializers.Serializer):
    notice = NoticeSerializer(allow_null=True)
    acknowledged = serializers.BooleanField(help_text="I have acknowledged this version")


class AcknowledgeSerializer(serializers.Serializer):
    version = serializers.IntegerField()


class CorrectionSerializer(serializers.ModelSerializer):
    employee = InScope(Employee, required=False, help_text="Leave out to ask about your own record")
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True)
    subject_name = serializers.CharField(source="get_subject_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    decided_by_name = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = CorrectionRequest
        fields = (
            "id",
            "employee",
            "employee_name",
            "employee_no",
            "subject",
            "subject_name",
            "wrong",
            "should_be",
            "state",
            "state_name",
            "due_by",
            "overdue",
            "created_at",
            "decided_by_name",
            "decided_at",
            "decision_note",
            "is_mine",
        )
        read_only_fields = ("state", "due_by", "created_at", "decided_at", "decision_note")

    def get_decided_by_name(self, request_) -> str | None:
        return _name(request_.decided_by)

    def get_overdue(self, request_) -> bool:
        return request_.state == CorrectionRequest.State.OPEN and request_.due_by < timezone.localdate()

    def get_is_mine(self, request_) -> bool:
        user = self.context["request"].user
        return request_.employee.user_id == user.pk


class DecisionSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["corrected", "declined"])
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)


@extend_schema(
    responses=CurrentNoticeSerializer, summary="The privacy notice in force, and whether I have read it"
)
@api_view(["GET"])
@permission_classes([SelfServicePermission])
def current_notice_view(request):
    notice = services.current_notice()
    acknowledged = (
        bool(notice) and NoticeAcknowledgement.objects.filter(notice=notice, user=request.user).exists()
    )
    return Response(CurrentNoticeSerializer({"notice": notice, "acknowledged": acknowledged}).data)


@extend_schema(
    request=AcknowledgeSerializer,
    responses={200: CurrentNoticeSerializer, 409: ErrorSerializer},
    summary="Record that I have read the privacy notice",
)
@api_view(["POST"])
@permission_classes([SelfServicePermission])
def acknowledge_view(request):
    data = AcknowledgeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    notice = services.current_notice()
    if notice is None or notice.version != data.validated_data["version"]:
        return Response(
            {"code": "not_current", "detail": "That is not the notice in force. Read the current one."},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        with transaction.atomic():
            NoticeAcknowledgement.objects.create(
                notice=notice, user=request.user, source_ip=client_ip(request)
            )
            record(request, "notice_acknowledged", notice, after={"version": notice.version})
    except IntegrityError:
        pass  # already read: nothing more to record
    return Response(CurrentNoticeSerializer({"notice": notice, "acknowledged": True}).data)


class OwnRecordSerializer(serializers.Serializer):
    produced_at = serializers.DateTimeField()
    about = serializers.CharField()
    account = serializers.DictField(allow_null=True)
    staff_record = serializers.DictField(allow_null=True)


@extend_schema(responses=OwnRecordSerializer, summary="Everything the system holds about me (audited)")
@api_view(["GET"])
@permission_classes([SelfServicePermission])
def own_record_view(request):
    data = services.record_of(request.user)
    record(request, "record_viewed", request.user, after={"sections": sorted(data["staff_record"] or [])})
    return Response(data)


class NoticeViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """Versions of the privacy notice, written and published by the HR Manager or an administrator."""

    permission_classes = [RolePermission]
    read_roles = NOTICE_WRITE + (Role.AUDITOR,)
    write_roles = NOTICE_WRITE
    serializer_class = NoticeSerializer
    queryset = PrivacyNotice.objects.select_related("published_by")
    http_method_names = ["get", "post", "patch", "head", "options"]

    @transaction.atomic
    def perform_create(self, serializer):
        version = (PrivacyNotice.objects.aggregate(top=Max("version"))["top"] or 0) + 1
        notice = serializer.save(version=version, created_by=self.request.user)
        record(self.request, "notice_drafted", notice, after={"version": version, "title": notice.title})

    @transaction.atomic
    def perform_update(self, serializer):
        notice = serializer.save()
        record(
            self.request, "notice_edited", notice, after={"version": notice.version, "title": notice.title}
        )

    @extend_schema(
        request=None, responses={200: NoticeSerializer, 409: ErrorSerializer}, summary="Publish a draft"
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        notice = self.get_object()
        if notice.published_at is not None:
            return Response(
                {"code": "published", "detail": "This version is already published."},
                status=status.HTTP_409_CONFLICT,
            )
        newest = services.current_notice()
        if newest is not None and newest.version > notice.version:
            return Response(
                {
                    "code": "older",
                    "detail": f"Version {newest.version} is already in force; write a new draft.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            notice.published_at = timezone.now()
            notice.published_by = request.user
            notice.save(update_fields=["published_at", "published_by"])
            record(request, "notice_published", notice, after={"version": notice.version})
        return Response(self.get_serializer(notice).data)


@extend_schema(
    parameters=[OpenApiParameter("state", OpenApiTypes.STR, enum=["open", "corrected", "declined"])]
)
class CorrectionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Requests to correct a record. A person sees their own; HR sees those of the staff on their campuses."""

    permission_classes = [SelfServicePermission]
    serializer_class = CorrectionSerializer
    queryset = CorrectionRequest.objects.none()

    def get_queryset(self):
        user = self.request.user
        requests_ = CorrectionRequest.objects.select_related("employee", "decided_by")
        own = requests_.filter(employee__user=user)
        if has_role(user, *CORRECTION_DECIDE):
            requests_ = (scope_queryset(user, requests_, campus_field="employee__campus") | own).distinct()
        else:
            requests_ = own
        state = self.request.query_params.get("state")
        if state:
            requests_ = requests_.filter(state=state)
        return requests_.order_by("state", "due_by", "-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        own = getattr(user, "employee", None)
        employee = serializer.validated_data.get("employee") or own
        if employee is None:
            raise serializers.ValidationError({"employee": ["Your account is not linked to a staff record."]})
        if employee != own and not (
            has_role(user, *CORRECTION_DECIDE) and campus_in_scope(user, employee.campus_id)
        ):
            self.permission_denied(self.request, message="You may ask only about your own record.")
        days = settings.PRIVACY_RESPONSE_DAYS
        with transaction.atomic():
            correction = serializer.save(
                employee=employee,
                due_by=timezone.localdate() + timedelta(days=days),
                created_by=user,
                updated_by=user,
            )
            record(
                self.request,
                "correction_requested",
                correction,
                after={
                    "subject": correction.subject,
                    "wrong": correction.wrong,
                    "should_be": correction.should_be,
                },
            )
        handlers = {
            person
            for code in CORRECTION_DECIDE
            for person in users_with_role(code, campus=employee.campus)
            if person.pk != getattr(employee.user, "pk", None)
        }
        notify(
            handlers,
            title=f"Correction requested: {employee.full_name}",
            body=f"{correction.get_subject_display()}: answer by {correction.due_by:%d/%m/%Y}.",
            link="/admin/corrections",
            kind=Notification.Kind.APPROVAL,
            dedupe_key=f"correction:{correction.id}:open",
        )

    @extend_schema(
        request=DecisionSerializer,
        responses={200: CorrectionSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Answer a correction request: corrected, or not changed with the reason",
    )
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        if not has_role(request.user, *CORRECTION_DECIDE):
            self.permission_denied(request, message="Only Human Resources answers correction requests.")
        correction = self.get_object()
        if correction.employee.user_id == request.user.pk:
            self.permission_denied(
                request, message="Someone else in Human Resources answers a request about you."
            )
        if not campus_in_scope(request.user, correction.employee.campus_id):
            self.permission_denied(request, message="That member of staff is not on a campus you work with.")
        if correction.state != CorrectionRequest.State.OPEN:
            return Response({"code": "decided", "detail": "This request has been answered."}, status=409)
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        note = (data.validated_data.get("note") or "").strip()
        outcome = data.validated_data["outcome"]
        if outcome == "declined" and not note:
            raise serializers.ValidationError({"note": ["Say why the record is not changed."]})
        with transaction.atomic():
            correction.state = outcome
            correction.decided_by = request.user
            correction.decided_at = timezone.now()
            correction.decision_note = note
            correction.updated_by = request.user
            correction.save()
            record(request, f"correction_{outcome}", correction, after={"note": note}, reason=note)
        words = "has been corrected" if outcome == "corrected" else "was not changed"
        notify(
            [correction.employee.user],
            title=f"Your correction request {words}",
            body=f"{correction.get_subject_display()}. {note}".strip(),
            link="/my-record",
            dedupe_key=f"correction:{correction.id}:{outcome}",
        )
        return Response(self.get_serializer(correction).data)


@extend_schema(
    responses=OwnRecordSerializer, summary="A member of staff's record, for a request made on paper (audited)"
)
@api_view(["GET"])
@permission_classes([RolePermission])
def employee_record_view(request, pk: int):
    if not has_role(request.user, *RECORD_FOR_REQUEST):
        return Response(
            {"code": "permission_denied", "detail": "Only the HR Manager or an administrator produces this."},
            status=status.HTTP_403_FORBIDDEN,
        )
    employee = scope_queryset(request.user, Employee.objects.all()).filter(pk=pk).first()
    if employee is None:
        return Response({"code": "not_found", "detail": "No such member of staff."}, status=404)
    data = services.record_of_employee(employee)
    record(request, "record_produced", employee, after={"for": "the person's request"})
    return Response(data)
