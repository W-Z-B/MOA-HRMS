"""The first letter templates (item 1.19): draft wording for GSA's Human Resources to review and change.

Each is added once, as version 1, when no template has its code. A template GSA has changed is \
never touched:
their change is its next version.
"""

PRINCIPAL = "Principal"
HR_MANAGER = "Human Resources Manager"

TEMPLATES = [
    {
        "code": "job_letter",
        "kind": "job_letter",
        "name": "Job letter",
        "subject": "Confirmation of employment: {{full_name}}",
        "addressed": False,
        "classification": "internal",
        "signatory_title": HR_MANAGER,
        "asks": [{"key": "purpose", "label": "What the letter is for", "type": "text"}],
        "body": """To whom it may concern,

This is to confirm that **{{full_name}}** (employee number {{employee_no}}) has been employed by \
the Guyana \
School of Agriculture since {{first_appointed}}, and now holds the post of {{post_title}} in the \
{{unit}}, \
{{campus}}, on a {{appointment_type}} appointment.

This letter is issued at the employee's request, for {{purpose}}.""",
    },
    {
        "code": "job_letter_salary",
        "kind": "job_letter",
        "name": "Job letter with salary",
        "subject": "Confirmation of employment and salary: {{full_name}}",
        "addressed": False,
        "classification": "confidential",
        "signatory_title": HR_MANAGER,
        "asks": [{"key": "purpose", "label": "What the letter is for", "type": "text"}],
        "body": """To whom it may concern,

This is to confirm that **{{full_name}}** (employee number {{employee_no}}) has been employed by \
the Guyana \
School of Agriculture since {{first_appointed}}, and now holds the post of {{post_title}} in the \
{{unit}}, \
{{campus}}, on a {{appointment_type}} appointment.

The employee's salary is {{monthly_salary}} a month, on grade {{grade}}.

This letter is issued at the employee's request, for {{purpose}}.""",
    },
    {
        "code": "appointment",
        "kind": "appointment",
        "name": "Letter of appointment",
        "subject": "Appointment to the post of {{post_title}}",
        "addressed": True,
        "classification": "confidential",
        "signatory_title": PRINCIPAL,
        "asks": [{"key": "reply_by", "label": "Reply by", "type": "date"}],
        "body": """Dear {{first_name}} {{last_name}},

I am pleased to tell you that you are appointed to the post of **{{post_title}}** (post \
{{post_number}}) in the \
{{unit}}, {{campus}}, on a {{appointment_type}} appointment, from {{appointed_on}}.

Your salary is {{monthly_salary}} a month, on grade {{grade}}. The appointment is subject to a \
period of \
probation, which ends on {{probation_end}}.

Your hours, duties and other conditions are set out in your contract and in the School's \
conditions of service.

Please let the Human Resources office know by {{reply_by}} whether you accept this appointment.""",
    },
    {
        "code": "confirmation",
        "kind": "confirmation",
        "name": "Confirmation of appointment",
        "subject": "Confirmation in the post of {{post_title}}",
        "addressed": True,
        "classification": "confidential",
        "signatory_title": PRINCIPAL,
        "asks": [{"key": "confirmed_from", "label": "Confirmed from", "type": "date"}],
        "body": """Dear {{first_name}} {{last_name}},

I am pleased to tell you that, having completed your period of probation satisfactorily, you are \
confirmed in \
the post of **{{post_title}}** from {{confirmed_from}}.

All other conditions of your appointment remain the same.""",
    },
    {
        "code": "transfer",
        "kind": "transfer",
        "name": "Transfer",
        "subject": "Transfer to the post of {{new_post}}",
        "addressed": True,
        "classification": "confidential",
        "signatory_title": HR_MANAGER,
        "asks": [
            {"key": "new_post", "label": "The new post", "type": "text"},
            {"key": "new_unit", "label": "The new unit and campus", "type": "text"},
            {"key": "effective_date", "label": "Takes effect on", "type": "date"},
        ],
        "body": """Dear {{first_name}} {{last_name}},

You are transferred from the post of {{post_title}} in the {{unit}}, {{campus}}, to the post of \
**{{new_post}}** \
in the {{new_unit}}, from {{effective_date}}.

Please report to the head of the {{new_unit}} on that day. Your salary and other conditions of \
service do not \
change with this transfer.""",
    },
    {
        "code": "certificate_of_service",
        "kind": "exit",
        "name": "Certificate of service",
        "subject": "Certificate of service: {{full_name}}",
        "addressed": False,
        "classification": "internal",
        "signatory_title": HR_MANAGER,
        "asks": [{"key": "last_day", "label": "Last day of service", "type": "date"}],
        "body": """To whom it may concern,

This is to certify that **{{full_name}}** was employed by the Guyana School of Agriculture from \
{{first_appointed}} to {{last_day}}, and last held the post of {{post_title}} in the {{unit}}, \
{{campus}}.""",
    },
]


def seed_templates() -> int:
    """Add each first template whose code is not yet used. Returns how many were added."""
    from letters.models import LetterTemplate

    added = 0
    for spec in TEMPLATES:
        if LetterTemplate.objects.filter(code=spec["code"]).exists():
            continue
        LetterTemplate.objects.create(version=1, **spec)
        added += 1
    return added
