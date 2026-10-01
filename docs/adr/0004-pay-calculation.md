# ADR 0004: Calculate pay in the HRMS

**Status:** proposed (decision D1). **Needs the owner's decision before Phase 4 starts; it changes the
contract scope.**
**Date:** 1 October 2026.

## Context

Features 11 and 32 to 36 of the brief describe pay runs, flexible pay periods, reprocessing, online
payslips, payroll compliance and pay adjustments. Every earlier GSA document kept payroll outside the
HRMS: the Planning Pack (assumption A4), the Kick-off Plan, the code (`payroll` holds placeholders) and
the commercial proposal, which lists payroll processing as outside its scope.

The rules are knowable and change most years. For 2026 (GRA notice of 26 February 2026, Income Tax
(Amendment) Act No. 3 of 2026): a personal allowance of G$140,000 a month or one third of income,
whichever is greater; 25 percent up to G$3,360,000 a year and 35 percent above; deductions for NIS,
insurance premiums, children, overtime and a second job; a mid-year change that employers had to
refund over later months. NIS is 5.6 percent from the employee and 8.4 percent from the employer up to
G$280,000 a month. Wages may be paid weekly, fortnightly or monthly, and deductions may not exceed one
third of wages (Labour Act, per the Ministry of Labour).

## Options

| Option | What the HRMS does | Value | Risk |
|---|---|---|---|
| A. Payroll interface | Monthly change file, NIS and PAYE extracts, reconciliation report; pay stays in GSA's current process | Medium | Low |
| B. Pay engine | Pay groups and calendars, pay runs with review and lock, payslips, GRA Form 5 and 7B, NIS schedule, bank file, journal | High: features 11 and 32 to 36 in full | Highest in the system: an error reaches people's pay |

## Decision (recommended)

Option B, delivered as Release 2, with these conditions:

1. Rules are data, one rule set per tax year with start dates; no tax figure is written in code.
2. GRA's own worked examples are reproduced to the dollar as automatic tests (item 4.07).
3. The person who prepares a pay run cannot approve it; after a run is locked, corrections are dated
   adjustments only (items 4.15 to 4.17).
4. Pay goes live only after three consecutive pay periods match GSA's existing payroll to the dollar
   (item 4.26), with Finance signing each comparison.

If Option A is chosen instead, item 4.25 replaces items 4.02 to 4.23 and features 32 to 36 are met only
in part (payslips and pay runs stay in GSA's current process).

## Consequences

- Contract scope and cost are revisited before Phase 4 begins, outside this repository, following the
  Procurement Act 2003 (the work is procured as one, never divided).
- Finance commits time to three parallel runs and to signing each one.
- Pay data counts as a financial record, which the Data Protection Act 2023 treats as sensitive personal
  data: pay views stay restricted to HR, Finance, the Principal and auditors, and bank details are
  encrypted (item 1.07).
