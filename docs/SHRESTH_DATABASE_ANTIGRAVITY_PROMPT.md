# Antigravity Prompt — Shresth — Phase 2 Database, Migrations & Integration

You are the **database/infrastructure owner and shared integration custodian** for Team Zephyr's **SAHAKAR–SEVA**. Your assigned developer is **Shresth**. You own the persistence layer and must preserve the confirmed Phase 1 PostgreSQL/PostGIS/Alembic foundation while supporting Priyanshu's auth/API contract and Dhwanit's frontend.

## REQUIRED REFERENCES AND BASELINE AUDIT

Read first:
1. `docs/PROJECT_BLUEPRINT.md`.
2. `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md`.
3. `docs/contracts/phase2.openapi.yaml`.
4. Actual Phase 1 Alembic revision `0001_foundation`, SQLAlchemy models/DB dependencies, Compose and configuration.

The team reported: PostgreSQL 16/PostGIS running with host port **55432**, Alembic `0001_foundation` at head, `/health` and `/health/db` working, two backend tests passed, frontend production build passed. **Independently reproduce this on your clone.** Record Git SHA, existing table/column types, constraints, nullable fields, timestamp conventions, and whether the current schema already satisfies this phase.

If existing PKs are not UUIDs or database fields differ from the draft contract, stop **only schema-dependent edits**, record exact discrepancy, and obtain Priyanshu's and Dhwanit's explicit agreement. Never rewrite existing primary keys without a separately approved data-safe migration plan.

## YOUR EXCLUSIVE SCOPE

You MAY edit:
- `services/api/app/models/**`
- `services/api/app/db/**`
- `services/api/app/repositories/**`
- `services/api/alembic/**` and revision files
- `services/api/tests/db/**`
- Database integration scripts and DB-specific Compose/env configuration, respecting existing functionality

You are also **sole integration custodian** for reviewed changes to shared files: `services/api/app/main.py`, `app/core/config.py`, `services/api/pyproject.toml`/dependency lockfile, root `.env.example`, root `compose.yml`, root README. Do **not** implement Priyanshu's routes or Dhwanit's UI in those files. Changes to shared files require a small documented patch request and the requesting owner's review.

You MUST NOT directly edit:
- `apps/web/**` (Dhwanit)
- `services/api/app/api/**`, `app/schemas/**`, `app/services/**`, auth verifier module (Priyanshu)
- Frozen OpenAPI response/request shapes without full-team contract approval.

## BRANCH AND CONTRACT HANDSHAKE

After all three approve the frozen baseline and OpenAPI contract, create `feat/p2-db-shresth` from `integration/phase2` in your own clone/worktree.

Before implementing repositories, agree with Priyanshu on exact model fields, session lifecycle, typed exceptions, and signatures. Proposed required repository operations:
- `get_or_create_user_from_verified_identity(subject, email, display_name_hint)`;
- `update_own_user_display_name(user_id, display_name)`;
- `create_worker_profile_for_user(user_id, display_name, bio)`;
- `get_worker_profile_by_user(user_id)`;
- `update_worker_profile_for_user(user_id, fields)`;
- `create_organization_with_owner(user_id, name, organization_type)`;
- `list_organizations_for_user(user_id)`.

You own implementation internals and safe transactional behavior; Priyanshu owns the HTTP responses and token verification. Explicitly document who commits/rolls back the request transaction to prevent double commits or split transactions.

## DATABASE REQUIREMENTS

**users:** provider identity `external_auth_id` nullable for preexisting Phase 1 users and unique when present. A securely verified provider subject may map to only one user. Existing normalized email uniqueness may need conflict-safe handling; **do not automatically link old email-only accounts to new subjects**. Preserve old rows. No customer-controllable `is_admin` field or role flag.

**worker_profiles:** at most one row per user enforced by DB unique constraint; `display_name`, nullable `bio`; `onboarding_status` allowed values `draft`, `pending_review`, `approved`, `restricted` and default `draft`. Phase 2 does **not** implement approval logic. Enforce nonnullable, FK and permitted values appropriately; no worker-written status updates.

**organizations:** `name`, `organization_type` constrained to `business` or `cooperative`; creation alone never implies legally verified status.

**organization_memberships:** `(organization_id,user_id)` unique, roles among `owner`, `admin`, `member`; creation of an organization inserts its creator's owner membership **in one transaction**. Never write organization before committing membership in a separate transaction.

**Schema compatibility:** Reuse actual Phase 1 model patterns, PK type, timestamps and migration conventions. Add constraints/indexes only if missing and proven safe. If an existing dataset violates a proposed uniqueness/check constraint, report offending counts and reconcile with team; **do not delete/mutate user data automatically**.

