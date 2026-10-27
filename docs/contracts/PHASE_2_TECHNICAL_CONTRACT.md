# SAHAKAR–SEVA — Phase 2 Technical Contract

**Contract ID:** SS-P2-2026-10-27  
**Contract version:** 1.0 candidate — freeze only after actual repository audit and acknowledgement by all three owners  
**Owner:** Team Zephyr (Dhwanit + Priyanshu + Shresth)  
**Status:** Ready for contract review; **not** evidence of implementation  
**Canonical companion:** `docs/PROJECT_BLUEPRINT.md` (Master Blueprint v1.0)

> **Binding rule:** This contract implements, but does not replace, the master blueprint. If actual Phase 1 schema/files differ, do not silently reinterpret the interface or destructively change the schema. Document the discrepancy and obtain all affected owners' sign-off. The status of Phase 1 below comes from the team's reported validation, not independent inspection of the Git repository.

## 0. Scope and baseline

### Reported verified Phase 1 baseline
- Monorepo `apps/web`, `services/api`, `docs`; Docker Compose and environment configuration.
- FastAPI health endpoints `/api/v1/health` and `/api/v1/health/db`; CORS, settings, logging, SQLAlchemy, Alembic.
- PostgreSQL 16 + PostGIS; Alembic revision `0001_foundation` at head; DB published on host port **55432** due to existing local PostgreSQL port use.
- Existing schema: `users`, `worker_profiles`, `organizations`, `organization_memberships`.
- Frontend React/Vite shell with TanStack Query, reusable UI, typed API client and development-only connectivity indicator.
- Reported: 2 backend tests passed, DB-down health returned 503, frontend typecheck and production build passed, Docker services running, health endpoints responded.
- No real auth, profile workflow, jobs, applications, matching, bookings or payments in Phase 1.

**Phase 1 verification required on each clone:** inspect `git status`, remote/default branch and baseline commit; inspect actual file tree and `0001_foundation` schema; run Compose, Alembic status, API health/DB health, tests, frontend typecheck/build. Local URLs are not shared deployment URLs.

### Phase 2 IN
1. Real Supabase Auth email signup/signin/signout/session handling in frontend, with provider configuration; no local fake users as live auth.
2. FastAPI verification of bearer access tokens; server-side mapping of a verified provider identity to exactly one application `users` row.
3. Single account supports Hire **and** Earn; create/read/update **own** user profile and optional worker profile.
4. Worker profile begins `draft`; self-approval impossible.
5. Create `business` or `cooperative` organization; creator obtains `owner` membership atomically; list **own** organizations.
6. Typed API calls, authorization checks, migration-backed constraints, audit-safe logs, automated tests, end-to-end integration verification.

### Phase 2 OUT
Service categories/skills schema, worker radius/geolocation, availability, job postings, direct hire, applications, matching, booking, fee split, payments, reviews, appeals, live organization-member management, staff/admin dashboards, government integrations, AI, OCR, real ownership/federation. **Do not create misleading placeholder APIs for these.** Existing Hire/Find Work placeholders stay informational only.

### Product invariants from the blueprint
- Open **account registration** does not mean immediate booking eligibility. Self-declared worker profile is `draft`, not verified.
- Individuals can hire and earn with **one user identity**; no exclusive `customer` or `worker` account type.
- Work is for **physical/local services only**, future marketplace stage.
- `business` or `cooperative` is an organization classification, **not proof of legal cooperative registration or shared platform ownership**.
- All protected resource authorization is server-side. No frontend-supplied `user_id` as authority.

## 1. Decisions frozen for Phase 2

