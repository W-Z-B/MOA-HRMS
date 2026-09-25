# ADR 0001: Technology stack and licence policy

**Status:** accepted for Release 1, pending Steering Committee confirmation at Gate 1 (30 October 2026).
**Date:** 25 September 2026.

## Context

The HRMS must ship as a single product with no additional software licences, run identically on a GSA server
or a cloud VM, keep personal data in Guyana, and be maintainable by a small team. The Technology Stack
Definition evaluated four stacks; Stack A and Stack B tied, and Stack A was recommended.

## Decision

- Backend: Python 3.12, Django 5, Django REST Framework, drf-spectacular. Jobs: Procrastinate on PostgreSQL.
- Database: PostgreSQL 16. No separate cache, broker or search service.
- Front-end: React 18, TypeScript, Vite; self-service delivered first as an installable PWA.
- Edge and packaging: Caddy 2, Docker Engine, Docker Compose, Ubuntu Server LTS in production.
- Licence policy: only MIT, BSD, Apache 2.0, PostgreSQL or PSF licensed components in the shipped product.
  AGPL and source-available components (Redis 8, MinIO, Grafana, Sentry) are excluded from the product and
  may only be run by GSA as separate operational tools.

## Consequences

- One database to back up and secure; simpler operations for GSA IT.
- Native mobile apps and desktop installers are deferred to Release 2 and depend on app store account decisions.
- If the Phase 1 skills survey shows a PHP majority, Stack B (Laravel, Vue) can replace this decision before
  Sprint 1 with no loss of design artefacts; the schema, API contract and wireframes are stack-neutral.
- Every new dependency must be checked against the licence policy in code review.
