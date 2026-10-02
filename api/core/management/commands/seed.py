"""Seed reference data: campuses, roles, leave types, public holidays, report definitions.

Idempotent. Statutory rates are deliberately not seeded: Finance enters them from the official
NIS and GRA schedules with a source reference.
"""

from datetime import date

from django.core.management.base import BaseCommand

from core.holidays import by_rule
from core.models import PublicHoliday
from iam.models import Role
from leave.models import LeaveType
from org.models import Campus
from privacy.models import RetentionRule
from privacy.retention import RULES as RETENTION_RULES
from reports.models import ReportDefinition

CAMPUSES = [
    ("MRP", "Mon Repos Campus", "Mon Repos, East Coast Demerara", "Region 4"),
    ("ESQ", "Essequibo Campus", "Cotton Field, Essequibo Coast", "Region 2"),
]

# Guyana's public holidays that follow a rule (fixed dates, Easter, the first Monday in July) are worked out
# in core.holidays. Phagwah, Eid ul-Adha, Youman Nabi, Deepavali and any substitute day are named in the
# gazette each year, and HR adds them on the Admin screen (Holidays).

LEAVE_TYPES = [
    # code, name, annual days, accrues monthly, carry over max, paid, evidence, term restricted
    ("ANN", "Annual leave", 21, True, 10, True, False, True),
    ("SIC", "Sick leave", 14, False, 0, True, False, False),
    ("MAT", "Maternity leave", 0, False, 0, True, True, False),
    ("STU", "Study leave", 0, False, 0, True, True, False),
    ("SPE", "Special leave", 0, False, 0, True, False, False),
    ("NOP", "Leave without pay", 0, False, 0, False, False, False),
]
# code: beyond the balance, what the evidence is called, evidence is medical. Others take the defaults.
LEAVE_RULES = {
    "ANN": ("refuse", "Supporting document", False),
    "SIC": ("evidence", "Doctor's note", True),
    "MAT": ("allow", "Medical certificate", True),
    "STU": ("allow", "Letter of acceptance", False),
}

REPORTS = [
    (
        "establishment-vs-actual",
        "Establishment versus actual",
        ["hr_officer", "hr_manager", "principal", "finance", "ministry_liaison", "auditor"],
        True,
    ),
    ("headcount-by-campus", "Headcount by campus", [], True),
    # Item 1.09: identifiers missing or repeated, unlikely dates of birth, no contact, no contract.
    ("data-quality", "Staff records to check", ["hr_officer", "hr_manager", "administrator"], False),
    # Item 1.27: every role each account holds, signed off every three months on the Admin screen.
    ("access-review", "Who can see what", ["administrator", "hr_manager", "auditor"], False),
    # Item 1.31: who has read the privacy notice in force.
    ("privacy-acknowledgements", "Privacy notice read", ["administrator", "hr_manager", "auditor"], False),
]


class Command(BaseCommand):
    help = "Seed reference data for the Guyana School of Agriculture (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="GY")
        parser.add_argument("--year", type=int, default=date.today().year)

    def handle(self, *args, **options):
        if options["country"] != "GY":
            self.stderr.write("Only GY seed data is defined.")
            return
        for code, name, address, region in CAMPUSES:
            Campus.objects.update_or_create(
                code=code, defaults={"name": name, "address": address, "region": region}
            )
        for code, name in Role.CODES:
            Role.objects.update_or_create(code=code, defaults={"name": name})
        for code, name, days, monthly, carry, paid, evidence, term in LEAVE_TYPES:
            beyond, evidence_name, medical = LEAVE_RULES.get(code, ("allow", "Supporting document", False))
            LeaveType.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "annual_entitlement_days": days,
                    "accrues_monthly": monthly,
                    "carry_over_max_days": carry,
                    "is_paid": paid,
                    "requires_evidence": evidence,
                    "term_time_restricted": term,
                    "over_balance": beyond,
                    "evidence_name": evidence_name,
                    "evidence_is_medical": medical,
                },
            )
        for year in (options["year"], options["year"] + 1):
            for holiday in by_rule(year):
                PublicHoliday.objects.update_or_create(date=holiday.day, defaults={"name": holiday.name})
        for key, name, roles, pack in REPORTS:
            ReportDefinition.objects.update_or_create(
                key=key, defaults={"name": name, "roles": roles, "is_ministry_pack": pack}
            )
        # The retention schedule starts from the impact assessment's proposals. A period GSA has changed or
        # confirmed is kept: only the wording the code owns is refreshed.
        for code, name, months, counted_from, automatic, note in RETENTION_RULES:
            rule, created = RetentionRule.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "keep_months": months,
                    "counted_from": counted_from,
                    "automatic": automatic,
                    "note": note,
                },
            )
            if not created:
                RetentionRule.objects.filter(pk=rule.pk).update(
                    name=name, counted_from=counted_from, automatic=automatic
                )
        self.stdout.write(
            self.style.SUCCESS(
                "Seed data applied: campuses, roles, leave types, holidays, reports, retention schedule."
            )
        )
