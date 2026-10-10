"""The payslip PDF (H-M01), on disbursement. Reuses the letters app's WeasyPrint pattern (letters.pdf):
an HTML page built from escaped text only, rendered with a url fetcher that refuses everything, so a
payslip can never be made to reach out to a server, exactly as a letter cannot (item 1.19).
"""

import html

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from audit.services import record, snapshot
from letters import pdf
from notifications.services import notify
from people.models import Document

STYLE = """
@page {
  size: A4;
  margin: 20mm 20mm 24mm;
  @bottom-right {
    content: "Page " counter(page) " of " counter(pages);
    font: 8pt "DejaVu Sans", sans-serif;
    color: #555;
  }
}
body { font: 11pt/1.45 "DejaVu Serif", serif; color: #111; }
.head { border-bottom: 2pt solid #2f6b46; padding-bottom: 5pt; margin-bottom: 16pt; }
.org { font: bold 15pt "DejaVu Sans", sans-serif; color: #2f6b46; }
.period { font: 9pt "DejaVu Sans", sans-serif; color: #444; }
table { width: 100%; border-collapse: collapse; margin-bottom: 14pt; font-size: 10pt; }
td { padding: 3pt 0; }
td.amount { text-align: right; font-family: "DejaVu Sans Mono", monospace; }
tr.total td { border-top: 1pt solid #333; font-weight: bold; padding-top: 6pt; }
.foot { margin-top: 26pt; padding-top: 4pt; border-top: 0.5pt solid #bbb; font-size: 8pt; color: #555; }
"""


def _row(label: str, amount) -> str:
    return f'<tr><td>{html.escape(label)}</td><td class="amount">{amount:,.2f}</td></tr>'


def page(*, employee, period: str, payslip) -> str:
    escape = html.escape
    rows = [
        _row("Gross pay", payslip.gross),
        *([_row("Less unpaid days", -payslip.unpaid_deduction)] if payslip.unpaid_days else []),
        _row("NIS (employee)", -payslip.nis_employee),
        _row("PAYE income tax", -payslip.paye),
    ]
    subject = f"Payslip for {period}"
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<title>{escape(subject)}</title>
<meta name="author" content="{escape(settings.LETTER_ORGANISATION)}">
<style>{STYLE}</style>
</head>
<body>
<div class="head">
<div class="org">{escape(settings.LETTER_ORGANISATION)}</div>
<div class="period">{escape(subject)}</div>
</div>
<table><tr>
<td>{escape(employee.full_name)} ({escape(employee.employee_no)})</td>
<td class="amount">{escape(period)}</td>
</tr></table>
<table>
{"".join(rows)}
<tr class="total"><td>Net pay</td><td class="amount">{payslip.net:,.2f}</td></tr>
</table>
<div class="foot">Issued through the GSA HRMS. For a question about this payslip, contact Human Resources
or Finance and quote the period above.</div>
</body>
</html>"""


@transaction.atomic
def issue_payslips(pay_run, request) -> int:
    """A PDF per payslip in the run, filed to the employee's record and the employee told (item H-M01)."""
    issued = 0
    for payslip in pay_run.payslips.select_related("employee").filter(document__isnull=True):
        employee = payslip.employee
        content = pdf.render(page(employee=employee, period=pay_run.period, payslip=payslip))
        document = Document.objects.create(
            employee=employee,
            doc_type="payslip",
            title=f"Payslip, {pay_run.period}",
            file=ContentFile(content, name=f"payslip-{pay_run.period}-{employee.employee_no}.pdf"),
            classification=Document.Classification.CONFIDENTIAL,
            created_by=request.user,
            updated_by=request.user,
        )
        record(request, "create", document, before=None, after=snapshot(document))
        payslip.document = document
        payslip.save(update_fields=["document"])
        if employee.user is not None and employee.user.is_active:
            notify(
                [employee.user],
                title=f"Your payslip for {pay_run.period}",
                body=f"Net pay {payslip.net}. Open My payslips to read or download it.",
                link="/payroll",
                dedupe_key=f"payslip:{payslip.id}",
            )
        issued += 1
    return issued
