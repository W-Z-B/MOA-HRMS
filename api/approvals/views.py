"""Approvals (item 1.33): what waits for me, and who stands in for me while I am away."""

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from approvals.inbox import waiting_for
from approvals.models import Delegation
from audit.services import record, snapshot
from core.serializers import ErrorSerializer, InScope
from iam.permissions import SelfServicePermission
from iam.services import campus_in_scope, has_role, scope_queryset
from people.models import Employee
from people.views import HR_WRITE


class WaitingItemSerializer(serializers.Serializer):
    kind = serializers.CharField()
    kind_name = serializers.CharField()
    title = serializers.CharField()
    since = serializers.DateTimeField()
    waited_days = serializers.IntegerField(help_text="Working days it has waited")
    overdue = serializers.BooleanField(help_text="Waited past its time limit")
    link = serializers.CharField(help_text="Where it is decided, in the web app")
    for_whom = serializers.CharField(help_text="Who it was sent to, when deciding as their stand-in")


@extend_schema(
    responses=WaitingItemSerializer(many=True), summary="Everything waiting for my decision, oldest first"
)
@api_view(["GET"])
@permission_classes([SelfServicePermission])
def waiting(request):
    return Response(WaitingItemSerializer(waiting_for(request.user), many=True).data)


class DelegationSerializer(serializers.ModelSerializer):
    # Both named only among the staff the person may see, so a refusal never names anyone else.
    delegator = InScope(Employee, required=False, help_text="Whose decisions: yourself unless HR says")
    delegate = InScope(Employee, help_text="A colleague on a campus you work with")
    delegator_name = serializers.CharField(source="delegator.full_name", read_only=True)
    delegate_name = serializers.CharField(source="delegate.full_name", read_only=True)
    in_force = serializers.SerializerMethodField()

    class Meta:
        model = Delegation
        fields = (
            "id",
            "delegator",
            "delegator_name",
            "delegate",
            "delegate_name",
            "starts",
            "ends",
            "reason",
            "cancelled",
            "in_force",
            "created_at",
        )
        read_only_fields = ("id", "cancelled", "created_at")

    def get_in_force(self, delegation) -> bool:
        today = timezone.localdate()
        return not delegation.cancelled and delegation.starts <= today <= delegation.ends

    def validate(self, attrs):
        request = self.context["request"]
        own = getattr(request.user, "employee", None)
        delegator = attrs.get("delegator") or own
        if delegator is None:
            raise serializers.ValidationError(
                {"delegator": ["Your account is not linked to a staff record."]}
            )
        if delegator != own:
            if not has_role(request.user, *HR_WRITE) or not campus_in_scope(
                request.user, delegator.campus_id
            ):
                raise serializers.ValidationError(
                    {"delegator": ["You can name a stand-in for yourself only."]}
                )
        delegate = attrs["delegate"]
        if delegate == delegator:
            raise serializers.ValidationError({"delegate": ["A stand-in is someone else."]})
        if (
            delegate.status == Employee.Status.SEPARATED
            or delegate.user is None
            or not delegate.user.is_active
        ):
            raise serializers.ValidationError(
                {"delegate": [f"{delegate.full_name} cannot sign in to decide."]}
            )
        if attrs["ends"] < attrs["starts"]:
            raise serializers.ValidationError({"ends": ["It ends on or after the day it starts."]})
        if attrs["ends"] < timezone.localdate():
            raise serializers.ValidationError({"ends": ["That time has already passed."]})
        overlapping = Delegation.objects.filter(
            delegator=delegator, cancelled=False, starts__lte=attrs["ends"], ends__gte=attrs["starts"]
        )
        if overlapping.exists():
            raise serializers.ValidationError(
                {"starts": [f"{delegator.full_name} already has a stand-in for part of that time."]}
            )
        attrs["delegator"] = delegator
        return attrs


@extend_schema(parameters=[OpenApiParameter("employee", int, description="For HR: one member of staff")])
class DelegationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """My stand-ins and those I stand in for; HR also sees and names them for staff on their campuses."""

    queryset = Delegation.objects.none()
    serializer_class = DelegationSerializer
    permission_classes = [SelfServicePermission]

    def get_queryset(self):
        user = self.request.user
        own = getattr(user, "employee", None)
        qs = Delegation.objects.select_related("delegator", "delegate")
        employee = self.request.query_params.get("employee")
        if employee and has_role(user, *HR_WRITE):
            return scope_queryset(user, qs, "delegator__campus").filter(delegator_id=employee)
        if own is None:
            return qs.none()
        return qs.filter(delegator=own) | qs.filter(delegate=own)

    @transaction.atomic
    def perform_create(self, serializer):
        delegation = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        record(self.request, "create", delegation, after=snapshot(delegation), reason=delegation.reason)
        from notifications.services import notify

        notify(
            [delegation.delegate.user],
            title=f"You stand in for {delegation.delegator.full_name}",
            body=(
                f"From {delegation.starts:%d/%m/%Y} to {delegation.ends:%d/%m/%Y} "
                "you may decide what is sent to "
                f"{delegation.delegator.first_name}. It appears under To do."
            ),
            link="/to-do",
            dedupe_key=f"delegation:{delegation.pk}",
        )

    @extend_schema(
        request=None,
        responses={200: DelegationSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="End a stand-in early, or before it starts",
    )
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        delegation = self.get_object()
        own = getattr(request.user, "employee", None)
        hr = has_role(request.user, *HR_WRITE) and campus_in_scope(
            request.user, delegation.delegator.campus_id
        )
        if delegation.delegator != own and not hr:
            return Response(
                {"code": "forbidden", "detail": "Only the person who named the stand-in, or HR, ends it."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if delegation.cancelled or delegation.ends < timezone.localdate():
            return Response(
                {"code": "over", "detail": "It is already over."}, status=status.HTTP_409_CONFLICT
            )
        with transaction.atomic():
            before = snapshot(delegation)
            delegation.cancelled = True
            delegation.updated_by = request.user
            delegation.save(update_fields=["cancelled", "updated_by", "updated_at"])
            record(request, "delegation_ended", delegation, before=before, after=snapshot(delegation))
        return Response(self.get_serializer(delegation).data)
