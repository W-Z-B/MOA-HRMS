# Contributing to the GSA HRMS

Work follows the Gold Standard Plan: every change is a numbered checklist item, built on a short branch,
proven by the CI gates and reviewed in a pull request. This page says how.

## 1. Branches and pull requests

- Branch from `main`, named after the checklist item: `feature/1.06-qualifications`,
  `fix/1.35-upload-limits`, `docs/0.19-threat-model`. Phase-wide work may use `feature/phase-1-<topic>`.
- Commit titles start with the item number: `1.06 Qualifications and employment history`.
- Open a pull request early, as a draft if it is unfinished. CI runs on every push.
- Squash-merge into `main` when every gate is green. Merging to `main` deploys to staging on Railway,
  so a merge is the owner's decision.
- A branch that builds on an unmerged one targets that branch, and is retargeted to `main` once the
  lower one merges.

## 2. Definition of done

An item is done only when all of these hold. The pull-request template repeats them.

1. The acceptance points are met and shown working on a phone and on a desktop.
2. Rules and permissions have automatic tests, including the cases that must be refused. A new endpoint
   joins the permission-matrix test.
3. Every change it makes, and every view of a sensitive item, writes an audit row.
4. Screens pass the accessibility checks (keyboard use, labels, contrast; axe in the browser journeys)
   and fit a 360px phone without sideways scrolling.
5. The user guide page, the administrator note and the API documentation are updated.
6. Reviewed, every CI gate green, and running on staging with fictional data.
7. The checklist item is marked done in the Gold Standard Plan, which is kept with the project's
   planning documents rather than in this repository.

## 3. Commands

Everything runs in containers; the host needs Git and Docker.

| Purpose | Command |
|---|---|
| Backend tests with coverage (threshold in `api/pyproject.toml`) | `docker compose run --rm api pytest -q --cov` |
| Backend lint and format | `docker compose exec api ruff check . && docker compose exec api ruff format --check .` |
| API documentation is complete | `docker compose exec api python manage.py spectacular --validate --fail-on-warn --file /dev/null` |
| Production security settings | `docker compose exec -e DJANGO_DEBUG=0 api python manage.py check --deploy --fail-level WARNING` |
| Web lint, tests with coverage, type-check and build | `docker compose exec web sh -c "npm run lint && npm run test:coverage && npm run build && npm run check:bundle"` |
| Browser journeys, accessibility and phone layout | `bash scripts/e2e.sh` (add `KEEP=1` to leave the stack up for a failure) |
| Licence gates | `node scripts/check_npm_licences.mjs` and, for Python, `docker compose run --rm -v "$PWD:/repo" -w /repo api python scripts/check_licences.py` |
| Known vulnerabilities | `docker compose exec api pip-audit --require-hashes --disable-pip -r requirements.txt -r requirements-dev.txt` |

The production security check needs a `DJANGO_SECRET_KEY` of at least 50 characters in the environment;
CI sets a placeholder.

## 4. Dependencies

- **Licences (ADR 0002).** Only permissive licences ship, plus named LGPL or MPL exceptions in
  `scripts/licence-policy.json`. A new exception is a reviewed change to that file with a reason.
- **Python.** Edit `api/requirements.in` (runtime) or `api/requirements-dev.in` (tools), then re-lock:

  ```bash
  docker compose exec api python -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements.txt requirements.in
  docker compose exec api python -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.txt requirements-dev.in
  docker compose build api
  ```

  Locking downloads every file to hash it and can take several minutes.
- **Web.** `docker compose exec web npm install --save-exact <package>@<version>` (add `--save-dev` for
  tools); commit `package.json` and `package-lock.json` together.
- An upgrade is its own pull request: re-lock, pass every gate, then rehearse on staging.

## 5. Rules that never bend

- No secrets in tracked files, issues, pull requests or chat. `.env` is ignored; `.env.example` holds
  placeholders. The secret scan runs over the whole history.
- No real personal data outside production. Development and staging use `seed_demo --fictional` only.
  Personal data of GSA staff stays in Guyana.
- Every write to personnel data goes through an audited view or service.
- No decision about a person is made by the system alone (ADR 0007).
- Significant decisions are written as decision records in `docs/adr/`.

## 6. Documents to know

- Decision records: [docs/adr/README.md](docs/adr/README.md)
- Threat model: [docs/security/threat-model.md](docs/security/threat-model.md)
- Data protection impact assessment: [docs/privacy/dpia.md](docs/privacy/dpia.md)
- Setup: [docs/SETUP.md](docs/SETUP.md); architecture: [docs/architecture.md](docs/architecture.md)