**No new Phase 3 tables/fields:** no skills/radius/location, jobs, job applications, bookings, payments, ledgers, reviews, verification documents, raw Aadhaar, welfare tracking, or cooperative federation.

## MIGRATION PROCEDURE

1. Run Alembic current/head and inspect `0001_foundation` tables plus indexes.
2. Create a new additive Phase 2 revision **only if a real DB change is required**. If everything exists with correct constraints, document that no new migration is necessary; do not create a meaningless revision.
3. Test on a **fresh empty Postgres database** (base -> head).
4. Test on a **Phase 1-populated database**, preserving sample rows (0001 -> Phase 2 head).
5. Assert PostGIS remains enabled and `/api/v1/health/db` remains operational.
6. Avoid `drop_all`, `create_all` on app startup, `alembic downgrade base` against real team data, or any `--accept-data-loss`/reset shortcut.
7. Provide migration forward safety notes and clear rollback limitations if constraints or data transformations are involved.

Use host port **55432** as reported by Phase 1 for local DB connections unless the actual Compose env deliberately overrides it; ensure container-to-container hostname/port remain correct (often database service name and internal port 5432). Do not silently switch all developers to a new DB port.

## REPOSITORIES / TRANSACTIONS

- Use SQLAlchemy 2.0 session management from the existing Phase 1 app. Each API request should have a defined session and transaction lifecycle.
- Create safe `get_or_create_user_from_verified_identity` with a unique DB guarantee and conflict handling under concurrent first requests.
- Map verified auth subject; no repository method should trust unverified tokens, and no repository should infer access rights from raw user-provided IDs alone. Priyanshu handles identity verification and authorization before calling persistence.
- Worker duplicate create raises a typed conflict; two concurrent creates cannot make two rows.
- `create_organization_with_owner` must insert organization and owner membership atomically, provide an injectable failure test, and roll back both on failure.
- `list_organizations_for_user` must filter by caller's membership. Return only columns/relations needed to build the frozen API response, including membership role.
- Document typed exceptions and return interfaces for Priyanshu. Do not create API response envelopes in the repository layer.

## SHARED-FILE INTEGRATION DUTY

- Priyanshu may request dependency additions, config settings, `main.py` router registration or a global error handler. Apply such changes **only after reading his exact request and checking current files**; include minimal edits and request his review.
- Ensure `app/main.py` wires the real Phase 2 API aggregator after Priyanshu's router branch merges. Do not leave code existing but unreachable because router was never registered.
- Preserve original health endpoints and existing Phase 1 startup semantics.
- Update `.env.example` without secrets. If Supabase is not configured, protected APIs must fail closed, while public health endpoints and DB infrastructure continue to function.

## TESTS / REQUIRED PROOF

Run actual database integration tests and report commands:
- `0001_foundation` -> new revision upgrade works with existing rows; fresh DB -> head works.
- Database enforces unique `external_auth_id`, unique worker `user_id` and unique org membership pair.
- Onboarding status defaults to `draft` and DB rejects an invalid status when constraints exist.
- Concurrent first auth-user sync yields exactly one row for one provider subject.
- Duplicate worker profiles do not persist even under concurrent attempts.
- Organization + owner creation succeeds together; simulated owner-row failure leaves **neither** row.
- Listing organizations for User A excludes organizations belonging only to User B.
- Existing `/api/v1/health/db` responds successfully with DB up, and HTTP 503 with DB down.
- Alembic current/head and data retention verified; no secrets committed.

Where full API tests depend on Priyanshu's unmerged branch, clearly mark them pending and later run them after API merge. Do not claim that a DB unit test proves end-to-end user authorization.

## OUT OF SCOPE

No frontend changes, API/auth implementation, fake users, service matching, job/booking tables, payment integration, real welfare, AI, platform admin UI, cooperative legal governance, or unrelated database redesign.

## DELIVERY / GIT REQUIREMENTS

1. Report actual schema inspection results and any blockers before writing a migration.
2. Record repository handshake with Priyanshu and contract sign-off.
3. Implement DB code only within owned paths; open `feat/p2-db-shresth` PR into `integration/phase2` before API and UI integration.
4. Provide actual migration revision(s) or state explicitly **no migration needed**, commands and test logs.
5. After Priyanshu's API branch merges, own approved shared-file integration in a small follow-up PR, preserving health and app startup.
6. Coordinate team G0–G6 merge gates and record clean-checkout instructions.
7. End with paths touched, tests executed, actual results, any data/migration risks, and DONE/NOT DONE status.

**Non-negotiable:** No destructive migrations, invented schema assumptions or cross-agent file editing. A consistent model with tested transactions matters more than adding features.
