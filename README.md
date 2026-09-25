# GSA HRMS

Human Resource Management System for the Guyana School of Agriculture (Ministry of Agriculture).
Single-product, zero-extra-licence HRMS: web application, installable self-service app, REST API and
PostgreSQL database, packaged with Docker Compose for on-premise or cloud deployment.

Status: **development kick-off, Release 1 scope** (organisation and establishment, employee records,
contracts, documents, administration and security, leave, self-service, notifications, core reports).

## Repository layout

```
gsa-hrms/
  api/        Django 5 + Django REST Framework backend (Python 3.12+)
    config/   settings, urls, asgi/wsgi
    org/      campuses, units, positions, grades          (F01)
    people/   employees, assignments, contracts, documents (F02, F03, F04)
    leave/    leave types, ledger, requests, workflow      (F06)
    iam/      users, roles, scopes, MFA                    (F05)
    audit/    insert-only audit log                        (F05)
  web/        React 18 + TypeScript + Vite front-end and PWA
  deploy/     Caddyfile, production compose, scripts
  docs/       setup guide, architecture, component spec, ADRs
  .github/    CI workflow (also runs unchanged on Forgejo/Gitea Actions)
  compose.yml Development stack (PostgreSQL, API, web dev server, Caddy)
```

## Quick start (development)

Requirements: Docker Engine with the Compose plugin, Git. Nothing else is installed on the host.

```bash
git clone <repository-url> gsa-hrms && cd gsa-hrms
cp .env.example .env            # edit values; never commit .env
docker compose up -d --build
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
```

Open https://hrms.localhost (Caddy issues a local certificate). API docs at
https://hrms.localhost/api/docs. Full instructions: [docs/SETUP.md](docs/SETUP.md).

## Design

- [docs/architecture.md](docs/architecture.md): system diagram and request flow
- [docs/components.md](docs/components.md): component specification
- [docs/adr/](docs/adr/): architecture decision records
- Source documents (planning pack, specification, stack definition) live one folder up in the project.

## Rules

- Only permissively licensed components (MIT, BSD, Apache 2.0, PostgreSQL, PSF) may be added to the product.
  No AGPL, source-available or commercial dependencies. Check `docs/adr/0001-stack-selection.md`.
- Never commit secrets. `.env` is ignored; `.env.example` holds placeholders only.
- Every change goes through a pull request and the CI pipeline.
