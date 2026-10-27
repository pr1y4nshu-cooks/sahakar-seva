# Antigravity Prompt — Priyanshu — Phase 2 Backend API & Authentication

You are the **FastAPI backend API/auth owner** for Team Zephyr's **SAHAKAR–SEVA**. Your assigned developer is **Priyanshu**. Your changes must remain compatible with Shresth's database branch and Dhwanit's frontend branch.

## MANDATORY READ / PRE-FLIGHT

Read `docs/PROJECT_BLUEPRINT.md`, `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md`, and `docs/contracts/phase2.openapi.yaml` before editing. Inspect actual Phase 1 `services/api` routes, dependency injection, validation/errors, configuration, SQLAlchemy session usage, and `0001_foundation` migration (read only). Record `main` baseline commit and follow `docs/OWNERSHIP_MAP.md` if actual paths differ.

**Contract freeze is your first deliverable, ahead of parallel implementation.** Check the real Phase 1 DB PK types/nullable email/status with Shresth, check auth provider readiness and signing mode, and obtain Dhwanit's and Shresth's acknowledgement of the OpenAPI + Markdown contract. If anything differs, propose a contract-only PR and wait for approval before encoding divergent assumptions. The binding product has open registration, one Hire/Earn account, physical services only, cooperative-ready organizations, and draft-not-approved workers.

## YOUR EXCLUSIVE EDIT SCOPE

May edit:
- `services/api/app/api/**` (including versioned router aggregator under this path)
- `services/api/app/schemas/**`
- `services/api/app/services/**`
- Auth/security verifier module under `services/api/app/core/` where approved, e.g. `security.py` or `auth.py` (not shared `config.py`)
- `services/api/tests/api/**`
- `docs/contracts/phase2.openapi.yaml` only through team-reviewed contract PRs

May NOT edit:
- `services/api/app/models/**`, `app/db/**`, `app/repositories/**`, `services/api/alembic/**` (Shresth owns)
- `apps/web/**` (Dhwanit owns)
- `services/api/app/main.py`, `app/core/config.py`, backend dependency manifest, root `.env.example`/`compose.yml` (shared custodian Shresth; submit a small patch request)

Do not implement new database tables or ad hoc schema creation. Do not “fix” DB conflicts by changing Shresth's migration files.

## BRANCH / HANDSHAKE

After contract approval, branch `feat/p2-api-priyanshu` from the shared `integration/phase2` commit. Work in a separate clone/worktree. Before writing services, agree with Shresth on repository functions (names, return types, typed exceptions and session/commit boundary). Canonical semantics are in the contract. If needed, use **local test doubles** of repository interfaces while waiting; replace with real repositories for merged validation. Do not ship test double behavior to production.

## IMPLEMENT 1 — SECURE SUPABASE IDENTITY

- Use provider **user** access tokens sent in `Authorization: Bearer ...` to authenticated FastAPI dependencies.
- Verify JWT cryptographically, valid project `iss`, valid audience `authenticated`, expiration and subject, rejecting inappropriate algorithms, wrong projects, anonymous/public API keys and forged claims.
- Inspect project's actual signing mode: with asymmetric signing use verified provider JWKS; for legacy HS256/shared-secret setups where JWKS lacks public keys, use supported **Supabase Auth server-side get_user(token)** validation or arrange a signed-off migration to an asymmetric signing key. Never use `jwt.decode(..., verify_signature=False)` as authorization.
- Separate auth absence/invalid (401) from provider temporarily unavailable/misconfigured (503 fail-closed). Avoid exposing tokens and secrets in logs.
- Use verified provider identity to map `sub` -> `users.external_auth_id`. Derive email from provider-trusted claims/API, not customer input. Handle potential preexisting email collision without account takeover (`409 IDENTITY_CONFLICT`). Handle concurrent first access safely with Shresth's repository method and unique DB constraint.
- Test token verifier using signed test tokens/provider test infrastructure; injected verified-subject fixtures may exist **only in tests**, never as a runtime public bypass.
- Request server-only config/dependency changes from Shresth; public issuer/JWKS settings can be documented, but do not embed secrets or rely on a shared service-role key in browser.

## IMPLEMENT 2 — API ENDPOINTS (MATCH FROZEN OPENAPI)

