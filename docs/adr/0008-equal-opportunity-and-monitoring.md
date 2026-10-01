# ADR 0008: Equal opportunity data and employee monitoring software

**Status:** proposed (decision D5).
**Date:** 1 October 2026.

## Context

Feature 25 describes the United States EEOC self-identification questionnaire. Guyana has no equivalent
duty. The Prevention of Discrimination Act 1997 prohibits discrimination in advertising, recruitment,
terms, promotion, training and dismissal on fifteen grounds, and once a case is raised the employer must
show it did not discriminate. Race, ethnic origin, religious and political beliefs, trade union
membership, health, sexual life and similar facts are sensitive personal data under the Data Protection
Act 2023.

The brief's second part also mentions employee recording and monitoring software as a type of HR
system.

## Decision (recommended)

1. **Questionnaire off by default.** If GSA asks for it, it is voluntary, kept apart from the
   application, never visible to the shortlisting panel, and reported only as totals for groups of five
   or more (item 5.09).
2. **Fair process instead.** Recruitment compliance comes from the process the system enforces: an
   advert wording check, one question bank and one score sheet for every candidate, recorded reasons for
   each decision, panel conflict declarations, and deletion of unsuccessful applicants' data on schedule
   (items 5.02, 5.05, 5.06, 5.08).
3. **No monitoring software.** The HRMS does not record screens, keystrokes, browsing or location over
   time. Attendance location is checked only at the moment of clocking in (ADR 0006).

## Consequences

- GSA's defence to a discrimination complaint rests on records of a consistent process, which the
  system keeps.
- No sensitive personal data is collected for monitoring purposes, which shrinks what the impact
  assessment has to justify.
