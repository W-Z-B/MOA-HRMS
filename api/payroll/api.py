"""H-M01 endpoints: statutory rates, pay runs and their workflow, and payslips (own, or HR/Finance's)."""

from django.db.models import Q
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record
from core.views import AuditedModelViewSet
from iam.models import Role
from iam.permissions import RolePermission
from iam.services import has_role, scope_queryset
from payroll.models import PayRun, Payslip, StatutoryRate
from payroll.serializers import PayRunSerializer, PayslipSerializer, StatutoryRateSerializer
from payroll.services import RatesMissing
from payroll.workflow import PAY_RUN, WorkflowError

FINANCE = (Role.FINANCE, Role.ADMINISTRATOR)
BROAD_READ = FINANCE + (Role.HR_MANAGER, Role.PRINCIPAL, Role.AUDITOR)


def _refuse(code: str, detail: str, http_status: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"code": code, "detail": detail}, status=http_status)


class StatutoryRateViewSet(AuditedModelViewSet):
    queryset = StatutoryRate.objects.all()
    serializer_class = StatutoryRateSerializer
    read_roles = BROAD_READ
    write_roles = FINANCE


class PayRunViewSet(AuditedModelViewSet):
    queryset = PayRun.objects.all()
    serializer_class = PayRunSerializer
    read_roles = BROAD_READ
    write_roles = FINANCE

    def create(self, request, *args, **kwargs):
        # A run starts empty, in draft: figures only ever come from the calculate action, never from a
        # body posted here, so the engine's arithmetic can never be bypassed on the way in.
        period = str(request.data.get("period") or "").strip()
        if len(period) != 7 or period[4] != "-":
            return _refuse("invalid", "Give the period as YYYY-MM.", status.HTTP_400_BAD_REQUEST)
        if PayRun.objects.filter(period=period).exists():
            return _refuse("exists", "A run for that period already exists.")
        instance = PayRun.objects.create(period=period, created_by=request.user, updated_by=request.user)
        record(request, "create", instance, after={"period": period})
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        return _refuse("not_allowed", "Use the transition action.", status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.state != PayRun.State.DRAFT:
            return _refuse("not_allowed", "Only a run still in draft can be removed.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        action_name = str(request.data.get("action") or "")
        instance = self.get_object()
        try:
            PAY_RUN.apply(instance, action_name, request=request)
        except WorkflowError as exc:
            code = status.HTTP_403_FORBIDDEN if exc.code == "forbidden_actor" else status.HTTP_409_CONFLICT
            return Response({"code": exc.code, "detail": str(exc)}, status=code)
        except RatesMissing as exc:
            return _refuse("rates_missing", str(exc))
        return Response(self.get_serializer(instance).data)


class PayslipViewSet(viewsets.ReadOnlyModelViewSet):
    """Finance and HR see every payslip on their campuses; everyone else sees only their own, and only
    once the run is disbursed, so a figure still being worked out is never read as final (item H-M01)."""

    queryset = Payslip.objects.none()  # scoped per request in get_queryset; fails closed
    serializer_class = PayslipSerializer
    permission_classes = [RolePermission]  # authentication and, for Finance et al., MFA (iam.permissions)

    def get_queryset(self):
        user = self.request.user
        qs = Payslip.objects.select_related("employee", "pay_run")
        own = Q(employee__user=user, pay_run__state=PayRun.State.DISBURSED)
        if has_role(user, *BROAD_READ):
            scoped = scope_queryset(user, Payslip.objects.all(), campus_field="employee__campus")
            qs = qs.filter(Q(pk__in=scoped.values("pk")) | own)
        else:
            qs = qs.filter(own)
        params = self.request.query_params
        if params.get("pay_run"):
            qs = qs.filter(pay_run_id=params["pay_run"])
        if params.get("employee"):
            qs = qs.filter(employee_id=params["employee"])
        return qs.distinct()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        instance = self.get_object()
        if instance.document is None:
            return _refuse("not_issued", "The payslip is issued once the run is disbursed.", 404)
        record(request, "download", instance.document, after={"title": instance.document.title})
        return FileResponse(
            instance.document.file.open("rb"), as_attachment=True, filename=instance.document.download_name
        )


router = DefaultRouter()
router.register("statutory-rates", StatutoryRateViewSet)
router.register("runs", PayRunViewSet)
router.register("payslips", PayslipViewSet)
urlpatterns = router.urls

__all__ = ["urlpatterns", "viewsets"]
