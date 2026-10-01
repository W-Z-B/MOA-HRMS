"""The single next-of-kin pair on the employee becomes their first emergency contact, so the fact is held
in one place only. Reversing copies the first contact back."""

from django.db import migrations


def to_contacts(apps, schema_editor):
    Employee = apps.get_model("people", "Employee")
    EmergencyContact = apps.get_model("people", "EmergencyContact")
    for employee in Employee.objects.exclude(next_of_kin_name="").only(
        "id", "next_of_kin_name", "next_of_kin_phone"
    ):
        if not EmergencyContact.objects.filter(employee_id=employee.id).exists():
            EmergencyContact.objects.create(
                employee_id=employee.id,
                name=employee.next_of_kin_name,
                relationship="Next of kin",
                phone=employee.next_of_kin_phone or "not recorded",
                priority=1,
            )


def back_to_employee(apps, schema_editor):
    Employee = apps.get_model("people", "Employee")
    EmergencyContact = apps.get_model("people", "EmergencyContact")
    for contact in EmergencyContact.objects.filter(priority=1).order_by("employee_id", "id"):
        Employee.objects.filter(pk=contact.employee_id, next_of_kin_name="").update(
            next_of_kin_name=contact.name, next_of_kin_phone=contact.phone
        )


class Migration(migrations.Migration):
    dependencies = [("people", "0004_staff_record")]
    operations = [migrations.RunPython(to_contacts, back_to_employee)]
