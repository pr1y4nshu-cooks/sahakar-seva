# SAHAKAR–SEVA — Current State

Present-day technical source of truth. Where any older Phase 1–3 document disagrees with this file,
this file and the source code win. Phase documents under `docs/` are **development history**, not a
description of the current build.

_Verified on branch `shresthBranch`. Regenerate the test figures with the commands in
[`TESTING_AND_EVIDENCE.md`](TESTING_AND_EVIDENCE.md)._

## Repository / build identity

| Item | Value |
|---|---|
| Branch | `shresthBranch` |
| Latest commit | `947a5a6` — _feat(mvp): skills, location, availability, discovery, jobs, shared bookings, simulated settlement, disputes_ |
| Default remote branch | `origin/main` |
| Alembic migration head | `0007_demo_provenance` |
| Backend | Python ≥ 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Psycopg 3, Alembic |
| Frontend | React 18, TypeScript 5, Vite 6, Tailwind, React Router 7, TanStack Query |
| Database | PostgreSQL 16 + PostGIS (image `postgis/postgis:16-3.4`) |

> **Important working-tree note.** The trust-ledger, configurable pricing, demo seeder and the newest
> frontend pages are present in the **local working tree** (migrations `0005`–`0007` plus many modified
> and untracked files) but are **not yet committed**. `shresthBranch` is 10 commits ahead of
> `origin/shresthBranch`; neither `origin/shresthBranch` nor `origin/main` contains this work yet.
> See [`audits/FINAL_GITHUB_SUBMISSION_READINESS.md`](audits/FINAL_GITHUB_SUBMISSION_READINESS.md) for
> the exact publish steps.

## Migrations

`0001_foundation` · `0002_phase2_constraints` · `0003_skills_and_categories` ·
`0004_marketplace_core` · `0005_transparency_and_trust` · `0006_configurable_fee_policies` ·
`0007_demo_provenance`. Head = `0007`.

## Feature inventory (verified against source + tests)

Status legend: **Verified** = implemented and covered by executed tests; **Implemented** = present in
source and exercised in the demo but not independently re-verified here; **Simulated** = intentionally
not real (clearly labelled in UI/API); **Planned** = described, no code path.

| Area | Status | Notes / evidence |
|---|---|---|
| Health + DB health endpoints | Verified | `app/api/v1/health.py`; `tests/test_health.py` |
| User identity + worker profile + organizations | Verified | `tests/api/*`, `tests/db/test_*_repository.py` |
| Supabase token verification (HS256 or server-side `/auth/v1/user`) | Verified (config) | `tests/api/test_auth_*`, `test_config.py`; fails closed `503 AUTH_NOT_CONFIGURED` |
| Local development identity (`dev-auth`) | Verified | `tests/test_dev_auth.py`; refused unless `APP_ENV=development` |
| Service taxonomy (categories/skills) + seed | Verified | `tests/db/test_service_taxonomy_repository.py`, `app/db/seed.py` |
| PostGIS worker discovery / nearby jobs | Verified | `tests/db/test_marketplace.py`; geography radius queries |
| Availability slots + overlap prevention | Verified | exclusion constraint `ex_bookings_worker_no_overlap` (0004) + `tests/db/test_booking_concurrency.py` |
| Direct hire booking lifecycle | Verified | `app/services/booking_service.py`; `tests/db/test_marketplace.py` |
| Job posting → application → selection → booking | Verified | `app/services/job_service.py`; `tests/db/test_marketplace.py` |
| Versioned price agreements (quote / revise / accept) | Verified | `app/services/trust_service.py`; `tests/db/test_trust_ledger.py` |
| Configurable fee policies (percentage/fixed/hybrid, bearer, waivers, org terms) | Verified | migration `0006`, `app/trust/pricing.py`, `app/services/fee_policy_service.py`; `tests/db/test_fee_policies.py`, `tests/test_pricing_engine.py` |
| Simulated settlement (one immutable row per completed booking) | Simulated | `is_simulated=True`, label `SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED`; `tests/db/test_marketplace.py` |
| Balanced double-entry financial ledger | Verified | `app/trust/integrity.py` (`verify_ledger`); `tests/db/test_trust_ledger.py` |
| Hash-chained financial event log (SHA-256, domain-separated, RFC 8785 JCS) | Verified | `app/trust/chain.py`, `crypto.py`; `tests/test_trust_crypto.py`, `tests/db/test_trust_ledger.py` |
| Merkle checkpoints + inclusion proofs (RFC 9162) | Verified | `app/trust/crypto.py`, `anchoring.py`; `tests/test_trust_crypto.py` |
| Portable, offline receipt + independent verifier | Verified | `scripts/verify_receipt.py` (does not import server code); frontend `lib/receiptVerify.ts`; `tests/verifier_path.py` |
| External RFC 3161 timestamping of checkpoints | Implemented; unconfigured by default | `app/trust/timestamping.py`, `anchoring.py`; `tests/test_trust_timestamping.py` uses a test double. Real DigiCert TSA runs **only** when `TSA_URL`+`TSA_CA_FILE` are set |
| Tamper detection (chain/checkpoint/ledger) | Verified | `app/trust/integrity.py`; adversarial tests in `tests/db/test_trust_ledger.py`, `scripts/audit/*` |
| Disputes + human reviewer resolution | Verified | `app/services/dispute_service.py`; `tests/db/test_marketplace.py` |
| Repeat booking with same worker | Verified | `booking_service.create_direct_booking` (`repeat_of_booking_id`) |
| Organization financial summary + CSV | Implemented | `app/api/v1/trust.py` (`/organizations/{id}/financial-summary`, `.csv`) |
| Synthetic demo dataset (seed/status/verify, dev-only) | Verified | `app/demo/`, `app/cli/seed_demo.py`; `tests/db/test_demo_seed.py` |
| Background anchor worker (checkpoint + submit) | Implemented | `app/main.py` lifespan; enabled by `ANCHOR_WORKER_ENABLED` |
| Real bank/UPI payments | Planned / not implemented | Boundary described in `docs/architecture/REVENUE_AND_RETENTION_MODEL.md §7` |
| Business subscription billing | Planned / not implemented | No billing code, plan, or pay button |

