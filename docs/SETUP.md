# Development environment setup

Everything runs in containers. The host needs only Git and Docker Engine with the Compose plugin
(Docker Desktop on Windows or macOS is acceptable for developers; the server uses Docker Engine on Ubuntu).

## 1. Clone and configure

```bash
git clone <repository-url> gsa-hrms && cd gsa-hrms
cp .env.example .env
sh scripts/gen-secret.sh          # paste the two printed lines into .env
# set DB_PASSWORD to a local value; leave SMTP_* empty for development (emails print to the API log)
```

`.env` is git-ignored. Do not put real credentials in any tracked file, issue, or chat.

## 2. Start the stack

```bash
docker compose up -d --build
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
```

| URL | Purpose |
|---|---|
| https://hrms.localhost | Web application (Vite dev server with hot reload behind Caddy) |
| https://hrms.localhost/api/docs | OpenAPI documentation (Swagger UI); open to anyone in development, signed-in people only elsewhere (`API_DOCS_PUBLIC`) |
| https://hrms.localhost/api/health/ | Health check |
| https://hrms.localhost/admin/ | Django admin. Sign in through the web app first; the admin accepts only that session, after the authenticator code for privileged roles |

Caddy issues a local certificate for `hrms.localhost`; trust the Caddy root CA once
(`docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt`) or accept the browser warning.

## 3. Daily commands

```bash
docker compose logs -f api worker           # follow logs
docker compose exec api python manage.py makemigrations
docker compose run --rm api pytest -q --cov  # backend tests and coverage (PostgreSQL required)
docker compose exec api ruff check .         # lint
docker compose exec web npm run lint         # front-end lint
docker compose exec web npm run test         # front-end component and logic tests
docker compose exec web npm run build        # type-check and production bundle
bash scripts/e2e.sh                          # browser journeys, desktop and phone, with accessibility checks
docker compose down                          # stop; add -v to drop the database
```

## 3a. Seed data and first user

```bash
docker compose exec api python manage.py seed --country GY     # campuses, roles, leave types, holidays, reports
docker compose exec api python manage.py createsuperuser
```

The first administrator is the superuser created above. Everyone else gets an account from the Admin screen
in the web app (item 1.29): HR opens it from the staff record's email address, and the person receives an
invitation to choose their own password, which works once for 7 days. Roles are given and taken on the same
screen; who may give which role is set out in `api/iam/accounts.py`. Nobody ever chooses or sees another
person's password, and links sent in development print to the API log (`docker compose logs api`).
Administrator, HR Manager and Finance roles must enrol an authenticator app on first sign-in.

Before real records are loaded, the HR Manager publishes GSA's privacy notice from the Admin screen (Privacy
notice tab). A starting draft for GSA to complete is `docs/privacy/privacy-notice-draft.md`. Each person reads
and acknowledges it at their next sign-in, once for each version. `seed_demo --fictional` publishes a
demonstration notice, so on staging everyone sees it once.

## 3b. Import sample or migration data

```bash
docker compose exec api python manage.py import_staff --write-template /srv/files/import-template.xlsx
# fill the Units, Positions, Employees and LeaveBalances sheets, then validate without writing:
docker compose exec api python manage.py import_staff --file /srv/files/mon-repos-livestock.xlsx --dry-run
docker compose exec api python manage.py import_staff --file /srv/files/mon-repos-livestock.xlsx
```

The import is idempotent (natural keys: unit code, position number, employee number) and prints
a reconciliation table per sheet. Any validation error aborts the whole import with the sheet, row and
field named, so partial loads never happen. Identifiers are encrypted on the way in and never printed.

## 4. Branching and CI

- Work on short branches named after the Gold Standard Plan item (for example `feature/1.06-qualifications`).
  Branch protection on `main` is a repository setting the owner switches on (plan item 0.17).
- Open a pull request; CI runs every gate in the definition of done: lint and format, Django deployment
  checks, complete API documentation, backend tests with coverage, web tests and build, the page-weight
  budget, licence gates, known-vulnerability audits, browser journeys with accessibility checks, a secret
  scan of the whole history, and the production images. Merge only when green and reviewed.
  CONTRIBUTING.md has the commands to run each one locally.
- The workflow file is GitHub Actions syntax and runs unchanged on Forgejo or Gitea Actions if GSA hosts the repository in-country (Stack Definition decision item 9).

## 5. Production deployment (summary)

```bash
docker compose -f compose.yml -f deploy/compose.prod.yml up -d --build
docker compose exec api python manage.py migrate
```

