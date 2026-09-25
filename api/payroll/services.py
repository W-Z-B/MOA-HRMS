"""Payroll interface placeholders. Implemented in Release 2 once Finance confirms the payroll process."""

from datetime import date

from payroll.models import PayrollPeriod, StatutoryRate


def rate(kind: str, on: date):
    """Current value of a statutory parameter on a date, or None if Finance has not entered one."""
    row = StatutoryRate.objects.filter(kind=kind, effective_from__lte=on).order_by("-effective_from").first()
    return row.value if row else None


def build_change_file(period: PayrollPeriod) -> list[dict]:
    """Return the payroll change lines for a period: new hires, exits, unpaid leave, acting, overtime.

    Placeholder: the shape is fixed so the export and reconciliation report can be built against it.
    """
    return []


def build_nis_extract(period: PayrollPeriod) -> list[dict]:
    """NIS contribution lines per employee for the period. Placeholder until layouts are confirmed."""
    return []


def build_paye_extract(period: PayrollPeriod) -> list[dict]:
    """PAYE lines per employee for the period. Placeholder until layouts are confirmed."""
    return []
