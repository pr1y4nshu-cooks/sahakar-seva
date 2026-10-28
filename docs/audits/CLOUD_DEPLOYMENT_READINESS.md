# Cloud Deployment Readiness

Readiness audit for deploying SAHAKAR–SEVA to **Vercel** (frontend) + **Render** (API, Docker Web
Service) + **Neon** (PostgreSQL 16 + PostGIS) + **Supabase Auth**. This pass **prepared and validated
configuration locally**. **No cloud resource was created and nothing was deployed.** Step-by-step
instructions: [`../DEPLOYMENT_GUIDE.md`](../DEPLOYMENT_GUIDE.md).

> Supersedes the earlier Railway-targeted plan. The deployment target is now **Render + Neon**; the
> Railway blueprint (`services/api/railway.json`) was removed and replaced by `services/api/render.yaml`.

## Git status

| Item | Value |
|---|---|
| Branch | `shresthBranch` |
| HEAD | `48c3477` (in sync with `origin/shresthBranch`) |
| CI | GitHub Actions run `40613627138` → **success** (frontend + backend jobs) |
| Uncommitted (this pass) | `services/api/Dockerfile` (modified), `services/api/render.yaml` (new), `apps/web/vercel.json` (new), `docs/DEPLOYMENT_GUIDE.md` (rewritten), `docs/audits/CLOUD_DEPLOYMENT_READINESS.md` (this file); `services/api/railway.json` deleted (was never committed) |
| Migration head | `0007_demo_provenance` |

The deployment-config changes are in the working tree but **not committed** (per instructions).

## Files modified / added (deployment config only — no business logic changed)

| File | Change | Purpose |
|---|---|---|
| `services/api/render.yaml` | new | Render Blueprint: Docker web service, `rootDir=services/api`, `healthCheckPath=/api/v1/health`, free plan, `autoDeploy:false`, secret env vars `sync:false`, no startup migration. |
| `services/api/railway.json` | removed | Railway-specific; no longer the target. |
| `services/api/Dockerfile` | CMD honors `${PORT:-8000}` + `--proxy-headers`; no `--reload` | Works on Render ($PORT injected); local compose overrides the command so dev is unaffected. |
| `apps/web/vercel.json` | new | Vite preset; `npm ci`; build→`dist`; SPA rewrite `/(.*)→/index.html`. |
| `docs/DEPLOYMENT_GUIDE.md` | rewritten in place | Render + Neon steps (Supabase/Vercel unchanged). |

No changes to ledger, pricing, auth, or marketplace logic. Historical audit documents were not modified.

## Deployment configuration summary

- **Backend (Render Web Service, Docker):** image from `services/api`; production uvicorn (no reload)
  on `0.0.0.0:$PORT`; health `/api/v1/health`; migrations are an explicit one-off (Render free has no
  pre-deploy/shell). Expect free-tier cold starts (~15 min idle spin-down).
- **Database (Neon, PostgreSQL 16 + PostGIS):** `postgis` + `btree_gist` created by migrations;
  TLS-required (`sslmode=require`); **direct endpoint** for app + migrations.
- **Frontend (Vercel):** root `apps/web`, Vite preset, `dist`, SPA rewrites; points at the Render API.
- **Auth (Supabase):** server-side token validation (Mode B) — asymmetric-safe, no JWT secret required.

## Neon compatibility analysis (transaction/locking/concurrency)

- `DATABASE_URL` flows unchanged into both the SQLAlchemy engine (`app/db/session.py`,
  `pool_pre_ping=True`) and Alembic (`alembic/env.py`), so `?sslmode=require` is honored with **no code
  change**. `pool_pre_ping` also tolerates Neon's idle connection drops / scale-to-zero.
- PostGIS **geography** queries, **GiST** indexes, and the booking **exclusion constraint**
  (`ex_bookings_worker_no_overlap`, migration `0004`) are standard PostGIS/`btree_gist` features and work
  on Neon.
- The financial chain/checkpoints use **transaction-scoped advisory locks** (`pg_advisory_xact_lock`),
  which are released at commit and are compatible with transaction pooling.
- **Direct endpoint = tested behavior.** The **pooled** (`-pooler`, PgBouncer transaction) endpoint is
  **not** safe as-is because `psycopg` v3 uses server-side prepared statements by default; using it would
  require disabling them (`prepare_threshold=None`). The guide therefore specifies the **direct
  endpoint**, preserving the exact behavior covered by `tests/db/test_booking_concurrency.py` and
  `tests/db/test_trust_concurrency.py`.

## Secrets the user must configure (values never shown here)

