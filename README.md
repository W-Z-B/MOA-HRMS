# GSA HRMS

Human Resource Management System for the Guyana School of Agriculture (Ministry of Agriculture).
A single product with no additional software licences: web application, REST API and PostgreSQL
database, packaged with Docker Compose for on-premise or cloud deployment. All components are
MIT, BSD, Apache 2.0, PostgreSQL or PSF licensed (see `docs/adr/0001-stack-selection.md`).

**Status:** Release 1 in progress. Every module has models, migrations, an audited API and tests
(46 backend tests against PostgreSQL). Core HR, leave and notifications are usable end to end from the
web app; Release 2 modules are read-only scaffolds.

## Modules

| Directory | Requirement | State | What exists |
|---|---|---|---|
| `api/core` | shared | done | Base models, field encryption, seed command (campuses, roles, leave types, holidays, reports) |
| `api/audit` | F05 | done | Insert-only audit log (database trigger), same-transaction writes from every audited view |
| `api/iam` | F05 | done | Roles, campus and unit scopes, single permission layer, session login, TOTP multi-factor |
| `api/org` | F01 | done | Campuses, units, salary scales, effective-dated grades, positions with vacancy |
| `api/people` | F02, F03, F04 | done | Employees with encrypted identifiers and audited reveal, assignments (one substantive holder per post), contracts with their terms (hours, hourly rate, notice), documents, the employee's own terms and manager |
| `api/leave` | F06 | done | Leave types as data, ledger-derived balances, automatic checks (balance, overlap, eligibility, evidence), approval by the employee's own manager then HR, doctor's note beyond the sick-leave balance, receipt with the days left, entitlements per contract, monthly accrual and yearly grant jobs |
| `api/reports` | F17 | partial | Report definitions, establishment-versus-actual and headcount queries (JSON; PDF and Excel in Sprint 6) |
| `api/notifications` | F11 | done | In-app notifications with email delivery and per-key deduplication; leave workflow, contract-expiry and probation alerts feed it |
| `api/attendance` | F07 | scaffold | Shift patterns and attendance records, read-only |
| `api/performance` | F08 | scaffold | Appraisal cycles and appraisals, read-only |
| `api/training` | F09 | scaffold | Training records, read-only |
| `api/payroll` | F13, F14 | scaffold | Payroll periods, effective-dated statutory rates, placeholder change-file and extract builders |
| `web/` | F10 | partial | Installable web app laid out for phones (manifest, shell-only service worker, offline queue for leave requests); login with MFA; dashboard; people directory with tabbed file, create and edit, assignments, contract terms, document upload and audited reveal; leave: days left, request form that checks as it is filled in, photo of the doctor's note, progress of each request, approvals, receipt; My contract; notifications bell. Attendance, appraisals, payroll, reports and admin screens are placeholders |

API documentation is generated at `/api/docs`. Every endpoint lives under `/api/v1/`.

## Setup and build

Requirements on the host: Git and Docker Engine with the Compose plugin. Nothing else.

```bash
git clone git@github.com:W-Z-B/MOA-HRMS.git gsa-hrms && cd gsa-hrms
cp .env.example .env && sh scripts/gen-secret.sh      # paste the two lines into .env, set DB_PASSWORD
docker compose up -d --build
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed --country GY
docker compose exec api python manage.py createsuperuser
```

Open https://hrms.localhost (accept the local certificate on first visit). Sign in with the superuser,
enrol an authenticator app when prompted, and open People or the Dashboard.

| Command | Purpose |
|---|---|
| `docker compose run --rm api pytest -q` | Backend tests (need PostgreSQL, so run in the stack or CI) |
| `docker compose run --rm api ruff check .` | Lint |
| `docker compose exec web npm run lint && npm run build` | Front-end lint and production bundle |
| `docker compose -f compose.yml -f deploy/compose.prod.yml up -d --build` | Production stack |

Full guide: [docs/SETUP.md](docs/SETUP.md). Design: [docs/architecture.md](docs/architecture.md),
[docs/components.md](docs/components.md).

## Branching strategy

Trunk-based with short-lived branches.