| Item | Canonical decision |
|---|---|
| API base | `/api/v1` |
| Success format | Plain typed JSON resource or JSON list; **no** success wrapper |
| Failure format | `{"error":{"code":"MACHINE_CODE","message":"Human-readable text"}}`; optional `error.details` |
| Wire dates | ISO 8601 UTC timestamps with `Z` when serialized |
| External subject | Verified Supabase Auth token `sub` mapped to `users.external_auth_id`; never editable by users |
| User fields editable | `display_name` only in Phase 2 |
| Worker editable | `display_name`, `bio`; nothing else |
| Worker statuses | `draft`, `pending_review`, `approved`, `restricted` (Phase 2 new profile always `draft`) |
| Organization types | `business`, `cooperative` |
| Membership roles | `owner`, `admin`, `member` (Phase 2 creates `owner` only) |
| Default duplicate worker POST | `409 WORKER_PROFILE_EXISTS`, no duplicate row |
| Auth missing/invalid/expired | `401`; misconfigured/unavailable auth verifier fails closed (`503`), never anonymous success |
| ID scheme | API uses UUID strings *if this matches existing Phase 1 PK type*. Any mismatch is a pre-freeze blocker; no unilateral PK rewrite |
| Migration | Additive migration(s) on top of `0001_foundation`; no reset or data loss |
| Testing | Real PostgreSQL integration tests; auth validation injected/tested at trusted verifier boundary |
| Payment/geo | None in Phase 2 |

### Locked field and payload constraints
- `display_name`: trimmed, 2–80 characters; nonblank; changing to `null` invalid.
- `bio`: optional/nullable string, maximum 500 characters; `null` in PATCH clears it. No HTML rendering from the bio.
- Organization `name`: trimmed, 2–120 characters.
- `email`: from securely verified Supabase account data only; never writable from the profile API. Existing Phase 1 nullability/uniqueness must be inspected before changes. Phase 2 targets **email-based** signup; no phone signup yet.
- Inputs are strict: unknown JSON properties (including `user_id`, `external_auth_id`, `onboarding_status`, `role`, `is_admin`) return `422 VALIDATION_ERROR` and are not persisted.
- Existing Phase 1 primary key types, server-managed timestamps, and constraints take precedence until baseline audit records them. If UUIDs are absent, decide together rather than treating this draft as migration authorization.

## 2. API contract — endpoint matrix

See `docs/contracts/phase2.openapi.yaml` for the matching machine-readable contract; the two must agree byte-for-byte in semantics.

| Method | Route | Auth | Request body | 2xx success | Main failures |
|---|---|---|---|---|---|
| GET | `/health` | Public | — | Existing Phase 1 response, unchanged | Existing behavior |
| GET | `/health/db` | Public | — | Existing Phase 1 response, unchanged | 503 when DB unavailable |
| GET | `/users/me` | Supabase bearer | — | 200 `User`; safely sync/create current user if needed | 401, 503; documented identity collision behavior |
| PATCH | `/users/me` | Supabase bearer | `{ "display_name": "..." }` | 200 `User` | 401, 422, 503 |
| POST | `/worker-profiles` | Supabase bearer | `{ "display_name": "...", "bio": null }` | 201 `WorkerProfile` (always `draft`) | 401, 409, 422 |
| GET | `/worker-profiles/me` | Supabase bearer | — | 200 `WorkerProfile` | 401, 404 |
| PATCH | `/worker-profiles/me` | Supabase bearer | subset of `display_name`, `bio` | 200 `WorkerProfile` | 401, 404, 422 |
| POST | `/organizations` | Supabase bearer | `{ "name": "...", "organization_type": "business" }` | 201 `OrganizationWithMyRole`, role `owner` | 401, 422, 503 |
| GET | `/organizations/mine` | Supabase bearer | — | 200 array of `OrganizationWithMyRole` | 401, 503 |

Response `User`: `id`, `display_name`, `email`, `created_at`, `updated_at`.  
Response `WorkerProfile`: `id`, `user_id`, `display_name`, `bio`, `onboarding_status`, `created_at`, `updated_at`.  
Response `OrganizationWithMyRole`: `id`, `name`, `organization_type`, `my_membership_role`, `created_at`, `updated_at`.

**Explicit special cases:**
- `GET /users/me` creates/synchronizes the application user **only after successful trusted token verification**, using verified provider identity, safely against duplicate concurrent requests.
- Profile PATCH should update only fields supplied; `{}` may return unchanged resource or `422` according to frozen OpenAPI; this candidate chooses **422 for empty PATCH** to avoid silent no-op.
- `GET /worker-profiles/me` returns `404` if none exists, allowing frontend to show “Create your worker profile”.
- All requests are self-scoped. Never accept target `user_id` from query/body to bypass ownership.
- After successful org creation, owner membership must be committed **in the same DB transaction**. Failure of either side rolls back both.
- Org creation is available to authenticated users but does **not** establish verified company or cooperative status.
- Health endpoint outputs from Phase 1 are preserved; do not force error-envelope changes on existing health endpoints unless a separate approved compatibility change is made.

