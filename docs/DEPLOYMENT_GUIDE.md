# SAHAKAR–SEVA — Cloud Deployment Guide

Target: **Vercel** (frontend) + **Render** (FastAPI API, Docker Web Service) + **Neon** (PostgreSQL 16
+ PostGIS) + **Supabase Auth** (production identity). Payments remain **simulated**. External
timestamping stays **off** unless you deliberately configure a TSA.

This guide prepares and documents the deployment. It does **not** deploy anything for you, and it never
asks you to commit a secret. Commands you must run are marked **[USER ACTION]**. Where a real external
credential is required, you provide it; this guide never invents one.

Repository config added for deployment (see [`audits/CLOUD_DEPLOYMENT_READINESS.md`](audits/CLOUD_DEPLOYMENT_READINESS.md)):
`services/api/render.yaml` (Render Blueprint), `apps/web/vercel.json`, and a production-safe
`services/api/Dockerfile` start command that honors Render's `$PORT`.

> **Release gates (read first).** Two items are **not verifiable in this preparation pass** and must be
> confirmed by you on real infrastructure before calling the deployment done:
> 1. **Real Supabase login end-to-end** (no real Supabase project exists in this workspace).
> 2. **A hosted judge-demo dataset** — the seeder intentionally refuses non-development databases and is
>    not weakened. See §11.

---

## 1. Render + Neon project creation

**[USER ACTION]**
1. Create a **Neon** account (database) and a **Render** account (backend). The frontend is hosted
   separately on Vercel (§7). Authentication is Supabase (§6).
2. Optional CLIs: Neon CLI (`neonctl`) and Render CLI are available but the dashboard steps below are
   sufficient.
3. Pick one cloud region family and keep Render and Neon **in the same region** (e.g. both US-East or
   both US-West) to minimize API↔DB latency, since the DB is external to Render.

## 2. Neon PostGIS database setup

Neon is a serverless Postgres. It supports the `postgis` and `btree_gist` extensions this project needs.

**[USER ACTION]**
1. In Neon, **create a project** and choose **PostgreSQL 16** (for parity with local and CI).
2. Neon creates a default database and role. Note the **connection details**. Neon gives you two
   endpoint styles:
   - **Direct** (e.g. `ep-xxx.<region>.aws.neon.tech`) — a normal Postgres endpoint.
   - **Pooled** (host contains `-pooler`) — PgBouncer in transaction mode.
   **Use the DIRECT endpoint for this app** (see §4 for why).
3. Neon **requires TLS**: the connection string must include `sslmode=require`.
4. The required extensions are created by the application's **migrations** (`0001` creates `postgis`,
   `0004` creates `btree_gist`) via `CREATE EXTENSION IF NOT EXISTS …`. Neon permits these for your
   project role, so no manual step is normally needed. If your role cannot create them, run once in the
   Neon SQL editor:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS btree_gist;
   ```
   (UUIDs are generated in application code, so no `uuid-ossp`/`pgcrypto` is required.)
5. Neon persists data automatically (no volume to attach). Note: on the **free** plan a project may
   **scale to zero** when idle, causing a brief cold start on the next query — acceptable for a demo.
6. Use credentials **separate** from your local development database. Do not reuse the local password.

Driver note: the app uses the `psycopg` (v3) SQLAlchemy driver, so the URL must start with
`postgresql+psycopg://`. Neon shows `postgresql://…`; convert the scheme and keep the query string, e.g.:
```
postgresql+psycopg://<user>:<password>@<direct-host>/<db>?sslmode=require
```

### Neon connection-pooling compatibility (important)

The app relies on **transaction-scoped PostgreSQL advisory locks** (`pg_advisory_xact_lock`, used to
serialize the financial event chain and checkpoints), PostGIS **GiST** indexes, and a booking
**exclusion constraint** (`ex_bookings_worker_no_overlap`). These are all ordinary
transactional/DDL features and work on Neon.

- **Direct endpoint (recommended):** behaves exactly like the local/CI Postgres this project was tested
  against. All transaction, locking and concurrency tests (`tests/db/test_booking_concurrency.py`,
  `tests/db/test_trust_concurrency.py`) reflect this behavior. **No code change required.**