- `main` is always deployable and is protected: pull request, one review, green CI.
- Branch names carry the requirement ID: `feature/F06-leave-ledger`, `fix/F02-mask-tin`, `docs/setup-guide`.
- Squash-merge into `main`; the commit title starts with the requirement ID.
- Releases are tags `v<major>.<minor>.<patch>`; `deploy/` scripts deploy a tag, never a branch.
- Hotfixes branch from the tag, merge to `main`, and are re-tagged.

## Next development milestones

| Milestone | Date | Scope |
|---|---|---|
| M1 walking skeleton and Gate 1 | 30 Oct 2026 | This scaffold deployed to the test VM; assumptions, budget and hosting confirmed by the Steering Committee |
| M2 core HR complete | 27 Nov 2026 | Employee file screens (tabs), document upload UI, sample data import for one unit per campus |
| M3 leave and self-service | 15 Jan 2027 | Leave screens, approvals, installable web app with offline queue, email notifications |
| M4 reporting and migration rehearsal | 12 Feb 2027 | Report pack with PDF and Excel, full migration rehearsal |
| M5 security verification | 12 Mar 2027 | Penetration test, restore drill, DPIA sign-off |
| M6 to M8 | Apr to Jun 2027 | UAT, go-live at both campuses, hypercare; Release 2 planning (attendance, appraisal, payroll interface) |

The Sprint 1 board is on GitHub: milestone "Sprint 1 (M1 walking skeleton and Gate 1)".

## Rules

- Only permissively licensed components may be added; check ADR 0001 in review.
- Never commit secrets. `.env` is ignored; `.env.example` holds placeholders only.
- Personal data of GSA staff stays in Guyana. Sensitive identifiers are encrypted and never logged in clear.
- Every write to personnel data goes through an audited view or service so an audit row is produced.

## GSA ecosystem

The HRMS is one of three separately built and deployed systems. It is the system of record for staff,
positions, campuses and organisational units; the SRMS (`SRMS/gsa-srms`) owns students and results; the
LMS (`LMS/gsa-lms`) delivers courses.

```bash
docker network create gsa-ecosystem                       # once per host
docker compose exec api python manage.py create_service_client --name srms --scopes staff:read org:read
docker compose exec api python manage.py create_service_client --name lms --scopes staff:read org:read training:write
docker compose -f compose.yml -f compose.ecosystem.yml up -d
```

| Endpoint (header `Authorization: Api-Key <key>`) | Scope | Used by |
|---|---|---|
| `GET /api/v1/integration/staff/` | `staff:read` | SRMS and LMS resolve lecturers by employee number |
| `GET /api/v1/integration/org/` | `org:read` | SRMS and LMS share campus and unit codes |
| `POST /api/v1/integration/training-completions/` | `training:write` | LMS reports staff training, idempotent on `external_ref` |

Keys are stored hashed, shown once, scoped, rotatable, and every call is written to the audit log against
the calling client. No integration endpoint exposes NIS number, TIN, national ID, date of birth or address.

## Hosted staging (Railway)

A staging and demonstration copy runs on Railway in the project "GSA Ecosystem", beside the other two
systems, with fictional data only. How it is built and configured: [deploy/railway/README.md](deploy/railway/README.md).

## Demonstration data

`seed_demo` loads an invented dataset for staging and development: four units, thirteen posts (three
vacant, one frozen), nine staff with appointments, contracts, leave balances and requests, and a
training record.
Every person is fictional, says so in the address line, and carries identifiers that start with `DEMO-`.
**Never run it on a database that holds real records.**

```bash
docker compose exec api python manage.py seed_demo --fictional
```

It is idempotent and leaves existing appointments alone. The employee numbers (E0001 to E0009) are the
lecturers named by the SRMS demonstration data, so load the systems in this order: HRMS, SRMS, LMS.

**Accounts.** With `DEMO_USER_PASSWORD` set in the environment, `seed_demo` also gives every invented
employee an account named `first.last` (for example `asha.persaud`), all with that password. Heads of
unit are supervisors and `natasha.khan` is the HR Officer, so one request can be followed from the
employee to the manager to Human Resources. Without the variable no account is created: a database that
can be reached from the internet never receives accounts with a password its owner did not choose.
An account that already exists keeps its password.
