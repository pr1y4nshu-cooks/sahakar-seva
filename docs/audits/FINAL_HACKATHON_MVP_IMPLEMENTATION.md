# SAHAKAR–SEVA — Final Hackathon MVP Implementation Report

**Date:** 2026-10-27 · **Branch:** `shresthBranch` · **Base:** `90c52df` → checkpoint `6468635` (Phase 3A) → MVP commit (see §12)
**Verdict:** **Working local hackathon MVP.** Both hiring methods run end to end through the real UI, API and PostGIS. Authentication was verified with the **local development identity provider only**; live Supabase E2E was **not** verified. This is not production-ready.

## 1. Implemented features (all genuinely functional, persisted, tested)

| Slice | Feature | Evidence |
|---|---|---|
| A | Public categories/skills/localities; worker declares/removes self-declared skills (cap 20, duplicates 409, invalid 422) | DB tests, API E2E, browser E2E |
| B | Service area (locality, centre rounded to ~1.1 km, radius 2/5/10/15/25 km, hourly rate) as `geography(Point,4326)` + GIST; dated availability slots with DB-level overlap exclusion; slots holding bookings cannot be removed | DB tests, migration test, E2E |
| C | `/hire` live discovery: skill/category + worker radius covers job point + customer search radius + eligibility + optional time window; ordered by distance with plain-language match reasons; honest verification labels; no coordinates exposed; hardcoded fake counts removed | DB tests, E2E (4.3 km found; Whitefield excluded) |
| D | Job posting (individual or org owner/admin), nearby job board within the worker's radius, apply/withdraw, duplicate rejection, skill + radius eligibility, applicant selection, cancellation, private address hidden from listings | DB tests, E2E |
| E | One booking model for both methods; finite state machine; worker accept/decline/start, customer complete/cancel; concurrency-safe confirmation (row lock + exclusion constraint); address revealed to the worker only after acceptance; 404 for unrelated users | DB + true multi-thread concurrency tests, E2E |
| F | Integer-paise pricing, fee snapshot on the booking, 10% pilot fee with configurable cap (startup-validated) and a 20% DB ceiling; one immutable (trigger) settlement per completed booking; reconciliation checks; "SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED" | DB tests, E2E (₹700 = ₹70 + ₹630) |
| G | Disputes by booking parties; reviewer rights only via server CLI; a party cannot review their own dispute; outcome + mandatory reason; audit events; no automated sanctions | DB tests, API E2E |
| Org | Owner/admin may post and manage jobs for an organization; members and outsiders cannot | DB tests, E2E |

Decisions and the state machine are in `docs/contracts/MVP_MARKETPLACE_CONTRACT.md`. Phase 2 frozen routes and schemas are unchanged.

## 2. API routes (`/api/v1`, 36 paths / 42 operations in the live OpenAPI)

**Phase 2 (unchanged):** `GET /health`, `GET /health/db`, `GET|PATCH /users/me`, `POST /worker-profiles`, `GET|PATCH /worker-profiles/me`, `POST /organizations`, `GET /organizations/mine`.

