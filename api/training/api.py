from rest_framework import viewsets
from rest_framework.routers import DefaultRouter

from core.serializers import TimeStampedSerializer
from iam.permissions import RolePermission
from training.models import TrainingRecord


class TrainingRecordSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = TrainingRecord
        fields = (
            "id",
            "employee",
            "course",
            "provider",
            "starts",
            "ends",
            "cost",
            "certification",
            "expiry_date",
            "bond_months",
        )


class TrainingRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TrainingRecord.objects.select_related("employee")
    serializer_class = TrainingRecordSerializer
    permission_classes = [RolePermission]


router = DefaultRouter()
router.register("records", TrainingRecordViewSet)
urlpatterns = router.urls
