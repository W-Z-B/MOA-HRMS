# ADR 0007: AI and automated decisions

**Status:** proposed (decision D4).
**Date:** 1 October 2026.

## Context

Feature 16 asks for AI-powered insight: performance, turnover, workforce planning and at-risk employees.
GSA's staff is small, so a model that predicts which individual will leave would rest on very few
cases and would be unreliable and unfair to the person it names. Sending staff data to an outside AI
service would be a transfer of personal data outside Guyana, which the Data Protection Act 2023 permits
only with adequate protection and safeguards or under its listed exceptions. Published commentary on
the Act refers to a provision on automated individual decision-making (section 19); GSA's legal adviser
should confirm its terms.

## Decision (recommended)

1. **Indicators, not predictions about people.** The HRMS calculates indicators inside the system:
   absence patterns, overdue appraisals, expiring certificates, long vacancies, contract endings. Each
   shows the evidence behind it (item 6.15).
2. **A person decides.** No decision about a person (hiring, pay, discipline, leave, confirmation) is
   made by the system alone. This is a rule in code review and in policy (item 6.17).
3. **No staff data leaves the system for an AI service** without GSA's written approval, given after the
   data protection impact assessment covers that use.
4. **Optional assistant** for policy and how-to questions, answering from GSA's published policies and
   guides only, with no personal data in what it is sent (item 6.16).

## Consequences

- Insight work (Phase 6) needs no external service and no transfer assessment.
- Indicators are explainable to staff and unions, and can be checked by a person.
- Any future use of a hosted AI model on personal data is a new decision with its own impact
  assessment.
