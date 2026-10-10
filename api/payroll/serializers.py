"""H-M01 serializers: statutory rates, pay runs and payslips."""

from rest_framework import serializers

from core.serializers import TimeStampedSerializer
from payroll.models import PayRun, Payslip, StatutoryRate
from payroll.workflow import PAY_RUN


class StatutoryRateSerializer(TimeStampedSerializer):
    class Meta(TimeStampedSerializer.Meta):
        model = StatutoryRate
        fields = ("id", "kind", "value", "effective_from", "source_reference")


class PayRunSerializer(TimeStampedSerializer):
    allowed_actions = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = PayRun
        fields = (
            "id",
            "period",
            "state",
            "calculated_at",
            "approved_at",
            "disbursed_at",
            "total_gross",
            "total_nis_employee",
            "total_nis_employer",
            "total_paye",
            "total_net",
            "allowed_actions",
        )
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + (
            "state",
            "calculated_at",
            "approved_at",
            "disbursed_at",
            "total_gross",
            "total_nis_employee",
            "total_nis_employer",
            "total_paye",
            "total_net",
        )

    def get_allowed_actions(self, instance) -> list[str]:
        request = self.context.get("request")
        if request is None:
            return []
        return PAY_RUN.allowed_actions(instance, request.user)


class PayslipSerializer(TimeStampedSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True)
    period = serializers.CharField(source="pay_run.period", read_only=True)
    pay_run_state = serializers.CharField(source="pay_run.state", read_only=True)
    has_document = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Payslip
        fields = (
            "id",
            "pay_run",
            "period",
            "pay_run_state",
            "employee",
            "employee_name",
            "employee_no",
            "gross",
            "unpaid_days",
            "unpaid_deduction",
            "nis_employee",
            "nis_employer",
            "paye",
            "net",
            "breakdown",
            "has_document",
        )

    def get_has_document(self, instance) -> bool:
        return instance.document_id is not None
