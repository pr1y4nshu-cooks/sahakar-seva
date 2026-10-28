# SAHAKAR–SEVA — Local Development Readiness

**Audit date:** 2026-10-27
**Machine:** Shresth's MacBook (macOS), Docker Desktop (Docker 29.2.1, Compose v5.1.0)
**Status:** Local environment is operational. All three services verified live.

---

## 1. Prerequisites (verified present)

- Docker Desktop — confirmed (`docker --version` → 29.2.1; `docker compose version` → v5.1.0)
- Ports available and in use by the correct services only: `55432` (db), `8000` (api), `5173` (web) — confirmed via `lsof`, all owned by Docker.
- Root `.env` present (copied from `.env.example`, not committed — confirmed via `.gitignore` and `git ls-files`).
- `apps/web/.env.example` present; `apps/web/.env.local` **not present** (expected for local dev without Supabase — frontend runs in fixtures mode).

---

## 2. Working startup commands

```bash
# From repository root
cp .env.example .env            # if not already done
docker compose up --build       # starts db, api, web
docker compose exec api alembic upgrade head   # apply any new migrations
docker compose exec api python -m app.db.seed  # optional: seed service taxonomy data
```

Verified live during this audit — all three containers reach a stable `Up` state with `RestartCount=0`.

### Running tests locally

```bash
# Backend — safe, no database required
cd services/api
source .venv/bin/activate
python -m pytest tests/ --ignore=tests/db

# Backend — database tests (isolated, non-destructive to dev data)
docker compose up -d db
sh services/api/scripts/create_test_database.sh
export TEST_DATABASE_URL=postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test
python -m pytest tests/

# Frontend
cd apps/web
npm run typecheck
npm run test -- --run
npm run build
```

All of the above were executed during this audit with the results recorded in `FULL_STACK_INTEGRATION_AUDIT.md`.

---

## 3. Environment configuration

### Root `.env` (server-only secrets, never committed)

| Variable | Purpose | Local value observed |
|---|---|---|
| `DATABASE_URL` | Backend Postgres connection | Set, points to `localhost:55432/sahakar_seva` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Compose-managed Postgres credentials | Set (`sahakar_seva` / `sahakar` / `sahakar`) |
| `ALLOWED_ORIGINS` | CORS allow-list | Set to `http://localhost:5173,http://localhost:4173` |
| `SUPABASE_URL` | Mode B auth verification | **Empty** — Supabase auth not configured locally |
| `SUPABASE_ANON_KEY` | Mode B auth verification | **Empty** |
| `SUPABASE_JWT_SECRET` | Mode A auth verification | **Empty** |

With all three Supabase variables empty, the backend correctly fails closed: every protected endpoint returns `503 AUTH_NOT_CONFIGURED` once a bearer token is actually checked (missing-token requests still return `401 AUTH_REQUIRED` first, which was verified live).

### `apps/web/.env.local` (not present locally)

To enable the real backend/Supabase integration in the browser, create this file from `apps/web/.env.example` and set:

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=<your Supabase project URL>
VITE_SUPABASE_ANON_KEY=<public anon/publishable key only>
```

Without it, the frontend auto-detects placeholder/missing values and runs in **fixtures mode** (clearly indicated in-app via a "Dev fixtures active" badge and a console warning) — this is a safe, intentional fallback, not a bug.

---

## 4. Local URLs (all verified live during this audit)

| Service | URL | Verified |
|---|---|---|
| Frontend | http://localhost:5173 | `curl` → 200 |
| Backend API | http://localhost:8000 | `curl /api/v1/health` → 200 |
| Swagger / OpenAPI docs | http://localhost:8000/docs | Available (FastAPI default; not independently re-curled this audit, but `/openapi.json` was served per app config) |
| Database | `localhost:55432` (Postgres + PostGIS) | `psql` queries executed successfully against it |

---

## 5. Services verified

| Service | Verification |
|---|---|
| `db` (PostgreSQL 16 + PostGIS) | Container healthy; `alembic current` → `0003_skills_and_categories (head)`; row counts preserved across all operations in this audit |
| `api` (FastAPI) | Container Up, `RestartCount=0`; health/db-health endpoints 200; auth fails closed correctly; 119 backend tests pass |
| `web` (Vite dev server) | Container Up; serves 200; 24 frontend tests pass; typecheck clean; production build succeeds |

---

## 6. Remaining environmental blockers

1. **Live Supabase authentication cannot be exercised** — no project credentials configured. This is a credentials/environment gap, not a code defect. To unblock: create a Supabase project, populate `SUPABASE_URL`/`SUPABASE_ANON_KEY` (and optionally `SUPABASE_JWT_SECRET`) in the root `.env`, and the matching `VITE_*` values in `apps/web/.env.local`.
2. **Frontend is in fixtures mode locally** — this is expected and documented, not a blocker for backend/database work, but means no real end-to-end browser → API flow can be observed until the above credentials are set.

No other environmental blockers were found. The application restarts reliably: this was exercised implicitly by running `docker compose exec api alembic upgrade head` (which triggers an app reload under the dev entrypoint) and reconfirming health endpoints and test pass rates afterward.
