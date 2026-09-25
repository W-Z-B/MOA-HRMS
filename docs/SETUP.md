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
| https://hrms.localhost/api/docs | OpenAPI documentation (Swagger UI) |
| https://hrms.localhost/api/health/ | Health check |
| https://hrms.localhost/admin/ | Django admin (development only) |

Caddy issues a local certificate for `hrms.localhost`; trust the Caddy root CA once
(`docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt`) or accept the browser warning.

## 3. Daily commands

```bash
docker compose logs -f api worker           # follow logs
docker compose exec api python manage.py makemigrations
docker compose exec api pytest -q            # backend tests
docker compose exec api ruff check .         # lint
docker compose exec web npm run lint         # front-end lint
docker compose exec web npm run build        # production bundle check
docker compose down                          # stop; add -v to drop the database
```

## 4. Branching and CI

- `main` is protected. Work on `feature/<id>-<short-name>` branches named after the requirement ID (for example `feature/F06-leave-ledger`).
- Open a pull request; CI runs lint, migration check, tests, front-end build and a compose validation. Merge only when green and reviewed.
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
| ruff, pytest, ESLint | Quality gates | MIT |
