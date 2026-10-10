"""H-W01 endpoints: vacancies, candidates and applications, interview scheduling, hires, and the
unauthenticated reference-and-code status check (item 1.47's own pattern, read by ``recruitment.reference``).
"""

import hmac
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, record_event, snapshot
from core.net import client_ip
from core.serializers import ErrorSerializer
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import has_role, scope_queryset
from recruitment import reference, services
from recruitment.models import Application, ApplicationCheckLog, Candidate, Hire, Interview, Vacancy
from recruitment.serializers import (
    ApplicationCheckSerializer,
    ApplicationSerializer,
    CandidateSerializer,
    CheckedApplicationSerializer,
    HireSerializer,
    InterviewSerializer,
    TransitionSerializer,
    VacancySerializer,
)
from recruitment.workflow import APPLICATION, WorkflowError

HR = (Role.HR_OFFICER, Role.HR_MANAGER, Role.ADMINISTRATOR)
BROAD_READ = HR + (Role.SUPERVISOR, Role.PRINCIPAL)
NO_MATCH = "No application matches that reference and code. Check them against the email you were sent."


def _refuse(code: str, detail: str, http_status: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"code": code, "detail": detail}, status=http_status)


class VacancyViewSet(AuditedModelViewSet):
    queryset = Vacancy.objects.select_related("position", "position__grade", "position__org_unit__campus")
    serializer_class = VacancySerializer
    read_roles = BROAD_READ
    write_roles = HR

    def get_queryset(self):
        return scope_queryset(
            self.request.user, super().get_queryset(), campus_field="position__org_unit__campus"
        )


class CandidateViewSet(AuditedModelViewSet):
    """Candidates are created with their first application (``ApplicationViewSet``); this endpoint is for
    correcting their own details afterwards, and reading them. Not deleted: a decided application keeps
    its history, and the retention date (set on decision) is how old, unsuccessful records are dealt with."""

    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer
    read_roles = BROAD_READ
    write_roles = HR

    def create(self, request, *args, **kwargs):
        detail = "Create a candidate through their application."
        return _refuse("not_allowed", detail, status.HTTP_405_METHOD_NOT_ALLOWED)

    def destroy(self, request, *args, **kwargs):
        detail = "Candidate records are not deleted here."
        return _refuse("not_allowed", detail, status.HTTP_405_METHOD_NOT_ALLOWED)


class ApplicationViewSet(AuditedModelViewSet):
    queryset = Application.objects.select_related("candidate", "vacancy", "vacancy__position")
    serializer_class = ApplicationSerializer
    read_roles = BROAD_READ
    write_roles = HR

    def get_queryset(self):
        qs = scope_queryset(
            self.request.user, super().get_queryset(), campus_field="vacancy__position__org_unit__campus"
        )
        vacancy = self.request.query_params.get("vacancy")
        if vacancy:
            qs = qs.filter(vacancy_id=vacancy)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        return qs

    def destroy(self, request, *args, **kwargs):
        return _refuse("not_allowed", "Use withdraw or reject instead of deleting an application.")

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record(self.request, "create", instance, before=None, after=snapshot(instance))
        services.send_submission_receipt(instance)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        instance = self.get_object()
        body = TransitionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if body.validated_data["action"] == "schedule_interview":
            # This action moves the application only as a side effect of creating the Interview row
            # (InterviewViewSet.create), so the two can never go out of step; it is not a plain transition.
            detail = "Schedule the interview through the interviews endpoint."
            return _refuse("use_interview_endpoint", detail)
        try:
            APPLICATION.apply(
                instance,
                body.validated_data["action"],
                request=request,
                comment=body.validated_data["comment"],
            )
        except WorkflowError as exc:
            code = status.HTTP_403_FORBIDDEN if exc.code == "forbidden_actor" else status.HTTP_409_CONFLICT
            return Response({"code": exc.code, "detail": str(exc)}, status=code)
        return Response(self.get_serializer(instance).data)