## Backend API surface (prefix `/api/v1`)

- **health**: `GET /health`, `GET /health/db`
- **users**: `GET /users/me`, `PATCH /users/me`
- **worker-profiles**: `POST /worker-profiles`, `GET /worker-profiles/{id}`, `PATCH /worker-profiles/me`; onboarding under `/worker-profiles/me/{skills,service-settings,availability}`
- **organizations**: `POST /organizations`, `GET /organizations`, plus reporting `GET /organizations/{id}/financial-summary`, `GET /organizations/{id}/financial-report.csv`
- **bookings**: `POST /bookings`, `GET /bookings/mine`, `GET /bookings/{id}`, `POST /bookings/{id}/{action}` (accept/decline/start/complete/cancel), `POST /bookings/{id}/disputes`; agreement/evidence `GET /bookings/{id}/financial-record`, `GET /bookings/{id}/receipt`, `POST /bookings/{id}/quote-revisions`, `POST /bookings/{id}/quotes/{version}/accept`, `GET /bookings/{id}/repeat-options`
- **jobs**: `POST /jobs`, `GET /jobs/mine`, `GET /jobs/nearby`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `POST /jobs/{id}/applications`, `GET /jobs/{id}/applications`, `POST /jobs/{id}/applications/{application_id}/select`
- **applications**: `GET /applications/mine`, `POST /applications/{id}/withdraw`
- **disputes**: `GET /disputes/mine`, `GET /disputes/reviewer-status`, `GET /disputes/review-queue`, `POST /disputes/{id}/resolve`
- **demo** (development only): `GET /marketplace/overview`, `GET /jobs/open`, `GET /demo/guide`, `GET /demo/showcase/{key}/receipt`
- **dev-auth** (development only): `POST /dev-auth/token`

Full OpenAPI at `http://localhost:8000/openapi.json` / Swagger at `/docs`.

## Frontend routes (`apps/web/src/App.tsx`)

`/` · `/login` · `/signup` · `/dashboard` · `/profile` · `/earn` · `/organizations` · `/hire` ·
`/find-work` · `/bookings` · `/my-jobs` · `/applications` · `/disputes/review` · `/pricing` ·
`/verify` · `/economics` · `/bookings/:bookingId/transparency` · `/demo` ·
`/demo/transparency/:key` · `/demo/tamper`. Protected routes use `AuthGuard`.

## Authentication modes

1. **Supabase (production path).** API verifies bearer tokens with `SUPABASE_JWT_SECRET` (HS256) or
   `SUPABASE_URL` + `SUPABASE_ANON_KEY` (server-side `/auth/v1/user`). With neither set, protected
   endpoints fail closed with `503 AUTH_NOT_CONFIGURED`.
2. **Local development identity (`dev-auth`).** For demos without Supabase. Refused unless
   `APP_ENV=development`; requires `DEV_AUTH_SECRET` ≥ 32 chars and `DEV_AUTH_PASSCODE` ≥ 8 chars; only
   `@demo.sahakar.test` emails. This is **not** production identity verification.

## Ledger / proof status

- **Locally consistent:** event hash chain, Merkle checkpoints, inclusion proofs, and double-entry
  ledger all recompute and reconcile. Tamper is detected by `app/trust/integrity.py`.
- **Independently verifiable:** downloaded receipts verify offline with `scripts/verify_receipt.py`,
  and a participant's earlier receipt copy detects a later rewrite (`--compare`).
- **External anchoring:** RFC 3161 timestamping is implemented but **unconfigured by default**
  (`LOCAL_ONLY`). When a TSA + pinned CA are configured, checkpoints progress to
  `EXTERNALLY_ANCHORED`. Statuses: `LOCAL_ONLY`, `ANCHOR_PENDING`, `ANCHOR_SUBMITTED`,
  `EXTERNALLY_ANCHORED`, `ANCHOR_FAILED`, `PROOF_INVALID`.

## Testing (see TESTING_AND_EVIDENCE.md for executed output)

- Backend: `335 passed` (isolated PostGIS test DB), plus a `182`-test no-database subset.
- Frontend: `typecheck` clean, `build` succeeds, `vitest` `68 passed`.

## Known limitations

- Payments are **simulated**; no money moves and no bank/UPI integration exists.
- The local ledger proves internal consistency; it does **not** by itself prove a real payment.
- External timestamping is off by default; receipts are then "local integrity only".
- `dev-auth` is development-only; live Supabase login is not exercised by the test suite.
- Worker profiles are self-declared; there is no identity or eligibility verification.
- No production operations (monitoring, backups, rate limiting, abuse controls) and no subscription
  billing or regulatory/tax readiness.

## Production-readiness disclaimer

This is a hackathon build intended for local demonstration and review. It is not hardened for
production use and must not handle real payments or real personal data as-is.