Set `DOMAIN` to the public or internal name, `DJANGO_DEBUG=0`, and configure `deploy/Caddyfile.prod`
for public (automatic Let's Encrypt), internal CA, or `tls internal`. Backups use pgBackRest against the `db`
service volume; see the Development Specification section 4.5 for the full procedure.

## 6. Tooling inventory

| Tool | Role | Licence |
|---|---|---|
| Git, GitHub or Forgejo | Version control, reviews, CI | GPL-2 (Git), MIT (Forgejo) |
| Docker Engine, Compose | Reproducible environments | Apache 2.0 |
| Python 3.12, Django 5, DRF, drf-spectacular | Backend and API docs | PSF, BSD |
| Procrastinate | PostgreSQL-backed jobs | MIT |
| PostgreSQL 16 | Database | PostgreSQL |
| Node.js 22, Vite, React, TypeScript | Front-end | MIT, Apache 2.0 |
| Caddy 2 | TLS and reverse proxy | Apache 2.0 |
| ruff, pytest, pytest-cov, pip-audit, pip-tools | Backend quality gates and locked dependencies | MIT, Apache 2.0, BSD |
| oxlint, Vitest, Testing Library, jsdom | Front-end lint and tests | MIT |
| Playwright, axe-core | Browser journeys and accessibility checks (development only) | Apache 2.0, MPL 2.0 |
| gitleaks | Secret scan in CI | MIT |

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `scripts/e2e.sh` is slow the first time | It builds the hosted image and pulls the Playwright browsers (about 2 GB, stored wherever Docker keeps its data). Later runs reuse both. |
| A browser journey fails | Run `KEEP=1 bash scripts/e2e.sh`, then open `web/playwright-report/index.html`; screenshots and traces of the failure are in `web/test-results/`. |
| You want to see the screens a change touched | `SCREENSHOTS=1 bash scripts/e2e.sh` saves the main screens, desktop and phone, in `web/test-results/screens/`. |
| Saving an employee asks for a reason | Changes to the personal record must say why (item 1.08); the reason is kept in the file's history. |
| The admin sends you to the web app | Expected: sign in at the web app (with the authenticator code if your role needs one), then open `/admin/` again. |
| You are sent back to sign-in with "signed out after 30 minutes without activity" | The idle time-out (`SESSION_IDLE_MINUTES`). Sessions also end 8 hours after sign-in. My account lists every device signed in. |
| An upload is refused with "The file's contents do not match its name" | The file is not what its name says (for example a web page saved as `.pdf`). Save it again as a PDF or photograph. Limits: 10 MB for leave evidence, 20 MB for documents. |
| An invitation or password link does not arrive | In development, email prints to the API log (`docker compose logs api`). Elsewhere, check `SMTP_*` and the address on the account; until an invitation is used, "Send the invitation again" on the Admin screen sends it to the address now on the staff record. Links in the email start with `PUBLIC_URL`. |
| A password link says it has expired or been used | Invitations work for 7 days and resets for 60 minutes (`INVITATION_DAYS`, `PASSWORD_RESET_MINUTES`), once each; signing in also ends a reset link. Ask for a new one from the sign-in page. |
| "The audit log has been altered" | The nightly check (or "Check every entry now" on the Admin screen's Audit log tab) found an entry that no longer matches its fingerprint, or entries missing from the end. Treat it as a security incident: leave the database as it is, record the time, and compare with the latest backup. `docker compose exec api python manage.py verify_audit_chain` repeats the check from the command line. |
| The audit chain breaks after changing `FIELD_ENCRYPTION_KEY` | The fingerprints use a key derived from it. Before rotating the key, run `verify_audit_chain` and keep the result and the old key with the backups, so that the earlier entries can still be checked. |
| Someone is signed out after HR changed their roles | Expected: giving or taking a role ends the person's sessions, so the change, and any authenticator code it needs, applies from their next sign-in. |
| Sign-in answers "Too many failed sign-ins from this network" | 20 failed sign-ins from one address in 15 minutes, across any accounts. Wait 15 minutes, or raise `LOGIN_MAX_FAILURES_PER_ADDRESS` if a campus shares one address and the limit is too tight. |
| Document upload returns 500 and the API log shows `Permission denied: '/srv/files/...'` | The `files` volume was created before the image set its owner. Run `docker compose exec -u root api chown -R app:app /srv/files` once. |
| Tests report "skipped: database tests need PostgreSQL" | You ran pytest on the host against SQLite. Run `docker compose run --rm api pytest -q`. |
| Privileged user gets 403 with "Multi-factor verification is required" | Enrol and verify an authenticator code through the login screen (or `/api/v1/auth/mfa/`). |
