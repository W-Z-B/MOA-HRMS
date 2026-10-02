"""Letters (item 1.19): templates kept by the HR Manager, letters written by HR, and each person's own.

Templates are never edited in place: a change is the next version, so every letter can show the wording it
was made from. Letters are confidential records: the register is for HR, the Principal and the auditor, on
their campuses; the person a letter is for reads it under My contract.
"""

from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import RolePermission, SelfServicePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from letters import serializers, services
from letters.fields import ASK_TYPES, PAY_FIELDS, RECORD_FIELDS
from letters.models import Letter, LetterTemplate
from people.models import Document
from people.views import CONFIDENTIAL_READ, HR_WRITE, MEDICAL_READ

TEMPLATE_READ = CONFIDENTIAL_READ
TEMPLATE_WRITE = (Role.HR_MANAGER, Role.ADMINISTRATOR)


def _refused(exc: services.Refused) -> Response:
    code = status.HTTP_400_BAD_REQUEST if exc.code == "missing" else status.HTTP_409_CONFLICT
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


def _download(request, letter: Letter) -> FileResponse:
    document = letter.document
    record(request, "download", document, after={"title": document.title, "version": document.version})
    return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.download_name)


@extend_schema(
    parameters=[
        OpenApiParameter("code", str, description="Only this template"),
        OpenApiParameter("versions", str, enum=["all"], description="Every version, not only the newest"),
    ]
)
class LetterTemplateViewSet(AuditedModelViewSet):
    queryset = LetterTemplate.objects.none()
    serializer_class = serializers.LetterTemplateSerializer
    read_roles = TEMPLATE_READ
    write_roles = TEMPLATE_WRITE
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = LetterTemplate.objects.all()
        params = self.request.query_params
        if params.get("code"):
            qs = qs.filter(code=params["code"])
        if params.get("versions") != "all":
            newest = (
                LetterTemplate.objects.filter(code=OuterRef("code")).order_by("-version").values("pk")[:1]
            )
            qs = qs.filter(pk=Subquery(newest))
        return qs.order_by("name", "-version")

    @extend_schema(
        request=serializers.LetterTemplateSerializer,
        responses={201: serializers.LetterTemplateSerializer, 400: ErrorSerializer},
        summary="Save a change to a template as its next version",
    )
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        newest = self.get_object()
        data = {**request.data, "code": newest.code}
        serializer = self.get_serializer(
            data=data, context={**self.get_serializer_context(), "revising": True}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            versions = LetterTemplate.objects.select_for_update().filter(code=newest.code)
            latest = max(t.version for t in versions)
            revised = serializer.save(
                version=latest + 1,
                is_active=newest.is_active,
                created_by=request.user,
                updated_by=request.user,
            )
            record(request, "template_revised", revised, before=snapshot(newest), after=snapshot(revised))
        return Response(self.get_serializer(revised).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=serializers.InUseSerializer,
        responses={200: serializers.LetterTemplateSerializer},
        summary="Put a template out of use, or back in use (every version)",
    )
    @action(detail=True, methods=["post"], url_path="in-use")
    def in_use(self, request, pk=None):
        newest = self.get_object()
        data = serializers.InUseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        active = data.validated_data["is_active"]
        with transaction.atomic():
            LetterTemplate.objects.filter(code=newest.code).update(
                is_active=active, updated_by=request.user, updated_at=timezone.now()
            )
            newest.refresh_from_db()
            record(
                request,
                "template_restored" if active else "template_retired",
                newest,
                after={"code": newest.code},
            )
        return Response(self.get_serializer(newest).data)

    @extend_schema(responses=serializers.FieldsSerializer, summary="The fields a template may use")
    @action(detail=False, methods=["get"])
    def fields(self, request):
        return Response(
            {
                "record": [{"key": k, "label": v, "pay": k in PAY_FIELDS} for k, v in RECORD_FIELDS.items()],
                "ask_types": [{"value": k, "label": v} for k, v in ASK_TYPES.items()],
            }
        )


@extend_schema(
    parameters=[
        OpenApiParameter("employee", int, description="Letters to one member of staff"),
        OpenApiParameter("q", str, description="Part of a reference, a name or an employee number"),
        OpenApiParameter("kind", str, description="appointment, job_letter, transfer..."),
    ]
)
class LetterViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Letter.objects.none()
    serializer_class = serializers.LetterSerializer
    permission_classes = [RolePermission]
    read_roles = CONFIDENTIAL_READ
    write_roles = HR_WRITE
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        user = self.request.user
        qs = Letter.objects.select_related("employee", "template", "document", "created_by")
        qs = scope_queryset(user, qs, campus_field="employee__campus")
        if not has_role(user, *MEDICAL_READ):
            qs = qs.exclude(document__classification=Document.Classification.MEDICAL)
        params = self.request.query_params
        if params.get("employee"):
            qs = qs.filter(employee_id=params["employee"])
        if params.get("kind"):
            qs = qs.filter(template__kind=params["kind"])
        if params.get("q"):
            text = params["q"].strip()
            qs = qs.filter(
                Q(reference__icontains=text)
                | Q(employee__first_name__istartswith=text)
                | Q(employee__last_name__istartswith=text)
                | Q(employee__employee_no__istartswith=text)
            )
        return qs

    def _written(self, request):
        data = serializers.WriteLetterSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        employee = data.validated_data["employee"]
        if not campus_in_scope(request.user, employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        return (
            employee,
            data.validated_data["template"],
            data.validated_data.get("answers", {}),
            data.validated_data.get("career_event"),
        )

    @extend_schema(
        request=serializers.WriteLetterSerializer,
        responses={201: serializers.LetterSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Issue a letter: its PDF is filed in the staff record and the person is told",
    )
    def create(self, request):
        employee, template, answers, event = self._written(request)
        try:
            letter = services.issue(request, template, employee, answers, career_event=event)
        except services.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(letter).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=serializers.WriteLetterSerializer,
        responses={200: serializers.PreviewSerializer},
        summary="What the letter would say, and anything it still needs",
    )
    @action(detail=False, methods=["post"])
    def preview(self, request):
        employee, template, answers, _ = self._written(request)
        letter = services.draft(
            template, employee, answers, on=timezone.localdate(), reference="(given when issued)"
        )
        return Response(
            {
                "subject": letter["subject"],
                "addressed": template.addressed,
                "blocks": letter["blocks"],
                "values": letter["values"],
                "missing": letter["missing"],
                "classification": template.classification,
            }
        )

    @extend_schema(responses={(200, "application/pdf"): bytes}, summary="Download the letter as issued")
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        return _download(request, self.get_object())


class MyLettersViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The letters issued to the signed-in person, whatever their roles."""

    queryset = Letter.objects.none()
    serializer_class = serializers.LetterSerializer
    permission_classes = [SelfServicePermission]
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        employee = getattr(self.request.user, "employee", None)
        if employee is None:
            return Letter.objects.none()
        return Letter.objects.filter(employee=employee).select_related("employee", "template", "document")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "own": True}

    @extend_schema(responses={(200, "application/pdf"): bytes}, summary="Download one of my letters")
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        return _download(request, self.get_object())
