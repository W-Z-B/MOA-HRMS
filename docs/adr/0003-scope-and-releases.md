# ADR 0003: Scope and releases from the 36-feature brief

**Status:** proposed (decisions D0 and D6 of the Gold Standard Plan). The owner said "let us proceed
with the GSA HRMS gold standard plan" on 1 October 2026; written confirmation of D0 and D6 is still
needed before the Kick-off Plan's dates are changed.
**Date:** 1 October 2026.

## Context

On 1 October 2026 the owner set out 36 features (People Managing People, "key features of HRMS
software") as the features, principles and cores the HRMS must inherit. The Gold Standard Plan checked
each against the build and against Guyana's law. The list adds pay, attendance, hiring, performance
and analytics to what the Kick-off Plan scheduled, and several items are written for United States
employers.

## Decision

1. **Scope.** The 36 features, as restated for Guyana and for GSA in the Gold Standard Feature Audit,
   plus the fifteen gaps the audit adds (leaving and settlement, discipline, incidents, privacy rights,
   approvals, migration, backups, accessibility, testing and others), are the full scope of the HRMS.
2. **Releases.**
   - Release 1: phases 0 to 2 (ground rules, core record and control, self-service, absence and phone)
     and the core reports (items 6.01 to 6.03). Go-live stays 7 May 2027.
   - Release 2: phases 3 and 4 (time, rosters, attendance; pay and benefits).
   - Release 3: phases 5 and 6 (hiring, onboarding, performance, training, engagement; full reports
     and analytics).
   - Phase 7 (assurance) gates every release.
3. **Restatements accepted (D6).**
   - Recruiting uses a structured application form and a GSA careers page, not CV parsing and job-board
     integrations.
   - Course delivery and the catalogue stay in the LMS; the HRMS keeps training records, certificates,
     competencies and training needs.
   - Cost estimates are by unit, roster and post, not by client project.
   - Gamification is light (onboarding progress, training badges, recognition) and comes last.
   - Healthcare compliance means NIS benefit claims, the tax deduction for insurance premiums, the
     confidentiality of medical documents and the Occupational Safety and Health incident register.
   - Equal opportunity monitoring follows ADR 0008.
4. **Change control.** Anything added to Release 1 displaces work of equal size or moves to a later
   release, as the Kick-off Plan already requires.

## Consequences

- The Kick-off Plan's release split is superseded once this is accepted; its Release 1 dates stand.
- Dates for Releases 2 and 3 are set at the Release 1 go-live review, from measured delivery speed
  rather than estimates (checklist item 0.15).
- Contract scope and cost are revisited if pay is calculated in the HRMS (ADR 0004); that is a
  commercial matter handled outside this repository.
- The one-owner rule of the GSA ecosystem holds: the HRMS owns staff, posts and training records; the
  SRMS owns students and results; the LMS owns courses and content.
