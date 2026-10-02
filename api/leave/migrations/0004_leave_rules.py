"""Give the existing leave types their balance and evidence rules.

Leave with an entitlement can no longer be requested beyond the balance. Sick leave is the exception
the School asked for: within the balance no note is needed, beyond it a doctor's note is required.
"""

from django.db import migrations


def set_rules(apps, schema_editor):
    LeaveType = apps.get_model("leave", "LeaveType")
    LeaveType.objects.filter(annual_entitlement_days__gt=0).update(over_balance="refuse")
    LeaveType.objects.filter(code="SIC").update(
        over_balance="evidence",
        requires_evidence=False,
        evidence_name="Doctor's note",
        evidence_is_medical=True,
    )
    LeaveType.objects.filter(code="MAT").update(evidence_name="Medical certificate", evidence_is_medical=True)


class Migration(migrations.Migration):
    dependencies = [("leave", "0003_leave_self_service")]

    operations = [migrations.RunPython(set_rules, migrations.RunPython.noop)]
