"""A letter as a PDF (item 1.19): the School's heading, the letter, and its reference on every page.

The page is built from escaped text only, and the PDF engine is given nothing it may fetch: no image, font,
style sheet or page from any address, so a letter can never be made to reach out to a server.
"""

import html
import re

from django.conf import settings

STYLE = """
@page {
  size: A4;
  margin: 20mm 20mm 24mm;
  @bottom-left { content: "Reference REF"; font: 8pt "DejaVu Sans", sans-serif; color: #555; }
  @bottom-right {
    content: "Page " counter(page) " of " counter(pages);
    font: 8pt "DejaVu Sans", sans-serif;
    color: #555;
  }
}
body { font: 11pt/1.45 "DejaVu Serif", serif; color: #111; }
.head { border-bottom: 2pt solid #2f6b46; padding-bottom: 5pt; margin-bottom: 16pt; }
.org { font: bold 15pt "DejaVu Sans", sans-serif; color: #2f6b46; }
.place { font: 9pt "DejaVu Sans", sans-serif; color: #444; }
.meta { width: 100%; border-collapse: collapse; margin-bottom: 14pt; font-size: 10pt; }
.meta td { padding: 0; }
.meta .on { text-align: right; }
.to { margin-bottom: 14pt; }
.subject { font-weight: bold; margin: 0 0 12pt; }
p { margin: 0 0 9pt; }
ul { margin: 0 0 9pt 16pt; padding: 0; }
.close { margin-top: 16pt; }
.sign { margin-top: 34pt; }
.foot { margin-top: 26pt; padding-top: 4pt; border-top: 0.5pt solid #bbb; font-size: 8pt; color: #555; }
"""
SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9/-]{1,30}$")


def _refuse(url, *args, **kwargs):
    raise ValueError(f"A letter fetches nothing, so not {url!r}.")


def page(*, template, values: dict[str, str], body_html: str, subject: str, check_code: str = "") -> str:
    """The whole letter as an HTML page, every piece of text escaped. The foot says how to check it is
    genuine: with its reference and code on the School's checking page (item 1.47)."""
    escape = html.escape
    reference = values["reference"]
    if not SAFE_REFERENCE.match(reference):
        raise ValueError("A reference holds only letters, digits, / and -.")
    place = " · ".join(v for v in (values["campus"], values["campus_address"]) if v)
    to = ""
    if template.addressed:
        unit_and_campus = ", ".join(v for v in (values["unit"], values["campus"]) if v)
        lines = [values["full_name"], values["post_title"], unit_and_campus]
        to = f'<div class="to">{"<br>".join(escape(line) for line in lines if line)}</div>'
    signatory = "<br>".join(escape(v) for v in (template.signatory_name, template.signatory_title) if v)
    if check_code:
        how = (
            f"To check that this letter is genuine, go to {escape(settings.LETTER_CHECK_URL)} and enter its "
            f"reference, {escape(reference)}, and the code {escape(check_code)}."
        )
    else:
        how = (
            "To confirm that this letter is genuine, contact Human Resources and quote reference "
            f"{escape(reference)}."
        )
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<title>{escape(subject)}</title>
<meta name="author" content="{escape(settings.LETTER_ORGANISATION)}">
<style>{STYLE.replace("REF", reference)}</style>
</head>
<body>
<div class="head">
<div class="org">{escape(settings.LETTER_ORGANISATION)}</div>
<div class="place">{escape(place)}</div>
</div>
<table class="meta"><tr>
<td>Our reference: {escape(reference)}</td>
<td class="on">{escape(values["today"])}</td>
</tr></table>
{to}
<div class="subject">{escape(subject)}</div>
{body_html}
<div class="close">Yours faithfully,</div>
<div class="sign">{signatory}</div>
<div class="foot">Issued through the GSA HRMS. {how}</div>
</body>
</html>"""


def render(html_page: str) -> bytes:
    from weasyprint import HTML  # loaded only when a letter is made: it is large

    return HTML(string=html_page, url_fetcher=_refuse).write_pdf()
