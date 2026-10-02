"""Item 1.21: scanned papers filed in bulk by HR. A batch is begun with what the papers are, then its files
are sent one at a time, so a large pile never makes one large request; each answer says where the file went.

A batch is seen by whoever began it, and by HR roles that work on every campus, since its files name people.
"""

from django.db.models import Count, Prefetch, Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer, InScope
from iam.permissions import RolePermission
from iam.services import campus_limit
from people import scanning
from people.models import Document, Employee, ScanBatch, ScanItem
from people.serializers import _RESTRICTION, LEAST_CLASSIFICATION
from people.views import HR_WRITE


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


class ScanItemSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True, allow_null=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True, allow_null=True)
    document_title = serializers.CharField(source="document.title", read_only=True, allow_null=True)
    filed = serializers.SerializerMethodField()

    class Meta:
        model = ScanItem
        fields = (
            "id",
            "name",
            "employee",
            "employee_name",
            "employee_no",
            "document",
            "document_title",
            "filed",
            "refused",
            "at",
        )
        read_only_fields = fields

    def get_filed(self, item) -> bool:
        return item.document_id is not None


class ScanBatchSerializer(serializers.ModelSerializer):
    doc_type = serializers.ChoiceField(choices=list(scanning.DOC_TYPES.items()))
    doc_type_name = serializers.SerializerMethodField()
    classification = serializers.ChoiceField(choices=Document.Classification.choices, required=False)
    created_by_name = serializers.SerializerMethodField()
    filed = serializers.IntegerField(read_only=True, default=0)
    not_filed = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ScanBatch
        fields = (
            "id",
            "doc_type",
            "doc_type_name",
            "classification",
            "note",
            "created_by_name",
            "created_at",
            "filed",
            "not_filed",
        )
        read_only_fields = ("id", "doc_type_name", "created_by_name", "created_at", "filed", "not_filed")

    def get_doc_type_name(self, batch) -> str:
        return scanning.DOC_TYPES.get(batch.doc_type, batch.doc_type)

    def get_created_by_name(self, batch) -> str | None:
        return _name(batch.created_by)

    def validate(self, attrs):
        """Never filed below what the type needs: a contract shows pay, a medical paper someone's health."""
        doc_type = attrs["doc_type"]
        if doc_type not in LEAST_CLASSIFICATION:
            attrs.setdefault("classification", Document.Classification.CONFIDENTIAL)
            return attrs
        what, least = LEAST_CLASSIFICATION[doc_type]
        given = attrs.setdefault("classification", least)
        if _RESTRICTION.index(given) < _RESTRICTION.index(least):
            needed = "Medical" if least == Document.Classification.MEDICAL else "Confidential or Medical"
            raise serializers.ValidationError({"classification": [f"{what} is filed as {needed}."]})
        return attrs


class ScanBatchDetailSerializer(ScanBatchSerializer):
    items = ScanItemSerializer(many=True, read_only=True)

    class Meta(ScanBatchSerializer.Meta):
        fields = ScanBatchSerializer.Meta.fields + ("items",)
        read_only_fields = ScanBatchSerializer.Meta.read_only_fields + ("items",)


class ScanFileSerializer(serializers.Serializer):
    file = serializers.FileField()
    employee = InScope(
        Employee,
        required=False,
        allow_null=True,
        help_text="Whose file it belongs in, when its name gives nobody",
    )


class ScanBatchViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """Batches of scanned papers: each HR officer's own, and every one for those who work on every campus."""

    queryset = ScanBatch.objects.none()
    serializer_class = ScanBatchSerializer
    permission_classes = [RolePermission]
    read_roles = HR_WRITE
    write_roles = HR_WRITE
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        qs = ScanBatch.objects.select_related("created_by").annotate(
            filed=Count("items", filter=Q(items__document__isnull=False)),
            not_filed=Count("items", filter=Q(items__document__isnull=True)),
        )
        if campus_limit(self.request.user) is not None:
            qs = qs.filter(created_by=self.request.user)
        if self.action == "retrieve":
            items = ScanItem.objects.select_related("employee", "document")
            qs = qs.prefetch_related(Prefetch("items", queryset=items))
        return qs.order_by("-created_at", "-id")

    def get_serializer_class(self):
        return ScanBatchDetailSerializer if self.action == "retrieve" else ScanBatchSerializer

    def perform_create(self, serializer):
        batch = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record(self.request, "create", batch, before=None, after=snapshot(batch))

    @extend_schema(
        request={"multipart/form-data": ScanFileSerializer},
        responses={200: ScanItemSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        summary="File one scanned paper: into the record its name gives, or the one chosen",
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def files(self, request, pk=None):
        batch = self.get_object()
        if batch.created_by_id != request.user.pk:
            return Response(
                {"code": "not_yours", "detail": "Papers are added to a batch by whoever began it."},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = ScanFileSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        item = scanning.file_one(
            request, batch, data.validated_data["file"], employee=data.validated_data.get("employee")
        )
        fresh = ScanItem.objects.select_related("employee", "document").get(pk=item.pk)
        return Response(ScanItemSerializer(fresh).data)