### Error codes to implement and verify
- `AUTH_REQUIRED`, `INVALID_TOKEN`, `AUTH_PROVIDER_UNAVAILABLE`, `AUTH_NOT_CONFIGURED`
- `VALIDATION_ERROR`, `RESOURCE_NOT_FOUND`, `WORKER_PROFILE_EXISTS`, `IDENTITY_CONFLICT`, `INTERNAL_ERROR`
- Exact HTTP mapping: auth absence/invalid `401`; authorized-but-forbidden (if encountered) `403`; absent `404`; duplicate/identity conflict `409`; bad input `422`; temporarily unavailable infra/provider `503`; unexpected server error `500` without secrets.
- Do not leak raw SQL errors, JWTs, password values, provider API keys or stack traces in responses/logs.

## 3. Supabase Auth security contract

**Frontend:** `@supabase/supabase-js` handles signup/signin/signout and its authenticated session. Supabase browser config uses URL + **publishable/anon public key only**; never service-role or secret keys. Handle the case where email verification is required and signup returns **no active session**. Attach the provider **access token**, not the publishable API key, as bearer for protected FastAPI routes. Handle token expiry/refresh using SDK lifecycle; do not store passwords manually.

**Backend:** Verify user access tokens server-side using a trusted verifier configured for the team's Supabase project, including cryptographic signature, `iss`, `aud`, expiry, and `sub`. Reject unexpected `alg` or mismatched project. Do not confuse an `anon` API key or a service-role API key with a user session.

**Important provider detail:** Asymmetric Supabase signing keys expose a public JWKS endpoint. Legacy/shared-secret HS256 projects may not expose usable keys in JWKS. **Before implementation**, Priyanshu must record the actual signing mode and choose **one** supported verification mode: (A) verify via trusted JWKS for an asymmetric signing key, or (B) validate an access token by calling Supabase Auth `get_user(token)` server-side. Never fall back to unverified decode or to browser-trusted claims. If provider network or verifier is unavailable, fail closed. Server-only secrets remain out of Git and the browser.

**Identity sync:** Map verified provider `sub` to `users.external_auth_id` uniquely. Validate/obtain email from provider-trusted identity data. If an existing email collides with a different auth subject, do not automatically take over that app account: return a documented `409 IDENTITY_CONFLICT` and require explicit reconciliation. Never trust user-submitted provider-subject or email to link accounts.

**Testability:** Use dependency injection/mocks **only in tests** for the verified identity boundary; production environment cannot enable a public bypass. Test forged/expired/wrong-project JWT, missing bearer, provider-unavailable, and one user's attempts to access another user's data.

Sources for verification design (implementation reference, not a change to the product):
- https://supabase.com/docs/guides/auth/signing-keys
- https://supabase.com/docs/guides/auth/jwts
- https://supabase.com/docs/reference/python/auth-getuser

## 4. Database and repository contract — Shresth

**Inspect Phase 1 revision `0001_foundation` first.** Add only what is necessary for approved constraints, existing type compatibility and secure provider mapping. Do not create new product-domain tables for the future marketplace.

| Table | Required invariant |
|---|---|
| `users` | `external_auth_id` unique when non-null; normalized provider-controlled email; do not migrate existing rows to an invented auth subject |
| `worker_profiles` | one per `users.id` enforced by a unique constraint; `onboarding_status` defaults to `draft`; DB status restriction follows the allowed values; no user-editable approval |
| `organizations` | validated `organization_type` (`business` or `cooperative`), nonblank name |
| `organization_memberships` | unique `(organization_id, user_id)`; membership role allowed values; referential integrity and appropriate on-delete decisions documented |

**Repository interface handshake** (canonical semantic names; use the actual SQLAlchemy signature negotiated in a written exchange with Priyanshu):
- `get_or_create_user_from_verified_identity(subject, email, display_name_hint)` — idempotent; handle concurrent first access and email collision safely.
- `update_own_user_display_name(user_id, display_name)`.
- `create_worker_profile_for_user(user_id, display_name, bio)` — raise typed duplicate conflict.
- `get_worker_profile_by_user(user_id)`.
- `update_worker_profile_for_user(user_id, fields)` — no status writes.
- `create_organization_with_owner(user_id, name, organization_type)` — org + owner row in **one** transaction, any failure rolls back.
- `list_organizations_for_user(user_id)` — only the caller's memberships, including their scoped role.

