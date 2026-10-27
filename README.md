# SAHAKAR–SEVA

SAHAKAR–SEVA is a foundation for a hyperlocal physical-services marketplace. Phase 1 establishes a production-conscious full-stack base without implementing marketplace workflows, authentication, payments, or simulated marketplace data.

## Stack

- **Web:** React, TypeScript, Vite, Tailwind CSS, local shadcn-style accessible components, React Router, TanStack Query, Lucide React
- **API:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Psycopg 3, Alembic, Pytest
- **Database:** PostgreSQL 16 with PostGIS
- **Local infrastructure:** Docker Compose

## Structure

```text
apps/web/       React frontend
services/api/   FastAPI service, SQLAlchemy models, Alembic migrations
docs/           Architecture and API contract notes
compose.yml     PostgreSQL, API, and web development services
```

## Prerequisites

Install Docker Desktop, Node.js 20+, npm, and Python 3.12+. Docker development is the most reproducible option on macOS.

## Option A: Docker development

**Hackathon MVP quick start:** `sh scripts/dev_up.sh`, then open http://127.0.0.1:5173. Demo steps, the local demo identity and troubleshooting are in `docs/audits/LIVE_DEMO_RUNBOOK.md`. API decisions are in `docs/contracts/MVP_MARKETPLACE_CONTRACT.md`.

```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

- Web: http://localhost:5173
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs

The database service includes a PostGIS health check. The API waits for PostgreSQL to become healthy before starting.

## Option B: Hybrid development

Start only PostgreSQL:

```bash
cp .env.example .env
docker compose up -d db
```

Run the API locally:

```bash
cd services/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, run the web app:

```bash
cd apps/web
npm install
npm run dev
```

## Tests and checks

```bash
cd services/api
pytest

cd ../../apps/web
npm run typecheck
npm run build
```

### Database tests (isolated test database)

Database integration tests (`services/api/tests/db`) run **only** against a separate test database set in `TEST_DATABASE_URL`. They never fall back to the development database. They refuse any URL whose database name lacks `test` or that matches `DATABASE_URL`, and they roll back every test's data. Create the test database once (it is idempotent, and leaves the dev DB and volume untouched):

```bash
docker compose up -d db
sh services/api/scripts/create_test_database.sh

cd services/api
export TEST_DATABASE_URL=postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test
pytest                       # all tests; tests/db fail clearly if TEST_DATABASE_URL is unset
```

Inside Docker: `docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://sahakar_test:sahakar_test@db:5432/sahakar_seva_test api python -m pytest tests/`. The API tests (`tests/api`) use in-memory SQLite and need no database.

### Seed data (Phase 3A service taxonomy)

After `alembic upgrade head`, run `python -m app.db.seed` from `services/api` (or `docker compose exec api python -m app.db.seed`). It inserts the initial low-risk categories and skills, is safe to re-run, and never modifies existing rows or user data. Use `--dry-run` to preview. See `docs/contracts/PHASE_3A_DATA_CONTRACT.md`.

## Configuration

Copy `.env.example` to `.env`. The API reads `DATABASE_URL`, `ALLOWED_ORIGINS` (comma-separated exact origins; `*` is rejected), and host/port settings.

Authentication (Phase 2): the API verifies Supabase bearer tokens with `SUPABASE_JWT_SECRET` (HS256, legacy shared-secret projects) or `SUPABASE_URL` + `SUPABASE_ANON_KEY` (server-side `/auth/v1/user` validation). With neither configured, protected endpoints fail closed with `503 AUTH_NOT_CONFIGURED`. These are server-only values; Compose passes them to the `api` container from the root `.env`.

Frontend: copy `apps/web/.env.example` to `apps/web/.env.local` and set `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY` (public anon/publishable key only — never a service-role or JWT secret).

After changing backend dependencies in `services/api/pyproject.toml`, rebuild the API image: `docker compose build api && docker compose up -d api`.

## Architecture boundary

Users are modeled as flexible identities that can later hire services, offer services, or participate in organizations. A worker profile is an optional capability profile and is not a verification claim. Organizations represent businesses or cooperatives, while memberships and organization permissions remain separate from personal user permissions. Future Supabase Auth identities will map to `users.external_auth_id`; no custom login system is included in this phase.

## Implemented vs planned

Implemented: service health endpoints, real database health checks, PostGIS-enabled local database, foundational models and migration, typed frontend API client, responsive structural pages, and development connectivity indicator.

Planned for later phases: authentication, worker discovery, jobs, applications, bookings, payments, maps, notifications, reviews, verification, and cooperative governance.

## Troubleshooting

- If the API cannot reach PostgreSQL, confirm `docker compose ps` shows `db` as healthy and that the local `DATABASE_URL` uses port `55432` (the Compose default avoids conflicts with an existing local PostgreSQL service).
- If the web app reports an API failure, start the API on port `8000` and verify http://localhost:8000/api/v1/health.
- If Docker ports are occupied, change the host-side ports in `compose.yml` and update `.env`.
- Re-run `docker compose exec api alembic upgrade head` after changing migrations.