- **Pooled endpoint (`-pooler`, PgBouncer transaction mode):** advisory **xact** locks still work
  (released at transaction end), but `psycopg` v3 uses server-side **prepared statements** by default,
  which PgBouncer transaction pooling does not support and which can raise "prepared statement already
  exists" errors. The app does not currently disable client-side prepared statements, so **do not use
  the pooled endpoint as-is**. If you later need many connections, use the pooled host **and** disable
  prepared statements (psycopg `prepare_threshold=None` via SQLAlchemy `connect_args`) — a small, tested
  change — before switching.

Bottom line: **use the Neon direct endpoint** for both the app and migrations to preserve the exact
tested behavior.

## 3. Render backend (FastAPI) deployment

The API ships with a production-ready `services/api/Dockerfile` (uvicorn, **no `--reload`**, binds
`0.0.0.0:$PORT`, runs behind Render's proxy). `services/api/render.yaml` describes the service.

**[USER ACTION]** — Blueprint (recommended) or manual:
- **Blueprint:** Render Dashboard → **Blueprints → New Blueprint Instance** → pick this repo + branch
  **`shresthBranch`**. Render reads `services/api/render.yaml` and creates the `sahakar-seva-api` web
  service (Docker, `rootDir=services/api`, health check `/api/v1/health`, free plan, `autoDeploy:false`).
- **Manual:** **New → Web Service** → connect the repo, branch `shresthBranch` → **Root Directory** =
  `services/api` → **Runtime** = Docker → Render auto-detects the `Dockerfile` → **Health Check Path** =
  `/api/v1/health` → plan **Free**.

Render injects `PORT` (free web services typically use `10000`); the container already binds `$PORT`. Do
**not** set a start command containing `--reload` or a migration. Set the environment variables in §4,
then deploy.

**Render Free limitations to expect:**
- **Cold starts:** a free web service **spins down after ~15 minutes of inactivity**; the next request
  wakes it and can take ~30–60 s. Warn judges, or hit the health URL to pre-warm before a demo.
- **No Pre-Deploy Command / Shell on free:** Render's pre-deploy (release) command and the in-dashboard
  Shell are **paid-tier** features. Do **not** rely on them for migrations — run migrations explicitly
  from your machine against the Neon direct URL (§5). The image deliberately does **not** migrate on
  start, so replicas never race.
- One free instance; no horizontal scaling.

## 4. Backend environment variables (Render → service → Environment)

Set these in the Render service. `render.yaml` marks the secret ones `sync: false` (dashboard-entered).
Never put any of these in the frontend.

| Variable | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | Must not be `development`. (Pre-set in `render.yaml`.) |
| `DATABASE_URL` | `postgresql+psycopg://…neon-direct…?sslmode=require` | Neon **direct** endpoint, `+psycopg` scheme, `sslmode=require`. |
| `ALLOWED_ORIGINS` | `https://<your-app>.vercel.app` | Exact frontend origin(s), comma-separated. Wildcard `*` is rejected. Add a custom domain too if used. |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | Enables server-side token validation (asymmetric-safe). |
| `SUPABASE_ANON_KEY` | `<supabase anon/publishable key>` | Public anon key only; used server-side to call `/auth/v1/user`. |
| `SUPABASE_JWT_SECRET` | *(leave unset)* | Only for legacy shared-secret projects. Leave empty for modern asymmetric projects (§6). |
| `DEV_AUTH_ENABLED` | `false` | Must be false in production (the app refuses to start otherwise). (Pre-set.) |
| `ANCHOR_WORKER_ENABLED` | `false` | Leave off unless you configure a TSA (§9). (Pre-set.) |
| `TSA_URL` / `TSA_CA_FILE` | *(unset)* | Only if you intentionally enable external timestamping (§9); must be set together. |

Do **not** set `DEV_AUTH_SECRET`/`DEV_AUTH_PASSCODE` in production. Do **not** copy the local root
`.env` into Render.

## 5. Migration execution (explicit, one-off)

Run migrations **once** against the Neon database, as an explicit authorized step — never automatically
in the API container (and Render free has no pre-deploy/shell anyway).

**[USER ACTION]** From `services/api` on your machine, pointed at the Neon **direct** URL:
```
cd services/api
DATABASE_URL="postgresql+psycopg://<user>:<password>@<direct-host>/<db>?sslmode=require" \
  alembic upgrade head
```
Verify: `alembic current` should report **`0007_demo_provenance`**. Use the **direct** (non-pooled) URL
for migrations (DDL + `CREATE EXTENSION` + advisory locks). Migrations are additive (`0001`→`0007`);
historical migrations are never modified. Take a Neon branch/snapshot before running (§17).

> **Never point this command at an unidentified remote database.** Confirm the host is your Neon
> project before running. The seeder and test harness refuse unknown/remote databases by design.

## 6. Supabase Auth setup (production identity)

The API verifies every protected request. The **recommended production path is Mode B**
(`app/core/security.py`): the API calls `GET {SUPABASE_URL}/auth/v1/user` with the user's bearer token
and the anon key. This works for **asymmetric (RS256/ES256) signing keys** because validation is
delegated to Supabase — you do **not** need the project's JWT secret, and you must **not** assume a
legacy shared secret exists.

**[USER ACTION]**
1. Create a Supabase project. In **Project Settings → API**, copy the **Project URL** and the **anon /
   publishable key**.
2. Backend (Render §4): set `SUPABASE_URL` and `SUPABASE_ANON_KEY`; leave `SUPABASE_JWT_SECRET` unset.
3. Frontend (Vercel §8): set `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and `VITE_AUTH_MODE=supabase`.
4. In **Authentication → URL Configuration**, set the **Site URL** to your Vercel URL and add it to
   **Redirect URLs** (email confirmation / password recovery / OAuth callbacks).
5. Choose your auth methods (email/password, magic link, OAuth) in the Supabase dashboard.

Issuer/audience: Supabase tokens carry `aud="authenticated"`; Mode B relies on Supabase's own validation
of signature, issuer and expiry. (The optional Mode A HS256 path additionally checks `aud` and expiry
locally, but is only for legacy shared-secret projects.)

> **Release gate:** after deploying, perform the end-to-end login verification in §13. It has not been
> exercised in preparation because no real Supabase project exists in this workspace.

## 7. Vercel frontend deployment

`apps/web/vercel.json` pins the Vite framework preset, install/build commands, output directory, and SPA
rewrites.

**[USER ACTION]**
1. Vercel → **Add New → Project**, import this repository.
2. Set **Root Directory** to **`apps/web`**.
3. Framework preset: **Vite** (auto-detected). Build: `npm run build`; Output: `dist`; Install:
   `npm ci` (all pinned by `vercel.json`).
4. Set the environment variables in §8 **before** the first build (Vite inlines them at build time).
5. Deploy. Note the assigned `https://<app>.vercel.app` URL — put it into the backend `ALLOWED_ORIGINS`
   (§4) and Supabase redirect URLs (§6).

## 8. Frontend environment variables (Vercel → Project Settings → Environment Variables)

These are **build-time** public values. Never put a database URL, service-role key, or JWT secret here.

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://<your-api>.onrender.com` (your Render API HTTPS URL) |
| `VITE_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | `<supabase anon/publishable key>` |
| `VITE_AUTH_MODE` | `supabase` |

If any of `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` are missing or placeholders,
the app **silently falls back to fixtures mode** (`apps/web/src/lib/api-adapter.ts`). Set all three to
real values so the deployed build talks to the real Render API. Verify with §12.

## 9. Domains, CORS and redirect URLs

- **CORS:** set the API's `ALLOWED_ORIGINS` to the exact Vercel origin(s) — e.g.
  `https://sahakar-seva.vercel.app` and any custom domain. The wildcard `*` is rejected because the API
  allows credentialed requests.
- **Custom domains:** if you add one in Vercel, add it to `ALLOWED_ORIGINS` and Supabase redirect URLs.
- **API URL:** the frontend must point at the Render API (`VITE_API_BASE_URL`), never `localhost`. Render
  serves HTTPS on `*.onrender.com` by default.

## 10. CORS and redirect verification

**[USER ACTION]** After both are live:
```
# Allowed origin -> should echo your Vercel URL in access-control-allow-origin
curl -s -D - -o /dev/null -X OPTIONS https://<your-api>.onrender.com/api/v1/users/me \
  -H "Origin: https://<app>.vercel.app" -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
# Disallowed origin -> should return NO access-control-allow-origin header
curl -s -D - -o /dev/null -X OPTIONS https://<your-api>.onrender.com/api/v1/users/me \
  -H "Origin: https://evil.example" -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
```
Both behaviors were verified locally against the production image (allowed → ACAO header; disallowed →
none).

## 11. Hosted judge-demo data preparation

**The automatic demo seeder is development-only by design and is not weakened for the cloud.**
`app/cli/seed_demo.py` / `app/demo/seed.py` refuse to run unless `APP_ENV=development` against a local,
non-remote, non-Supabase, non-test database at migration head. A hosted Neon database (with
`APP_ENV=production`) will be **refused** — this guard is intentional and preserved.

Options, in order of preference:
1. **Keep the fully-seeded local demo as the primary judge demo** (reliable, already validated, with
   screenshots in `docs/assets/`). Recommended. See [`JUDGE_REVIEW_GUIDE.md`](JUDGE_REVIEW_GUIDE.md) and
   [`audits/LIVE_DEMO_RUNBOOK.md`](audits/LIVE_DEMO_RUNBOOK.md).
2. **A dedicated, access-controlled judge-staging environment** (optional, manual): a separate Render
   service + Neon database + Supabase project, with **real Supabase demo accounts** you create in the
   Supabase dashboard, and sample records generated through the **real API** (not the dev seeder). This
   keeps production-grade auth and disables no safeguard. It is manual work and **out of scope** for this
   preparation pass.

Do **not** copy the local database/volume into Neon, and do **not** set `APP_ENV=development` on a public
service to trick the seeder (that would also re-enable dev auth and is forbidden). If no hosted dataset
is created, the public marketplace counts are simply empty, which is honest.

**Status: hosted demo data is BLOCKED/manual** (see readiness report). The local demo is the dependable
option.

## 12. Health checks

- **Liveness:** `GET https://<your-api>.onrender.com/api/v1/health` → `{"status":"ok","service":"api"}`.
  Render's health check uses this path (`render.yaml`). (First hit after idle may be slow — cold start.)
- **Database:** `GET https://<your-api>.onrender.com/api/v1/health/db` →
  `{"status":"ok","database":"connected"}` once migrations are applied and `DATABASE_URL` (Neon,
  `sslmode=require`) is correct.
- **Frontend not in fixtures mode:** open the site; DevTools should show **no** "Dev fixtures active"
  warning and the mode badge should read "Production API"; network calls go to your Render API.

## 13. Production-auth end-to-end verification (release gate)

**[USER ACTION]** — must pass before declaring auth done:
1. Open the Vercel site → **Sign up** with a real email → complete Supabase email confirmation → land
   authenticated.
2. **Log out**, then **log in** again.
3. Confirm a **protected** route works while logged in (e.g. `/dashboard`, `/bookings`) and the API
   accepts the Supabase bearer token (no `AUTH_NOT_CONFIGURED`/`401`).
4. Let the session **expire** (or revoke it in Supabase) and confirm protected calls then return `401`
   and the UI returns to login.
5. Confirm `POST /api/v1/dev-auth/token` returns **404** on the deployed API (dev auth disabled).

Locally verified in preparation: with no Supabase configured, protected endpoints fail closed with
`503 AUTH_NOT_CONFIGURED`, and `/dev-auth/token` returns `404` under `APP_ENV=production`,
`DEV_AUTH_ENABLED=false`. **Real Supabase login itself was not tested here** (no real project).

## 14. Financial ledger verification

The deployed system preserves the full ledger stack (unchanged code): configurable fee policies,
versioned quote acceptance, balanced double-entry ledger, SHA-256 event chain, Merkle checkpoints,
receipt export, offline verification and tamper detection.

**[USER ACTION]** After a completed booking on the hosted site (or via the local demo):
- Verify a receipt offline: `python3 scripts/verify_receipt.py receipt.json` → `LOCAL INTEGRITY VERIFIED`.
- Tamper and confirm rejection: `python3 scripts/tamper_receipt.py receipt.json --mode payload
  --worker-share 40000 --out bad.json && python3 scripts/verify_receipt.py bad.json` → `VERIFICATION
  FAILED`.

**External anchoring:** unless you set `TSA_URL`+`TSA_CA_FILE` (together) and enable the anchor worker,
checkpoints stay `LOCAL_ONLY` and receipts report "local integrity only". **Do not claim an external
anchor exists** unless you configured a TSA and independently verified a timestamp. Payments are
**simulated**; do not configure real payment collection, escrow, or wallets.

## 15. Security checks

- No secrets are committed (`.env`/`.env.*` are git-ignored; the only committed PEM is the **public**
  DigiCert TSA root). The deployment image contains no `.env` (verified).
- `APP_ENV=production` + `DEV_AUTH_ENABLED=false`: dev auth cannot start or issue/accept tokens.
- Use **HTTPS** everywhere (Vercel and Render provide TLS; Neon requires `sslmode=require`).
- `ALLOWED_ORIGINS` is an explicit allowlist; no wildcard.
- Neon enforces TLS; keep the database credentials out of Git and the frontend. Use a Neon role scoped
  to the app database; rotate anything that has been on disk locally.
- Authorization: organization reporting is owner/admin-only; dispute review requires a server-granted
  reviewer role (`app/cli/grant_reviewer.py`) — never a client claim.
- Public endpoints expose locality/distance only, never addresses or coordinates.
- **Not implemented — residual risk:** application-level rate limiting for public, auth-sensitive and
  resource-intensive endpoints. Add limits at Render/edge or a proxy before heavy public traffic. See
  [`SECURITY_AND_TRUST_MODEL.md`](SECURITY_AND_TRUST_MODEL.md).
- Do **not** reuse the local Supabase password or dev signing secret as cloud credentials.

## 16. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Frontend shows "Dev fixtures active" / mode badge not "Production API" | A `VITE_*` var missing at build time. Set all three (§8) and **redeploy** (Vite inlines at build). |
| API `503 AUTH_NOT_CONFIGURED` on protected routes | `SUPABASE_URL`/`SUPABASE_ANON_KEY` not set on the API, or wrong values (§4/§6). |
| Browser CORS error | `ALLOWED_ORIGINS` does not exactly match the frontend origin (scheme + host, no trailing slash). |
| `/api/v1/health/db` fails | Migrations not run (§5); `DATABASE_URL` missing `+psycopg` or `sslmode=require`; wrong Neon host. |
| `prepared statement "…" already exists` / pooling errors | You used the Neon **pooled** (`-pooler`) endpoint. Switch to the **direct** endpoint (§2). |
| First request very slow / 502 then OK | Render free **cold start** (spun down after ~15 min idle) and/or Neon scale-to-zero. Pre-warm by hitting `/api/v1/health`. |
| Refreshing `/hire`, `/bookings`, etc. gives 404 | `apps/web/vercel.json` SPA rewrite missing or root dir wrong; confirm root = `apps/web`. |
| API boots then restarts | Check `APP_ENV=production`, and that no start command injects `--reload`/migration. |
| `CREATE EXTENSION` permission error during migration | Pre-create `postgis`/`btree_gist` in the Neon SQL editor (§2), then re-run migrations. |
| Dev auth reachable in prod | `DEV_AUTH_ENABLED` not `false`; the app should refuse to start if it's true with `APP_ENV=production`. |

## 17. Rollback and recovery

- **Database backup before migrating:** use **Neon branching** (create a branch of the database as an
  instant restore point) or `pg_dump` via the direct URL **before** §5, and on a schedule. Test a
  restore once (Neon: restore/point-in-time or `pg_restore`).
- **API rollback:** Render keeps previous deploys — use **Rollback** to a prior successful deploy, or
  push a revert commit to `shresthBranch`.
- **Frontend rollback:** Vercel keeps immutable deployments — **Promote** a previous deployment.
- **Migrations:** additive; a downgrade (`alembic downgrade -1`) is possible but rehearse on a Neon
  branch first and only after a backup. Prefer roll-forward fixes.
- **Secret rotation:** if any cloud secret leaks, rotate it in Supabase/Neon/Render and redeploy; never
  commit it.

---

For what is and isn't verified, the exact files changed, and remaining blockers, see
[`audits/CLOUD_DEPLOYMENT_READINESS.md`](audits/CLOUD_DEPLOYMENT_READINESS.md).