**Render API service:** `APP_ENV=production` (pre-set), `DATABASE_URL` (Neon direct, `+psycopg`,
`sslmode=require`), `ALLOWED_ORIGINS` (Vercel origin), `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_JWT_SECRET` unset, `DEV_AUTH_ENABLED=false` (pre-set).
**Vercel project (build-time, public only):** `VITE_API_BASE_URL` (Render HTTPS URL), `VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY`, `VITE_AUTH_MODE=supabase`.
Do not reuse local dev credentials; do not copy the root `.env`; never put secrets in `VITE_*`.

## External services requiring manual setup

1. **Neon** account + PostgreSQL 16 project (direct connection string, `sslmode=require`).
2. **Render** account + Docker web service (`rootDir=services/api`).
3. **Supabase** project (URL + anon key; Site/Redirect URLs).
4. **Vercel** account + project (root `apps/web`).
5. (Optional) an **RFC 3161 TSA** for external anchoring (`TSA_URL` + `TSA_CA_FILE` together).

## Tests actually performed (this pass, local)

| Check | Result |
|---|---|
| Backend `pytest` (isolated PostGIS test DB) | **335 passed** (this session) |
| Frontend typecheck / `vitest` / build | **clean / 68 passed / build OK** |
| Migrations vs disposable `template0` DB | **pass** (incl. schema-drift test) — same path used for Neon |
| Production backend Docker image build | **success** (removed after test) |
| Prod container startup (safe config) | **ok** — `Uvicorn running on http://0.0.0.0:$PORT`, **no `--reload`** |
| `GET /api/v1/health` | **200** |
| `POST /dev-auth/token` under `APP_ENV=production, DEV_AUTH_ENABLED=false` | **404** |
| Protected endpoint, no Supabase | **503 `AUTH_NOT_CONFIGURED`** (fails closed) |
| CORS allowed / disallowed origin | **ACAO echoed / denied** |
| Secret inclusion in image | **none** (`.dockerignore` excludes `.env*`, `.venv`, caches) |
| `render.yaml` / `vercel.json` validity | **valid** |
| GitHub Actions CI on `shresthBranch` | **success** (run `40613627138`) |

Neon-specific items (SSL handshake, extension creation on Neon, cold start) **cannot be tested without a
real Neon project** and are documented as **[USER ACTION]** in the guide.

## Financial ledger / proofs status

Unchanged and intact: configurable agreements, versioned quote acceptance, balanced ledger, SHA-256
event chain, Merkle checkpoints, receipt export, offline verification, tamper-detection tests (all in the
backend suite; receipt verify + 3 tamper modes demonstrated this session). **External anchoring off by
default** → local-integrity status; no external anchor claimed. Payments remain **simulated**.

## Remaining blockers

1. **Real Supabase production login — NOT TESTED (release gate).** No real Supabase project in this
   workspace. Code path (Mode B) is asymmetric-safe and verified to fail closed; run the full
   signup/login/logout/expiry flow on the deployed stack (Guide §13).
2. **Neon connectivity (SSL, extensions, cold start) — NOT TESTED here.** No Neon project available;
   configuration and migration command are prepared and the local migration path is identical. Verify on
   the real Neon project (Guide §2, §5, §12).
3. **Hosted judge-demo data — BLOCKED/manual (by design).** Seeder refuses non-development databases and
   was **not** weakened. The dependable judge demo remains the **local** instance (seeded; screenshots in
   `docs/assets/`).
4. **No application-level rate limiting** — add at Render/edge/proxy before heavy public exposure.
5. **External TSA anchoring not configured** — intentional; local-integrity status unless configured.
6. **Render free cold starts / Neon scale-to-zero** — first request after idle is slow; pre-warm before a
   demo.

## Has cloud deployment been performed?

**No.** No Neon/Render/Vercel/Supabase resources were created, no remote migrations were run, and nothing
was deployed. Configuration was prepared and validated locally only.

## Exact next user actions

1. **Review** the uncommitted config changes (`git diff services/api/Dockerfile`; new
   `services/api/render.yaml`, `apps/web/vercel.json`; deleted `services/api/railway.json`).
2. **Authorize commit/push** (optional): if approved, commit to **`shresthBranch`** and push to
   **`origin/shresthBranch`** only (never `main`, no force). These files are safe to publish (no secrets).
3. **Provision** Neon (PG16 + PostGIS), Render (Docker web service), Supabase, and Vercel per the guide;
   set all environment variables (§4, §8).
4. **Run migrations once** against the Neon direct URL (Guide §5); confirm `alembic current` =
   `0007_demo_provenance`.
5. **Verify** health (§12), production auth E2E (§13 — release gate), CORS (§10), and a ledger receipt
   verify + tamper (§14).
6. Decide on hosted demo data (§11) — recommended: keep the local demo as primary.

Nothing here deploys automatically. Deployment and any commit/push await your explicit action/approval.
