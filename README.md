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

The API integration tests use `TEST_DATABASE_URL` when supplied and otherwise target the local development database. Ensure PostgreSQL is running before running database tests.

## Configuration

Copy `.env.example` to `.env`. The API reads `DATABASE_URL`, `ALLOWED_ORIGINS`, and host/port settings. Supabase settings are intentionally optional placeholders; Phase 1 does not implement authentication.

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
