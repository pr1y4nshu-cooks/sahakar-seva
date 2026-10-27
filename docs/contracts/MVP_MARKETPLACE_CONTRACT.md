# SAHAKAR–SEVA — Hackathon MVP Marketplace Contract

**Status:** Approved for the hackathon MVP (2026-10-27). Additive to the frozen Phase 2 contract: no Phase 2 route, schema, or table changes.
**Migration:** `0004_marketplace_core` (down revision `0003_skills_and_categories`).
**Error envelope:** unchanged — `{"error": {"code", "message", "details"}}`.

## 1. Phase 3A open questions — resolved

| Question (data contract §7) | Decision |
|---|---|
| Public taxonomy lists unauthenticated? | Yes. Categories and skills are non-personal. |
| Cap on declared skills? | 20 per worker (`WORKER_SKILL_LIMIT`, 422). |
| Inactive declared skills | Returned with `skill.is_active=false`; UI labels them "no longer offered". |
| New error codes | `WORKER_SKILL_EXISTS` (409), `SKILL_NOT_AVAILABLE` (422), plus the codes in §6. |
| Bulk replace vs add/remove | Individual add (`POST`) and remove (`DELETE`). |
| Invalid `skill_id` in a POST body | 422 `SKILL_NOT_AVAILABLE` (the body is invalid, not the URL). |

## 2. Eligibility and verification

- Skills are **self-declared**. Every API response carrying a skill declaration has `is_self_declared: true`. Nothing in the MVP verifies a skill.
- A worker is **discoverable** when `onboarding_status != 'restricted'`, they have at least one declared active skill, and they have service settings (location + radius + rate).
- `verification_label` is `"Platform approved"` only when `onboarding_status = 'approved'`. Otherwise it is `"Not verified — self-declared profile"`. No API sets `approved`. It is not self-service.

## 3. Location and privacy

- Workers pick a locality from the curated list (`GET /localities`) or use browser geolocation. The server **rounds worker service centres to 2 decimal places (~1.1 km)** before storing them.
- Points are stored as `geography(Point,4326)` with GIST indexes. Distances use `ST_DWithin`/`ST_Distance` on geography, so the units are metres. Radius is stored in km and multiplied by 1000.
- Allowed radii: 2, 5, 10, 15, 25 km.
- Customers see the worker's **locality name and rounded distance**, never coordinates. Workers' coordinates are returned only to the worker.
- A job's or booking's `address_details` is returned only to the customer, and to the worker once the booking is `confirmed` or later. Public job listings show locality and distance only. Job coordinates are rounded to 3 decimal places.

## 4. Availability

Explicitly dated slots: `starts_at < ends_at`, 30 min to 12 h, in the future. Active slots for one worker cannot overlap (PostgreSQL exclusion constraint). A slot referenced by a `requested`, `confirmed`, or `in_progress` booking cannot be removed (409 `SLOT_IN_USE`). A slot with a booking history is deactivated rather than deleted (FK `RESTRICT`).

## 5. Pricing and settlement (simulated)

- Money is integer **paise**.
- Direct hire: price = `hourly_rate_paise × minutes ÷ 60`, computed by the server from the worker's rate and the slot. Job hire: price = the job's `budget_paise`. Clients never send a price for a booking, and there is no endpoint that changes an agreed price.
- Fee policy (pilot assumption, configurable): `PLATFORM_FEE_BPS` (default 1000 = 10%) must be ≤ `PLATFORM_FEE_CAP_BPS` (default 1500). The app refuses to start otherwise. The database CHECK enforces an absolute ceiling of 2000 bps.
- `fee_paise = round_half_up(price × bps / 10000)` and `payout_paise = price − fee_paise`. The breakdown is snapshotted on the booking when it is created.
- On completion, exactly one `settlements` row is written (UNIQUE `booking_id`). It has CHECK `fee + payout = gross` and `is_simulated = true`, and a trigger makes it immutable (no UPDATE/DELETE).
- Every settlement payload carries `label: "SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED"`.

## 6. Booking state machine

