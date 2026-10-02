"""Signing (item 1.20): HR asks; the person signs or declines in their own account; the evidence is shown.

Requests and their evidence are read by those who read confidential documents, on their campuses. The person
asked reads the document through their own request, whatever their roles, and only they can sign it.
"""

from django.http import FileResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record
from core.serializers import ErrorSerializer, InScope
from iam.permissions import RolePermission, SelfServicePermission
from iam.services import campus_in_scope, scope_queryset
from iam.sessions import describe_device
from people.models import Document
from people.views import CONFIDENTIAL_READ, HR_WRITE
from signing import services
from signing.models import Signature, SignatureRequest


class EvidenceSerializer(serializers.ModelSerializer):
    signer_name = serializers.SerializerMethodField()
    device = serializers.SerializerMethodField()
    file_unchanged = serializers.SerializerMethodField(
        help_text="Whether the document's file still has the fingerprint it had when signed"
    )

    class Meta:
        model = Signature
        fields = (
            "signer_name",
            "signed_at",
            "statement",
            "document_title",
            "document_version",
            "sha256",
            "method",
            "source_ip",
            "device",
            "file_unchanged",
        )
        read_only_fields = fields

    def get_signer_name(self, signature) -> str:
        return signature.signer.get_full_name() or signature.signer.get_username()

    def get_device(self, signature) -> str:
        return describe_device(signature.user_agent)

    def get_file_unchanged(self, signature) -> bool:
        return services.fingerprint(signature.request.document) == signature.sha256


class SignatureRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    state_name = serializers.CharField(source="get_state_display", read_only=True)
    requested_by = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = SignatureRequest
        fields = (
            "id",
            "document",
            "document_title",
            "employee",
            "employee_name",
            "kind",
            "kind_name",
            "statement",
            "message",
            "due_by",
            "state",
            "state_name",
            "created_at",
            "decided_at",
            "decline_reason",
            "requested_by",
            "evidence",
            "download_url",
        )
        read_only_fields = fields

    def get_requested_by(self, wanted) -> str | None:
        user = wanted.created_by
        return (user.get_full_name() or user.get_username()) if user else None

    @extend_schema_field(EvidenceSerializer(allow_null=True))
    def get_evidence(self, wanted) -> dict | None:
        signature = getattr(wanted, "signature", None)
        return EvidenceSerializer(signature).data if signature else None

    def get_download_url(self, wanted) -> str:
        if self.context.get("own"):
            return f"/api/v1/signing/mine/{wanted.pk}/document/"
        return f"/api/v1/documents/{wanted.document_id}/download/"


class SignatureAskSerializer(serializers.Serializer):
    document = InScope(Document, campus_field="employee__campus", help_text="A document in a staff file")
    kind = serializers.ChoiceField(choices=SignatureRequest.Kind.choices)
    statement = serializers.CharField(
        max_length=300, required=False, allow_blank=True, help_text="Leave empty for the usual sentence"
    )
    message = serializers.CharField(max_length=300, required=False, allow_blank=True)
    due_by = serializers.DateField(required=False, allow_null=True)


class SignSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    agree = serializers.BooleanField()

    def validate_agree(self, agree):
        if not agree:
            raise serializers.ValidationError("Tick that you agree to the sentence above.")
        return agree


class SigningReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=300, error_messages={"required": "Say why.", "blank": "Say why."}
    )


def _refused(exc: services.Refused) -> Response:
    code = status.HTTP_409_CONFLICT if exc.code in services.CONFLICTS else status.HTTP_400_BAD_REQUEST
    if exc.code == "locked":
        code = status.HTTP_429_TOO_MANY_REQUESTS
    return Response({"code": exc.code, "detail": exc.detail}, status=code)


@extend_schema(
    parameters=[
        OpenApiParameter("employee", int, description="One member of staff"),
        OpenApiParameter("document", int, description="One document"),
        OpenApiParameter("state", str, enum=["waiting", "signed", "declined", "withdrawn"]),
    ]
)
class SignatureRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = SignatureRequest.objects.none()
    serializer_class = SignatureRequestSerializer
    permission_classes = [RolePermission]
    read_roles = CONFIDENTIAL_READ
    write_roles = HR_WRITE

    def get_queryset(self):
        qs = SignatureRequest.objects.select_related(
            "employee", "document", "created_by", "signature", "signature__signer"
        )
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        params = self.request.query_params
        for name in ("employee", "document", "state"):
            if params.get(name):
                qs = qs.filter(**{f"{name}_id" if name != "state" else name: params[name]})
        return qs

    @extend_schema(
        request=SignatureAskSerializer,
        responses={201: SignatureRequestSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
        summary="Ask the person a document is about to acknowledge it, or accept it",
    )
    def create(self, request):
        data = SignatureAskSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        document = data.validated_data.pop("document")
        if not campus_in_scope(request.user, document.employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        try:
            wanted = services.ask(request, document=document, **data.validated_data)
        except services.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(wanted).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=SigningReasonSerializer,
        responses={200: SignatureRequestSerializer, 400: ErrorSerializer},
        summary="Withdraw a request still waiting",
    )
    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        wanted = self.get_object()
        if not campus_in_scope(request.user, wanted.employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        data = SigningReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.withdraw(request, wanted, data.validated_data["reason"])
        except services.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(wanted).data)


class MySignaturesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """What the signed-in person has been asked to sign, and has signed, whatever their roles."""

    queryset = SignatureRequest.objects.none()
    serializer_class = SignatureRequestSerializer
    permission_classes = [SelfServicePermission]
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        employee = getattr(self.request.user, "employee", None)
        if employee is None:
            return SignatureRequest.objects.none()
        return (
            SignatureRequest.objects.filter(employee=employee)
            .exclude(state=SignatureRequest.State.WITHDRAWN)
            .select_related("employee", "document", "created_by", "signature", "signature__signer")
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "own": True}

    @extend_schema(
        responses={(200, "application/octet-stream"): bytes}, summary="Read the document I am asked to sign"
    )
    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        document = self.get_object().document
        record(request, "download", document, after={"title": document.title, "version": document.version})
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.download_name)

    @extend_schema(
        request=SignSerializer,
        responses={200: SignatureRequestSerializer, 400: ErrorSerializer, 429: ErrorSerializer},
        summary="Sign: agree to the sentence, confirmed with my password",
    )
    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        wanted = self.get_object()
        data = SignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.sign(request, wanted, data.validated_data["password"])
        except services.Refused as exc:
            return _refused(exc)
        wanted.refresh_from_db()
        return Response(self.get_serializer(wanted).data)

    @extend_schema(
        request=SigningReasonSerializer,
        responses={200: SignatureRequestSerializer, 400: ErrorSerializer},
        summary="Decline to sign, saying why",
    )
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        wanted = self.get_object()
        data = SigningReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.decline(request, wanted, data.validated_data["reason"])
        except services.Refused as exc:
            return _refused(exc)
        return Response(self.get_serializer(wanted).data)