**New:**
- Public: `GET /service-categories`, `GET /skills`, `GET /localities`, `GET /workers/search`.
- Worker setup: `GET|POST /worker-profiles/me/skills`, `DELETE /worker-profiles/me/skills/{skill_id}`, `GET|PUT /worker-profiles/me/service-settings`, `GET|POST /worker-profiles/me/availability`, `DELETE /worker-profiles/me/availability/{slot_id}`.
- Bookings: `POST /bookings`, `GET /bookings/mine`, `GET /bookings/{id}`, `POST /bookings/{id}/{accept|decline|cancel|start|complete}`, `POST /bookings/{id}/disputes`.
- Jobs: `POST /jobs`, `GET /jobs/mine`, `GET /jobs/nearby`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET|POST /jobs/{id}/applications`, `POST /jobs/{id}/applications/{application_id}/select`.
- Applications: `GET /applications/mine`, `POST /applications/{id}/withdraw`.
- Earnings: `GET /earnings/mine`.
- Disputes: `GET /disputes/mine`, `GET /disputes/reviewer-status`, `GET /disputes/review-queue`, `POST /disputes/{id}/resolve`.
- Dev only: `POST /dev-auth/token` (returns 404 unless enabled).

## 3. Database

Migration **`0004_marketplace_core`** (additive; down revision `0003`; no historical migration edited). Tables:

- `worker_service_settings`
- `availability_slots`
- `jobs`
- `job_applications`
- `bookings`
- `settlements`
- `disputes`
- `platform_reviewers`
- `audit_events`

PostGIS usage:

- `service_point` and `job_point` are `geography(Point,4326)` with GIST indexes.
- Distance checks use `ST_DWithin` / `ST_Distance` in metres; radii are stored in km × 1000.

Safety constraints:

- Exclusion constraints (`btree_gist`): `ex_bookings_worker_no_overlap` (confirmed/in-progress) and `ex_availability_slots_no_overlap`.
- `uq_bookings_active_job` (partial unique index) and `uq_job_applications_job_worker`.
- `uq_settlements_booking_id`.
- Money CHECKs: fee ceiling and `fee + payout = price`; settlements are `is_simulated` only.
- Dispute completeness and no self-review.
- `trg_settlements_immutable`.

The dev DB is at head. Pre-existing rows were preserved (389 users, 92 worker profiles, 88 orgs, 88 memberships before migration). The same counts held after migration and after every test run.

## 4. Frontend routes

| Route | State |
|---|---|
| `/`, `/login`, `/signup`, `/profile`, `/organizations`, `/dashboard` | Existing; dashboard "Soon" cards now link to live features |
| `/earn` | Profile + skills + service area + availability + simulated earnings |
| `/hire` | Live search/booking and **Post a job** tab (placeholder replaced) |
| `/find-work` | Live nearby-job board with apply (placeholder replaced) |
| `/bookings`, `/my-jobs`, `/applications` | New, auth-guarded |
| `/disputes/review` | New, reviewer-only (403 state otherwise) |

The mobile navigation button now works; previously it was inert. No marketplace placeholders remain. `Placeholder.tsx` is now unused.

## 5. Authentication status

- **Production path (Supabase):** unchanged and still supported. **Not verified E2E.** At audit time the root `.env` had `SUPABASE_URL` set, but `SUPABASE_ANON_KEY`/`SUPABASE_JWT_SECRET` were empty, and `apps/web/.env.local` had an empty `VITE_SUPABASE_ANON_KEY`. No credentials were invented.
- **Local development identity (used for every demo):** server-signed HS256 tokens, separate secret, `@demo.sahakar.test` only, passcode required. It is refused unless `APP_ENV=development`, off by default, and its tokens are rejected when it is disabled. Identities are `dev|<email>`, so they cannot take over Supabase accounts. Every protected request is verified server-side through the normal dependency. No client-supplied user IDs are trusted anywhere.

## 6. Tests executed

| Command | Result |
|---|---|
| `TEST_DATABASE_URL=…/sahakar_seva_test pytest tests/` (host, `services/api`) | **152 passed** (baseline 119; 33 new) |
| Same inside the API container | 150 passed, 2 skipped (contract YAML not mounted, pre-existing) |
| Dev-DB counts before/after the full suite | Identical (users=397, wp=94, orgs=89, jobs=3, bookings=4, settlements=2, disputes=1) |
| `npm run typecheck` | 0 errors |
| `npm run test -- --run` | **26 passed** (24 existing + 2 new) |
| `npm run build` | OK (573 kB chunk warning, pre-existing in kind) |
| `alembic current` | `0004_marketplace_core (head)` |
| `docker compose restart` + `dev_up.sh` | All 3 containers running, `RestartCount=0`; `/health` and `/health/db` 200; Swagger 200 |

New test coverage:

- skill listing/selection and unauthorised modification
- radius filtering and availability filtering
- direct booking, job posting, application, and applicant selection
- duplicate application
- double-booking (API, DB constraint, and two real concurrent threads/connections)
- invalid transitions
- fee cap and rounding, reconciliation, and settlement immutability
- dispute authorisation
- user isolation and organization permissions
- migration upgrade/downgrade preserving rows
- dev-auth safety

## 7. End-to-end scenarios demonstrated (live stack, real DB)

- `scripts/e2e_demo.py`: **35/35 checks**. It covers Scenarios 1–5 and the dispute with a human decision, and was re-run after a full container restart.
- `scripts/browser_e2e.cjs` (headless Chrome through the React UI, desktop + mobile viewport): **13/13 checks**. It covers worker onboarding with refresh persistence, discovery, booking request, acceptance, completion with the ₹700/₹70/₹630 simulated breakdown, worker earnings, and the unauthorised redirect.
- The job-posting and dispute flows were verified via the API script, not via browser automation. Their UI pages were built and type-checked, but not clicked through by a script.

## 8. Defects found and fixed during the sprint

1. `alembic/env.py` crashed the API container when `DATABASE_URL` contained `%`. It now escapes `%`.
2. `lib/supabase.ts` rendered a blank app when `VITE_SUPABASE_URL` was an empty string (`??` → `||`).
3. `api-adapter.ts` forced fixtures mode for any `http://localhost:8000` API, so the local backend could never be used. Fixed.
4. The mobile menu button did nothing. Fixed.
5. Misleading UI was removed: fake worker/job counts, a "Verified Workers" claim, and "Draft = not visible" copy.

