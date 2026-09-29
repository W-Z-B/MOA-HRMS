from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from core.serializers import TimeStampedSerializer
from core.views import AuditedModelViewSet
from iam.models import Role
from payroll.models import PayrollPeriod, StatutoryRate

FINANCE = (Role.FINANCE, Role.ADMINISTRATOR)


class PayrollPeriodSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = PayrollPeriod
        fields = ("id", "period", "state", "locked_at", "exported_at")
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + ("state", "locked_at", "exported_at")


class StatutoryRateSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = StatutoryRate
        fields = ("id", "kind", "value", "effective_from", "source_reference")


class PayrollPeriodViewSet(AuditedModelViewSet):
    queryset = PayrollPeriod.objects.all()
    serializer_class = PayrollPeriodSerializer
    read_roles = FINANCE + (Role.HR_MANAGER, Role.PRINCIPAL, Role.AUDITOR)
    write_roles = FINANCE

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Lock the period and produce the change file. Release 2: returns 501 until implemented."""
        return Response(
            {"code": "not_implemented", "detail": "Period close arrives in Release 2 (F13)."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class StatutoryRateViewSet(AuditedModelViewSet):
    queryset = StatutoryRate.objects.all()
    serializer_class = StatutoryRateSerializer
    read_roles = FINANCE + (Role.HR_MANAGER, Role.AUDITOR)
    write_roles = FINANCE


router = DefaultRouter()
router.register("periods", PayrollPeriodViewSet)
router.register("statutory-rates", StatutoryRateViewSet)
urlpatterns = router.urls

__all__ = ["urlpatterns", "viewsets"]