| From | Action | To | Actor |
|---|---|---|---|
| requested | accept | confirmed | worker |
| requested | decline | declined | worker |
| requested | cancel | cancelled | customer |
| confirmed | start | in_progress | worker |
| confirmed | cancel | cancelled | customer or worker |
| in_progress | complete | completed (+ settlement) | customer |
| confirmed / in_progress / completed | dispute | disputed | customer or worker |

Any other transition is rejected with 409 `INVALID_TRANSITION`. Acting on someone else's booking returns 404, so that it does not leak.

Concurrency: an exclusion constraint `EXCLUDE USING gist (worker_profile_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE status IN ('confirmed','in_progress')` guarantees that a worker never holds two overlapping active bookings. `accept` also row-locks the worker profile (`SELECT … FOR UPDATE`). A violation returns 409 `BOOKING_CONFLICT`. A job has at most one active booking (partial unique index).

## 7. Jobs and applications

- Job status: `open → filled | cancelled`. Applications: `applied → selected | rejected | withdrawn`.
- A worker may apply only if they have a worker profile, they declared the job's skill, the job lies within their radius, it is not their own job, and the job is open. UNIQUE `(job_id, worker_profile_id)` gives 409 `DUPLICATE_APPLICATION`.
- **Select** (job manager only) creates a `requested` booking (`origin='job'`) and marks the job `filled`. When the worker **accepts**, the other applications become `rejected`. If the worker **declines**, the job reopens and the application becomes `withdrawn`.
- Job manager = the poster, or an `owner`/`admin` of the job's organization. Posting on behalf of an organization requires `owner`/`admin` membership (403 `FORBIDDEN`).

## 8. Disputes

- Either booking party may open **one** dispute per booking (`confirmed`, `in_progress`, or `completed`). The booking moves to `disputed`.
- Only users in `platform_reviewers` may list or resolve disputes. That table is granted **only** by a server-side CLI (`python -m app.cli.grant_reviewer`), never by an API. A reviewer cannot resolve a dispute on a booking where they are the customer or the worker (403).
- Resolution records `outcome` (`resolved_for_customer` | `resolved_for_worker` | `no_fault`), a mandatory `reason`, the reviewer, and the time. No automated restriction of workers ever happens.
- Booking transitions, settlements, and dispute events are written to `audit_events`.

## 9. Local development identity (not production auth)

Supabase remains the production identity provider. For local demos without Supabase credentials, `DEV_AUTH_ENABLED=true` turns on `POST /api/v1/dev-auth/token`. Its constraints:

- It requires `APP_ENV=development`. The app refuses to start otherwise.
- It requires `DEV_AUTH_SECRET` (≥ 32 chars) and `DEV_AUTH_PASSCODE` (≥ 8 chars).
- It accepts only emails in `DEV_AUTH_EMAIL_DOMAIN` (default `demo.sahakar.test`).
- It issues HS256 tokens with `iss=sahakar-dev-auth`, signed with the dev secret. These are verified server-side exactly like real tokens.
- Dev tokens are rejected whenever dev auth is disabled. Dev identities use `sub = "dev|<email>"`, so they can never collide with or take over a Supabase identity.
- It is disabled by default.

## 10. Routes (all under `/api/v1`)

Public: `GET /service-categories`, `GET /skills`, `GET /localities`, `GET /workers/search`.
Worker: `GET|POST /worker-profiles/me/skills`, `DELETE /worker-profiles/me/skills/{skill_id}`, `GET|PUT /worker-profiles/me/service-settings`, `GET|POST /worker-profiles/me/availability`, `DELETE /worker-profiles/me/availability/{slot_id}`, `GET /jobs/nearby`, `POST /jobs/{id}/applications`, `GET /applications/mine`, `POST /applications/{id}/withdraw`, `GET /earnings/mine`.
Customer/organization: `POST /jobs`, `GET /jobs/mine`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/applications`, `POST /jobs/{id}/applications/{application_id}/select`.
Bookings: `POST /bookings`, `GET /bookings/mine`, `GET /bookings/{id}`, `POST /bookings/{id}/{accept|decline|cancel|start|complete}`, `POST /bookings/{id}/disputes`.
Disputes: `GET /disputes/mine`, `GET /disputes/reviewer-status`, `GET /disputes/review-queue`, `POST /disputes/{id}/resolve`.
Dev only: `POST /dev-auth/token`.
