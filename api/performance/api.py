from rest_framework import viewsets
from rest_framework.routers import DefaultRouter

from core.serializers import TimeStampedSerializer
from iam.permissions import RolePermission
from performance.models import Appraisal, AppraisalCycle


class AppraisalCycleSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = AppraisalCycle
        fields = ("id", "name", "year", "starts", "ends", "is_open")


class AppraisalSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = Appraisal
        fields = ("id", "employee", "cycle", "kind", "state", "overall_rating", "outcome", "form_data")


class AppraisalCycleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AppraisalCycle.objects.all()
    serializer_class = AppraisalCycleSerializer
    permission_classes = [RolePermission]


class AppraisalViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Appraisal.objects.select_related("employee", "cycle")
    serializer_class = AppraisalSerializer
    permission_classes = [RolePermission]


router = DefaultRouter()
router.register("cycles", AppraisalCycleViewSet)
router.register("appraisals", AppraisalViewSet)
urlpatterns = router.urls