Base `/api/v1`; preserve original `/health` and `/health/db` routes and behavior.

1. `GET /users/me` -> 200 `User`; idempotent app-user sync after token verified.
2. `PATCH /users/me` -> 200 `User`, **display_name only** (2–80 chars trimmed).
3. `POST /worker-profiles` -> 201 `WorkerProfile`, first profile `onboarding_status="draft"`; duplicate for same subject -> 409.
4. `GET /worker-profiles/me` -> 200 owned profile or 404.
5. `PATCH /worker-profiles/me` -> 200 owned profile; **only** display_name and nullable bio (max 500); no status/user_id/privileged field accepted.
6. `POST /organizations` -> 201 organization with `my_membership_role="owner"`; Shresth's repository creates organization and membership in **one transaction**.
7. `GET /organizations/mine` -> 200 own organization list including scoped membership roles; no disclosure of other groups.

Use Pydantic v2 strict request schemas, `extra="forbid"`, validation and response models exactly matching the OpenAPI schemas. Response success is direct resource JSON, not `{"success":true,"data":...}`. Error response is `{"error":{"code":"...","message":"..."}}` plus optional details, with 401/403/404/409/422/503/500 semantics. Existing health endpoint schema is exempt from breaking changes.

**Module boundary:** Place API aggregator under `app/api/**`. Do not directly edit `main.py`; provide Shresth exact router registration patch/request for shared integration after API merge. If a global error handler or config change is required, likewise request it through the integration custodian.

## AUTHORIZATION SAFETY

- Every `/me` operation derives owner user ID from **verified token identity** and DB mapping. Ignore/refuse client-supplied `user_id`.
- No publicly callable user enumeration or worker approval endpoints.
- No self-assigned `approved`, `admin`, or membership owner for organizations other than the creator's server-side `owner` creation.
- A new organization with organization_type `cooperative` is **self-classification**, not evidence of registered/legal worker ownership.
- Normal errors should not leak SQL details, server file paths, provider secrets or database credentials.

## TESTS AND PROOF

Test against real merged Postgres/SQLAlchemy repositories, as well as isolated unit tests where useful:
- Missing, malformed, expired, wrong-issuer, wrong-audience, tampered bearer -> 401.
- Configured auth provider unavailable -> 503 and no trusted user created.
- GET `/users/me` safely maps two different verified subjects to two different app users, with no cross-account profile access.
- Concurrent first-use `/users/me` creates one user for a subject.
- Patching `email`, `external_auth_id`, `user_id`, `is_admin`, `onboarding_status` -> 422.
- Worker profile creation -> `draft`; second creation -> 409, no second DB row; GET-before-create -> 404.
- Bio PATCH `null` clears it; illegal or oversized input -> 422.
- Organization creation creates exactly one owner membership; failed membership insert rolls back organization.
- List organizations shows only caller's memberships, including correct role.
- Generated live `/openapi.json` agrees with version-controlled contract for new endpoints; `GET /health` and DB health continue working.
- Verify error mapping (`401`, `404`, `409`, `422`, `503`) and status/field shape.

If the current database migration is not yet integrated, run mock/facade tests now and clearly mark DB-backed tests **PENDING**, then re-run after Shresth's DB PR is merged.

## OUT OF SCOPE — DO NOT BUILD

Jobs, skills/radius/availability, direct hiring, job post applications, bookings, financial ledger, AI/OCR, payment providers, admin/co-op governance, platform ratings, full enterprise features. No dummy or hardcoded API responses marketed as real.

## REQUIRED AGENT OUTPUT

1. Repository audit and contract audit results.
2. Frozen contract PR link/hash + acknowledgements; repository handshake with Shresth.
3. Exact owned files modified; shared-file patch requests instead of direct edits.
4. Actual commands/tests run, output summary, DB integration status and unresolved failures.
5. OpenAPI comparison results; verification mode actually configured.
6. PR into `integration/phase2`, with integration dependencies and code owner sign-off.
7. Final **DONE** only when provider-authenticated API tests operate against real merged database; otherwise report the precise BLOCKED work.

**Non-negotiable:** Correct server-side identity and authorization come before API convenience. Never 'temporarily' disable token checks to make the demo pass.
