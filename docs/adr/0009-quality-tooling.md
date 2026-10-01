# ADR 0009: Test tooling, quality gates and locked dependencies

**Status:** proposed (decision D8). Implemented by pull request 15; merging it accepts this decision.
**Date:** 1 October 2026.

## Context

Gold standard is a set of measures with proof (the Gold Standard Plan). On 1 October 2026 the backend
had 74 tests and 90 percent coverage, but the web app had no tests, nothing checked accessibility or
the phone layout, dependencies were unpinned version ranges, and nothing checked licences, known
vulnerabilities or committed secrets.

## Decision

**Tools added (all development or CI only; none ships in the product):**

| Tool | Licence | Use |
|---|---|---|
| Vitest, @vitest/coverage-v8, jsdom | MIT | Web component and logic tests with coverage thresholds |
| Testing Library (react, dom, jest-dom, user-event) | MIT | Tests that act as a user would |
| Playwright (@playwright/test and its container image) | Apache-2.0 | Browser journeys on desktop and a 360px phone |
| @axe-core/playwright, axe-core | MPL-2.0 | WCAG 2.2 AA checks on every journey screen |
| pytest-cov | MIT | Backend coverage threshold |
| pip-audit | Apache-2.0 | Known vulnerabilities in the locked Python packages |
| pip-tools | BSD-3-Clause | Locks Python dependencies with hashes |
| gitleaks (container image in CI) | MIT | Secrets in the whole git history |

**Gates (CI, `.github/workflows/ci.yml`):** ruff lint and format; Django checks including
`check --deploy`; complete OpenAPI documentation (`--fail-on-warn`); backend tests with coverage at
least 88 percent; web lint, type-check, tests with coverage thresholds and a production build; a
page-weight budget for the application shell; licence gates for Python and the web; pip-audit and npm
audit; browser journeys with accessibility and reflow checks; gitleaks; production images carry no test
tools.

**Locked dependencies:** `api/requirements.in` lists what the product needs; `requirements.txt` and
`requirements-dev.txt` pin the whole tree with hashes and images install with `--require-hashes`.
`web/package-lock.json` pins the web tree. GitHub Actions are pinned to commits. An upgrade is a pull
request that re-locks and passes every gate, then is rehearsed on staging.

**Approved in principle, added with the feature that needs them:** a router library, a chart library,
and push-notice libraries (ADR 0005; those ship and need named licence exceptions).

## Consequences

- Every change, including an upgrade, is proven by the same gates before it merges.
- A pull request takes longer in CI (about ten minutes, mostly the browser journeys).
- Base images (Python, Node, Caddy, PostgreSQL) still follow version tags so that security patches
  arrive. Pinning them by digest needs automated update pull requests (Dependabot or Renovate), which is
  a repository setting for the owner to decide.
