"""The register of items issued to staff (item 1.17): HR and supervisors hand them out and take them back."""

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record, snapshot
from core.serializers import ErrorSerializer, InScope, TimeStampedSerializer
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.services import campus_in_scope, scope_queryset
from people.models import Employee, IssuedItem
from people.views import HR_WRITE, STAFF_READ, InScopeWrites

# Supervisors hand out the tools, keys and gear of their unit, and take them back.
ITEM_WRITE = HR_WRITE + (Role.SUPERVISOR,)


class IssuedItemSerializer(TimeStampedSerializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    condition_name = serializers.CharField(source="get_condition_display", read_only=True)
    issued_by = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = IssuedItem
        fields = (
            "id",
            "employee",
            "kind",
            "kind_name",
            "description",
            "tag",
            "issued_on",
            "returned_on",
            "condition",
            "condition_name",
            "note",
            "issued_by",
            "created_at",
            "updated_at",
        )
        # Given back only through the return action, which says in what condition.
        read_only_fields = (*TimeStampedSerializer.Meta.read_only_fields, "returned_on", "condition")

    def get_issued_by(self, item) -> str | None:
        user = item.created_by
        return (user.get_full_name() or user.get_username()) if user else None


class ReturnSerializer(serializers.Serializer):
    returned_on = serializers.DateField()
    condition = serializers.ChoiceField(choices=IssuedItem.Condition.choices)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


@extend_schema(
    parameters=[
        OpenApiParameter("employee", int, description="One member of staff"),
        OpenApiParameter("outstanding", str, enum=["1"], description="Only what is still out"),
    ]
)
class IssuedItemViewSet(InScopeWrites, AuditedModelViewSet):
    queryset = IssuedItem.objects.none()
    serializer_class = IssuedItemSerializer
    read_roles = STAFF_READ
    write_roles = ITEM_WRITE
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = IssuedItem.objects.select_related("employee", "created_by")
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        params = self.request.query_params
        if params.get("employee"):
            qs = qs.filter(employee_id=params["employee"])
        if params.get("outstanding") == "1":
            qs = qs.filter(returned_on__isnull=True)
        return qs

    @extend_schema(
        request=ReturnSerializer,
        responses={200: IssuedItemSerializer, 400: ErrorSerializer},
        summary="Record that an item was given back, or lost",
    )
    @action(detail=True, methods=["post"], url_path="return")
    def give_back(self, request, pk=None):
        item = self.get_object()
        if not campus_in_scope(request.user, item.employee.campus_id):
            self.permission_denied(request, message="That employee is not on a campus you work with.")
        if item.returned_on is not None:
            return Response(
                {"code": "returned", "detail": f"It was given back on {item.returned_on:%d/%m/%Y}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ReturnSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data["returned_on"] < item.issued_on:
            return Response(
                {"code": "too_early", "detail": "It was given back after it was issued."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            before = snapshot(item)
            item.returned_on = data.validated_data["returned_on"]
            item.condition = data.validated_data["condition"]
            item.note = data.validated_data.get("note", item.note) or item.note
            item.updated_by = request.user
            item.save(update_fields=["returned_on", "condition", "note", "updated_by", "updated_at"])
            record(request, "item_returned", item, before=before, after=snapshot(item), reason=item.note)
        return Response(self.get_serializer(item).data)