class InterviewViewSet(AuditedModelViewSet):
    queryset = Interview.objects.select_related("application", "application__candidate", "interviewer")
    serializer_class = InterviewSerializer
    read_roles = BROAD_READ
    write_roles = HR

    def get_queryset(self):
        return scope_queryset(
            self.request.user,
            super().get_queryset(),
            campus_field="application__vacancy__position__org_unit__campus",
        )

    def update(self, request, *args, **kwargs):
        return _refuse("not_allowed", "Use the reschedule action to change the time of an interview.")

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return _refuse("not_allowed", "Use the cancel action instead of deleting an interview.")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.validated_data["application"]
        if application.state != Application.State.SHORTLISTED:
            return _refuse(
                "invalid_transition",
                "Shortlist the candidate before scheduling an interview.",
            )
        instance = Interview(
            application=application,
            interviewer=serializer.validated_data["interviewer"],
            starts_at=serializer.validated_data["starts_at"],
            ends_at=serializer.validated_data["ends_at"],
            location=serializer.validated_data.get("location", ""),
            ics_uid=services.new_ics_uid(),
            created_by=request.user,
            updated_by=request.user,
        )
        try:
            with transaction.atomic():
                instance.save()
                APPLICATION.apply(application, "schedule_interview", request=request)
        except IntegrityError:
            return _refuse("slot_taken", "That interviewer already has an interview booked over this time.")
        except WorkflowError as exc:
            return _refuse(exc.code, str(exc))
        record(request, "create", instance, before=None, after=snapshot(instance))
        instance.invited_at = timezone.now()
        instance.save(update_fields=["invited_at"])
        services.send_interview_invite(instance)
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        instance = self.get_object()
        serializer = InterviewSerializer(
            instance, data=request.data, partial=True, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        before = snapshot(instance)
        instance.starts_at = serializer.validated_data.get("starts_at", instance.starts_at)
        instance.ends_at = serializer.validated_data.get("ends_at", instance.ends_at)
        instance.location = serializer.validated_data.get("location", instance.location)
        instance.state = Interview.State.SCHEDULED
        instance.sequence += 1
        instance.updated_by = request.user
        try:
            with transaction.atomic():
                instance.save()
        except IntegrityError:
            return _refuse("slot_taken", "That interviewer already has an interview booked over this time.")
        record(request, "reschedule", instance, before=before, after=snapshot(instance))
        instance.invited_at = timezone.now()
        instance.save(update_fields=["invited_at"])
        services.send_interview_invite(instance)
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        instance = self.get_object()
        before = snapshot(instance)
        instance.state = Interview.State.CANCELLED
        instance.sequence += 1
        instance.updated_by = request.user
        instance.save(update_fields=["state", "sequence", "updated_by", "updated_at"])
        record(request, "cancel", instance, before=before, after=snapshot(instance))
        services.send_interview_invite(instance, cancelled=True)
        return Response(self.get_serializer(instance).data)


class HireViewSet(viewsets.ReadOnlyModelViewSet):
    """Hires are created only by an accepted offer (``recruitment.workflow``); HR records a start date
    here. The ``employee`` link is left for a later onboarding build (H-W02) to fill in (item H-W01)."""

    queryset = Hire.objects.select_related("candidate", "vacancy", "application")
    serializer_class = HireSerializer
    permission_classes = [RolePermission]
    read_roles = BROAD_READ

    def get_queryset(self):
        return scope_queryset(
            self.request.user, super().get_queryset(), campus_field="vacancy__position__org_unit__campus"
        )

    @action(detail=True, methods=["patch"])
    def start_date(self, request, pk=None):
        if not has_role(request.user, *HR):
            detail = "Only Human Resources may set a start date."
            return _refuse("forbidden", detail, status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        before = snapshot(instance)
        instance.start_date = request.data.get("start_date") or None
        instance.notes = request.data.get("notes", instance.notes)
        instance.updated_by = request.user
        instance.save(update_fields=["start_date", "notes", "updated_by", "updated_at"])
        record(request, "update", instance, before=before, after=snapshot(instance))
        return Response(self.get_serializer(instance).data)


def _blocked(address, ref: str) -> bool:
    since = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    failures = ApplicationCheckLog.objects.filter(matched=False, at__gte=since)
    limit = settings.RECRUITMENT_CHECK_FAILURES
    if address is not None and failures.filter(source_ip=address).count() >= limit:
        return True
    return failures.filter(reference__iexact=ref).count() >= limit


@extend_schema(
    request=ApplicationCheckSerializer,
    responses={200: CheckedApplicationSerializer, 429: ErrorSerializer},
    summary="Check an application's progress, by its reference and code, without signing in",
    auth=[],
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def check_application(request):
    """Open to any candidate holding their reference and code (mirrors ``letters.check_letter``, 1.47).
    A wrong code and an unknown reference get the same answer, so the page never confirms which
    references exist."""
    data = ApplicationCheckSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    ref = data.validated_data["reference"].strip()[:40]
    address = client_ip(request)
    if _blocked(address, ref):
        return Response(
            {
                "code": "too_many_attempts",
                "detail": "Too many wrong codes have been tried. Try again later.",
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    application = Application.objects.filter(reference__iexact=ref).select_related("vacancy").first()
    given = reference.plain(data.validated_data["code"]).encode()
    matched = bool(
        application is not None
        and application.check_code
        and hmac.compare_digest(reference.plain(application.check_code).encode(), given)
    )
    ApplicationCheckLog.objects.create(
        reference=ref, application=application if matched else None, matched=matched, source_ip=address
    )
    empty = dict.fromkeys(("reference", "vacancy", "state", "state_label", "submitted_at"))
    if not matched:
        return Response({"found": False, "detail": NO_MATCH, **empty})
    record_event(
        request, "application_checked", "recruitment.application", after={"application": application.pk}
    )
    return Response(
        {
            "found": True,
            "detail": "Found. This is the current stage of your application.",
            "reference": application.reference,
            "vacancy": application.vacancy.title,
            "state": application.state,
            "state_label": application.get_state_display(),
            "submitted_at": application.created_at,
        }
    )


router = DefaultRouter()
router.register("vacancies", VacancyViewSet)
router.register("candidates", CandidateViewSet)
router.register("applications", ApplicationViewSet)
router.register("interviews", InterviewViewSet)
router.register("hires", HireViewSet)

# Checking an application's progress is open to anyone with the reference and code (item 1.47's own
# pattern), so it comes before the register's own paths.
urlpatterns = [path("check/", check_application, name="application-check"), *router.urls]

__all__ = ["urlpatterns", "viewsets"]