## 9. Deferred (not implemented)

Ratings/reviews, chat, notifications, recurring/business contracts, cooperative governance/voting, real payments/escrow/wallets, AI matching, recurring availability, reviewer assignment workflow (the queue is shared), admin approval of worker profiles (`approved` exists, but no reviewer UI sets it), org-member visibility of org bookings (bookings are visible to the poster and the worker only).

## 10. Known limitations

- Worker eligibility is "not restricted + skill + service area". Draft workers are discoverable but clearly labelled unverified.
- Starting work has no time-window check. That keeps the demo practical but is not production behaviour.
- Booking price for a direct hire is for the whole slot; partial-slot booking is not supported.
- Demo runs leave tagged `@demo.sahakar.test` rows in the dev DB. This is intended demo data and never touches other rows.
- `apps/web/scripts/check-contract-drift.ts` fails with `ERR_MODULE_NOT_FOUND` (missing `tsx`). This is pre-existing and was not changed.
- The Supabase sign-in path in `auth.tsx` calls `refreshUser()` with a possibly stale session. It is untested without credentials.

## 11. Remaining blockers

- **Environment (not code):**
  - Supabase anon key / JWT secret are missing, so the provider-backed E2E is blocked.
  - The root `.env` `POSTGRES_*`/`DATABASE_URL` now target a remote Supabase Postgres. Use `scripts/dev_up.sh` for local runs.
  - A host Vite server on `[::1]:5173` shadows the Docker web app for `localhost`. Use `127.0.0.1`.
- **True defects:** none known open.

## 12. Git changes

- Checkpoint `6468635` on `shresthBranch`: Phase 3A database work plus the earlier audit reports.
- The MVP work is committed on `shresthBranch` as a second commit; `git log` shows the hash.
- Nothing was pushed. Not merged to `main`.
- Never committed: `.env` and `apps/web/.env.local`. Both are git-ignored, and both were edited locally: dev-auth values appended to `.env`; `.env.local` was not touched by this sprint.

## 13. Setup and demo

See `docs/audits/LIVE_DEMO_RUNBOOK.md`.