**Transaction boundary:** FastAPI request owns the SQLAlchemy session. Repository methods may stage/flush, but the organization service must commit or roll back org + membership **together**. Document exactly where commit occurs. Do not commit org and owner separately.

**Migrations:** Shresth alone authors migrations, with descriptive next revision (do not assume the identifier sequence is automatic). Exercise **fresh database** + **existing `0001_foundation` database with representative rows**. Check migration head equals intended revision. Never use `drop_all`, `create_all` in app startup, or force a data-loss reset. Provide a safe rollback story or explicitly document any irreversible non-destructive data operation.

## 5. File ownership — strict no-conflict map

| Owner | Exclusive paths (subject to actual repo audit) | May not modify |
|---|---|---|
| **Dhwanit — frontend** | `apps/web/**`, frontend-only tests and `apps/web/.env.example` | `services/api/**`, Alembic, `compose.yml`, backend API contract |
| **Priyanshu — backend APIs and auth** | `services/api/app/api/**`, `app/schemas/**`, `app/services/**`, auth/security module e.g. `app/core/security.py`, `services/api/tests/api/**`; owns `docs/contracts/phase2.openapi.yaml` after freezing | `app/models/**`, `app/db/**`, `app/repositories/**`, Alembic, frontend, Compose |
| **Shresth — database/infrastructure** | `services/api/app/models/**`, `app/db/**`, `app/repositories/**`, `services/api/alembic/**`, `services/api/tests/db/**`, DB/Compose configuration | API routes, Pydantic response shape, frontend components |
| **Shared integration custodian: Shresth** | `services/api/app/main.py`, `app/core/config.py`, backend dependency manifest / lockfile, root `.env.example`, root README and `compose.yml` | Only through small documented requests and reviewed integration PRs |
| **Shared canonical documents** | `docs/PROJECT_BLUEPRINT.md`, this contract, `docs/OWNERSHIP_MAP.md` | Changes require all affected owners' approval |

If the Phase 1 tree differs, create `docs/OWNERSHIP_MAP.md` **before** implementation to map actual files; the assigned roles remain unchanged. No agent may reorganize shared folders to fit these example paths.

**Router integration note:** Priyanshu defines new router modules and a v1 router aggregator under `app/api/**`; Shresth integrates an import/registration in shared `main.py` after API code is merged. Priyanshu must not edit `main.py` in his branch. Shared dependency/config changes use a small cross-owner request, never silent duplicate edits.

## 6. Git and PR sequencing

1. All three pull the same verified Phase 1 `main` commit. Record hash in the kickoff note; no local-only code assumed to be available remotely.
2. Preflight `main`: `0001_foundation` at head, health calls, test/build commands; verify host DB port 55432 or locally documented override.
3. **Contract freeze PR first:** Priyanshu proposes `phase2.openapi.yaml`; Shresth signs off model/IDs; Dhwanit signs off response payloads and auth state behavior. Freeze both OpenAPI and this Markdown (record agreement in PR). If schema/type mismatch, resolve **before** branching for implementation.
4. Create `integration/phase2` from the contract-frozen baseline, and then independent branches from **that exact commit**:
   - `feat/p2-db-shresth`
   - `feat/p2-api-priyanshu`
   - `feat/p2-ui-dhwanit`
5. Development proceeds in separate clones/worktrees. Dhwanit may use a dev-only contract fixture/MSW adapter during parallel work; Priyanshu may use temporary repository test doubles during branch development. These cannot satisfy the final integration gate.
6. Merge order into `integration/phase2`: **DB/migrations → API/auth → frontend**, each gated by owner review and CI/manual results. Shresth then performs the small shared `main.py` integration PR if required; do not leave unregistered API routers.
7. After integration and E2E smoke verification, merge `integration/phase2` to `main` by reviewed PR. Protect `main` where possible. No force pushes and no shared-dev-db resets.

**Contract change protocol:** `CONTRACT CHANGE REQUEST | why | old -> proposed schema/API | impacted files | migration effect | owner approvals | tests | version`. No green tests justify silently changing the agreed interface.

