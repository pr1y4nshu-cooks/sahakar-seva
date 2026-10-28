# SAHAKAR–SEVA — Current Project Implementation Status

**Audit date:** 2026-10-27
**Auditor role:** Principal Full-Stack Architect / Integration Engineer
**Branch audited:** `shresthBranch` @ `90c52df`
**Scope:** Phases 1–3A as actually implemented in the working tree (including Shresth's uncommitted Phase 3A work), verified against `docs/contracts/phase2.openapi.yaml`, `docs/contracts/PHASE_3A_DATA_CONTRACT.md`, and the master blueprint.

This report supersedes nothing. All prior `docs/audits/PHASE_2_*` reports remain historical evidence of their point in time and were not modified.

---

## 1. Phase-by-phase status

| Phase | Scope | Status |
|---|---|---|
| **Phase 1** | Health endpoints, PostGIS-enabled DB, foundational models/migration, typed frontend client, structural pages | **Complete** |
| **Phase 2** | Unified identity, worker profiles, organizations, Supabase bearer auth, frozen API contract (9 endpoints) | **Complete and verified** (119/119 backend tests, 24/24 frontend tests, live curl checks) |
| **Phase 3A** | Service taxonomy data layer (`service_categories`, `skills`, `worker_skills`), DB test isolation | **Database layer complete and tested; uncommitted on disk.** API layer explicitly NOT frozen/NOT implemented (correctly, per `PHASE_3A_DATA_CONTRACT.md` §7) |
| **Phase 3B+** | Worker discovery, bookings, direct hire, job postings, payments, location/PostGIS geometry, reviews, disputes | **Not implemented.** Frontend has non-functional UI placeholders only (`/hire`, `/find-work`) |
| **Phase 4+** | Cooperative governance, worker protections (explainable matching, human review), notifications | **Not implemented** |

---

## 2. Implemented features

| Feature | Frontend | Backend API | Database | Auth | Status |
|---|---|---|---|---|---|
| Health check | N/A | `GET /api/v1/health` | — | Public | Fully implemented & tested |
| DB health check | N/A | `GET /api/v1/health/db` | Live connection check | Public | Fully implemented & tested (pre-existing contract discrepancy on 503 body, see §5) |
| User identity sync | `useCurrentUser()` hook, `Dashboard.tsx`, `Profile.tsx` | `GET /api/v1/users/me` | `users` table | Bearer required | Fully implemented & tested |
| Update display name | `Profile.tsx` | `PATCH /api/v1/users/me` | `users` table | Bearer required | Fully implemented & tested |
| Worker profile creation | `Earn.tsx` | `POST /api/v1/worker-profiles` | `worker_profiles` table | Bearer required | Fully implemented & tested |
| Worker profile read/update | `Earn.tsx`, `Dashboard.tsx` | `GET/PATCH /api/v1/worker-profiles/me` | `worker_profiles` table | Bearer required | Fully implemented & tested |
| Organization creation | `Organizations.tsx` | `POST /api/v1/organizations` | `organizations` + `organization_memberships` (atomic) | Bearer required | Fully implemented & tested |
| Organization listing | `Organizations.tsx`, `Dashboard.tsx` | `GET /api/v1/organizations/mine` | Scoped join query | Bearer required | Fully implemented & tested |
| Login / signup | `Login.tsx`, `Signup.tsx` | Supabase Auth (external) | `users.external_auth_id` | Supabase session | Implemented; **live provider flow BLOCKED locally** (no credentials in `.env`) |
| Session/auth guarding | `AuthGuard.tsx`, `PublicOnlyGuard` | N/A | N/A | N/A | Fully implemented (loading states, expiry re-check, return-path redirect) |
| Service taxonomy (categories/skills) | Not built | Not built (correctly, per contract) | `service_categories`, `skills`, `worker_skills` tables + repository | N/A yet | **Database layer only** — implemented and tested; no routes exist |
| Database test isolation | N/A | N/A | `app/db/testing.py`, isolated `sahakar_seva_test` DB | N/A | Fully implemented & verified live (see §4) |
| Worker/job marketplace UI | `Hire.tsx`, `FindWork.tsx` | None | None | Public, unauthenticated | **Placeholder only** — no live data, no backend wiring, no interactive handlers |

---

## 3. Missing / placeholder functionality

| Item | Classification | Notes |
|---|---|---|
| `/hire`, `/find-work` pages | **Placeholder only** | Static UI shell: search inputs have no `onChange`, buttons have no `onClick`, result cards are commented-out source code, `EmptyState` always renders. Correctly left public since no private data is shown. "12 workers found" / "24 jobs posted this week" are hardcoded fake copy — see Full-Stack Integration Audit for the specific recommendation. |
| Worker discovery (search, filter, radius) | **Not implemented** | No backend endpoint, no PostGIS geometry columns yet. Phase 3B scope. |
| Direct hiring / bookings | **Not implemented** | No `bookings` table or state machine. Phase 3B/4 scope per blueprint. |
| Job postings / applications | **Not implemented** | No `jobs` or `job_applications` tables. Phase 3B scope. |
| Skills API (list categories/skills, declare/remove worker skill) | **Not implemented (correctly deferred)** | `PHASE_3A_DATA_CONTRACT.md` §7 explicitly marks this "NOT YET FROZEN." Database and repository layer are ready for it. |
| Payments, reviews, disputes, notifications | **Not implemented** | Phase 4+ scope. |
| Live Supabase authentication (browser → Supabase → FastAPI) | **Blocked, not a defect** | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` are all empty in the local `.env`. The backend correctly fails closed (`503 AUTH_NOT_CONFIGURED`) rather than silently allowing requests. |

---

## 4. API route inventory

All 9 frozen Phase 2 routes are implemented, mounted under `/api/v1`, and verified live:

| Method | Path | Auth | Verified |
|---|---|---|---|
| GET | `/api/v1/health` | Public | ✅ live curl 200 |
| GET | `/api/v1/health/db` | Public | ✅ live curl 200 |
| GET | `/api/v1/users/me` | Bearer | ✅ live curl 401 without token; tests pass |
| PATCH | `/api/v1/users/me` | Bearer | ✅ tests pass |
| POST | `/api/v1/worker-profiles` | Bearer | ✅ tests pass |
| GET | `/api/v1/worker-profiles/me` | Bearer | ✅ tests pass |
| PATCH | `/api/v1/worker-profiles/me` | Bearer | ✅ tests pass |
| POST | `/api/v1/organizations` | Bearer | ✅ tests pass |
| GET | `/api/v1/organizations/mine` | Bearer | ✅ tests pass |

No Phase 3A routes exist (correct — none are frozen).

---

## 5. Frontend route inventory

| Route | Guard | Backend dependency | Status |
|---|---|---|---|
| `/` | None (public) | None | Renders, static |
| `/login` | `PublicOnlyGuard` | Supabase Auth | Renders; live auth blocked locally |
| `/signup` | `PublicOnlyGuard` | Supabase Auth | Renders; live auth blocked locally; email-confirmation flow implemented |
| `/dashboard` | `AuthGuard` | `/users/me`, `/worker-profiles/me`, `/organizations/mine` | Renders behind auth; fixtures mode locally |
| `/profile` | `AuthGuard` | `PATCH /users/me` | Renders behind auth; fixtures mode locally |
| `/earn` | `AuthGuard` | `/worker-profiles` (POST/GET/PATCH) | Renders behind auth; fixtures mode locally |
| `/organizations` | `AuthGuard` | `/organizations` (POST/GET) | Renders behind auth; fixtures mode locally |
| `/hire` | None (public) | None (placeholder) | Renders; no real data or handlers |
| `/find-work` | None (public) | None (placeholder) | Renders; no real data or handlers |

Local frontend currently runs in **fixtures mode** (no `apps/web/.env.local`), so none of the authenticated pages call the real backend in the browser until that file is created with real `VITE_*` values.

---

## 6. Database migration state

| Revision | Purpose | Applied to dev DB |
|---|---|---|
| `0001_foundation` | Base tables, PostGIS extension | ✅ |
| `0002_phase2_constraints` | CHECK constraints for status/type/role enums | ✅ |
| `0003_skills_and_categories` | `service_categories`, `skills`, `worker_skills` (additive only) | ✅ (applied during this audit — see Full-Stack Integration Audit, Finding INT-02) |

Current Alembic head matches migration code head: `0003_skills_and_categories`. Seed data applied: 3 categories, 6 skills (matches `PHASE_3A_DATA_CONTRACT.md` §6 exactly). Existing Phase 2 data (389 users, 92 worker profiles, 88 organizations, 88 memberships) preserved throughout.

---

## 7. Integration readiness

| Layer | Readiness |
|---|---|
| Backend startup | Ready — container stable, `RestartCount=0` |
| Frontend startup | Ready — container stable, dev server responds 200 |
| Database | Ready — healthy, migrated to head, PostGIS active |
| Backend ↔ Database | Ready — repository layer fully delegated, tested against isolated DB |
| Frontend ↔ Backend | Ready in principle (contract-compliant client); **not exercised live** because local frontend runs in fixtures mode and Supabase credentials are absent |
| Test infrastructure | Ready and safe — isolated test DB verified non-destructive to dev data |

**Overall:** The implemented surface area (Phase 1 + Phase 2 + Phase 3A data layer) is internally consistent, contract-compliant, and locally operational. Nothing beyond the approved phases has been built into working functionality — the two marketplace-looking pages are inert placeholders, not functional scope creep.