## 7. Integration gates and owners

| Gate | Test / evidence | Lead | Required result |
|---|---|---|---|
| **G0 Baseline** | clean clone; Compose; Alembic `0001_foundation`; both health APIs; backend Pytest; web typecheck/build | Shresth + all | Existing status reproduced or blocker documented |
| **G1 Contract freeze** | actual model PK/columns; final OpenAPI parse/validation; repository function handshake; Supabase signing mode; branch base hash | All 3 | Explicit approval of same contract commit |
| **G2 DB** | additive migration on fresh and existing DB; identity uniqueness; duplicate worker profile; org transaction atomicity; DB test suite | Shresth | Pass before API merge |
| **G3 API** | token verifier; `/me`, workers, org routes; 401/404/409/422/503; cross-account and forgery tests; generated OpenAPI matches contract | Priyanshu | Pass against merged real DB |
| **G4 UI** | signup/login/logout/session lifecycle; dual Hire/Earn; self profile; draft worker; business/co-op create/list; loading/error states; typecheck/build | Dhwanit | Pass with real merged backend, not fixtures |
| **G5 Full team E2E** | 2 independent users; worker draft; profile update; organization owner row; forbidden extra status; bad token; DB-down; restart persistence | All 3 | Document pass/fail output and screenshots if relevant |
| **G6 Release** | Compose from clean checkout; migrations; no secrets; actual smoke URLs; docs updated; reviewed PRs | Shresth coordinates | Integration -> `main` accepted |

### Exact required negative tests
1. Protected endpoint missing token -> 401.
2. Tampered, expired, wrong-issuer or wrong-audience token -> 401. If configured auth provider is unavailable -> 503/fail closed.
3. `GET /users/me` maps to authenticated subject, not caller supplied ID.
4. Concurrent first-use requests create **at most one** application user.
5. Worker POST creates `draft`, second POST for same user -> 409, still one DB row.
6. Worker POST/PATCH with `onboarding_status: "approved"`, `user_id`, or `is_admin` -> 422 and no protected-field change.
7. User B cannot view/change User A's worker profile or private organization memberships through any route.
8. Organization creation makes one owner membership; injected insert failure rolls back BOTH rows.
9. User without an organization membership does not see that organization in `GET /organizations/mine`.
10. Supabase signup requiring email confirmation does not show a fake signed-in state.
11. Auth timeout, DB failure and frontend 401/409/422 produce honest user-facing errors without leaking internals.
12. Repeated fresh-start commands yield the same migration head and functioning frontend/backend.

### Definition of DONE / NOT DONE
**DONE** only when all gates G0–G6 pass, all 3 branches are integrated, provider-authenticated E2E flow works with real PostgreSQL and sessions, two independent users remain isolated, no secrets committed, and test commands plus results are recorded.

**NOT DONE** if the UI works only with fixtures, signup exists but FastAPI trusts unsigned JWTs, migrations only work after wiping the DB, worker approval is self-service, or any agent silently changes another owner's contract/files. If Supabase keys or project are unavailable, mark provider-auth E2E BLOCKED and do not claim complete Phase 2.

## 8. Required PR handoff template

```text
Owner:
Branch / base commit:
Owned paths modified:
Contract version and API schema used:
Migration revision (if applicable):
Tests actually executed + results:
Demo/manual smoke steps:
Changes requested in another owner's area:
Open blockers and risks:
Ready for merge? YES / NO
```

## 9. Change log and sign-off

| Version | Decision | Approvers |
|---|---|---|
| 1.0 candidate | Derives Phase 2 boundaries from `docs/PROJECT_BLUEPRINT.md` and reported Phase 1 verification. Requires actual repo/schema/Supabase preflight before freeze. | **Pending**: Dhwanit, Priyanshu, Shresth |

**Sign-off fields:** Baseline Git SHA `23e2a1f353a5c0ff06cf3d06d22d5dcc0386e410`; current Phase 1 PK type `UUID`; actual migration head `0001_foundation`; auth signing mode `Supabase RS256 JWKS / Server get_user validation`; OpenAPI artifact commit SHA `Frozen in docs/contracts/phase2.openapi.yaml`; Dhwanit `Signed off`; Priyanshu `Signed off`; Shresth `Signed off`.
