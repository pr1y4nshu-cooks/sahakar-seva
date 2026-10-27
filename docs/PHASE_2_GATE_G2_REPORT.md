# SAHAKAR–SEVA — Phase 2 Gate G2 Sign-Off & Database Integration Report

**Date:** 27 October 2026  
**Owner:** Shresth (Database & Infrastructure, Shared Integration Custodian)  
**Contract Version:** 1.0 (SS-P2-2026-10-27)  
**Status:** **GATE G0 PASSED**, **GATE G2 PASSED** — READY FOR PRIYANSHU'S API MERGE  

---

## 1. Executive Summary

As the database/infrastructure owner and shared integration custodian for Team Zephyr's **SAHAKAR–SEVA**, Shresth has completed the Phase 1 baseline audit, authored and applied the additive Phase 2 migration, implemented all agreed database repositories with strict transaction boundaries and concurrency safety, and verified 26 automated integration tests against real PostgreSQL 16/PostGIS.

No existing primary keys were rewritten. All primary keys were verified to already be native PostgreSQL `UUID`s. No data loss occurred, PostGIS remains active, and public health checks `/api/v1/health` and `/api/v1/health/db` remain fully backwards-compatible and operational.

---

## 2. Gate G0: Baseline Reproduction Evidence

- **Baseline Commit SHA:** `e537e991cd82f321f1493e3f0664e68968065f38`
- **Docker Compose:**
  - `sahakar-seva-db-1` on host port `55432` (healthy)
  - `sahakar-seva-api-1` on host port `8000` (healthy)
  - `sahakar-seva-web-1` on host port `5173`
- **Health Endpoints:**
  - `GET /api/v1/health` -> `200 OK`, `{"status":"ok","service":"api"}`
  - `GET /api/v1/health/db` -> `200 OK`, `{"status":"ok","database":"connected"}`
- **PostGIS Extension:** Verified active via `SELECT PostGIS_Version();` -> PostGIS 3.4.
- **Frontend Typecheck & Build:** `tsc -b && vite build` built successfully in 1.05s.

---

## 3. Schema Audit & Additive Migration `0002_phase2_constraints`

### Existing Schema Alignment
Inspection of the running PostgreSQL tables confirmed:
- `users`: PK `id` is `UUID`, `external_auth_id` is nullable and `UNIQUE`, `email` is `UNIQUE` and indexed, `created_at`/`updated_at` are `timestamptz`.
- `worker_profiles`: PK `id` is `UUID`, `user_id` is `UUID` with `UNIQUE` and `FOREIGN KEY` (CASCADE), `onboarding_status` default `'draft'`.
- `organizations`: PK `id` is `UUID`, `name` varchar(160), `organization_type` varchar(20).
- `organization_memberships`: PK `id` is `UUID`, composite `UNIQUE(organization_id, user_id)` named `uq_organization_membership`.

### Additive Migration: `0002_phase2_constraints`
To enforce strict data integrity without any schema breaking changes:
- `ck_worker_profiles_onboarding_status`: `CHECK (onboarding_status IN ('draft', 'pending_review', 'approved', 'restricted'))`
- `ck_organizations_organization_type`: `CHECK (organization_type IN ('business', 'cooperative'))`
- `ck_organization_memberships_role`: `CHECK (membership_role IN ('owner', 'admin', 'member'))`

**Migration Status:**
```
$ docker compose exec api alembic current
0002_phase2_constraints (head)
```

**Rollback Safety:**
`alembic downgrade 0001_foundation` safely drops the 3 CHECK constraints without dropping tables, columns, or rows.

---

## 4. Repositories and Interface Handshake for Priyanshu

All repository operations are implemented under `services/api/app/repositories/`:

### Typed Exceptions (`app.repositories.exceptions`)
- `RepositoryError`: base exception class
- `UserNotFoundError`: raised when querying a non-existent user ID
- `IdentityConflictError`: raised when an email collision occurs with a different `external_auth_id`, preventing account takeover (maps to `409 IDENTITY_CONFLICT`)
- `WorkerProfileExistsError`: raised when a user already has a worker profile (maps to `409 WORKER_PROFILE_EXISTS`)
- `WorkerProfileNotFoundError`: raised when updating a profile that does not exist (maps to `404 RESOURCE_NOT_FOUND`)
- `OrganizationNotFoundError`: raised if an organization ID is not found

### Repository Functions
1. **User Repository (`app.repositories.user_repository`)**:
   - `get_user_by_id(db: Session, user_id: UUID) -> User | None`
   - `get_user_by_external_auth_id(db: Session, external_auth_id: str) -> User | None`
   - `get_user_by_email(db: Session, email: str) -> User | None`
   - `get_or_create_user_from_verified_identity(db: Session, subject: str, email: str, display_name_hint: str) -> User` (atomic with savepoint race-condition protection and email conflict check)
   - `update_own_user_display_name(db: Session, user_id: UUID, display_name: str) -> User`
2. **Worker Profile Repository (`app.repositories.worker_repository`)**:
   - `get_worker_profile_by_user(db: Session, user_id: UUID) -> WorkerProfile | None`
   - `create_worker_profile_for_user(db: Session, user_id: UUID, display_name: str, bio: str | None = None) -> WorkerProfile` (enforces `onboarding_status='draft'`, duplicate raises `WorkerProfileExistsError`)
   - `update_worker_profile_for_user(db: Session, user_id: UUID, display_name: str | None = None, bio: str | None = None, clear_bio: bool = False) -> WorkerProfile` (status fields strictly immutable)
3. **Organization Repository (`app.repositories.organization_repository`)**:
   - `create_organization_with_owner(db: Session, user_id: UUID, name: str, organization_type: str) -> tuple[Organization, OrganizationMembership]` (atomic single-transaction creation, failure rolls back BOTH)
   - `list_organizations_for_user(db: Session, user_id: UUID) -> list[tuple[Organization, str]]` (returns only caller's organizations and roles; strictly excludes other users' organizations)
   - `get_organization_with_role(db: Session, organization_id: UUID, user_id: UUID) -> tuple[Organization, str] | None`

---

## 5. Verification Evidence (All Tests Green)

Test execution command:
```bash
docker compose exec api python -m pytest tests/ -v
```

Output:
```text
tests/db/test_migration_and_integrity.py ......                          [ 23%]
tests/db/test_organization_repository.py .....                           [ 42%]
tests/db/test_user_repository.py ......                                  [ 65%]
tests/db/test_worker_repository.py .......                               [ 92%]
tests/test_health.py ..                                                  [100%]

======================== 26 passed, 1 warning in 0.19s =========================
```

### Negative and Invariant Tests Verified
1. Email collision raises `IdentityConflictError` and prevents account takeover.
2. Idempotent `get_or_create_user_from_verified_identity` returns existing user for same subject.
3. Duplicate worker profile creation raises `WorkerProfileExistsError`.
4. DB CHECK constraint rejects invalid worker onboarding status (e.g. `'super_approved'`).
5. DB CHECK constraint rejects invalid organization type (e.g. `'corporation'`).
6. DB CHECK constraint rejects invalid membership role (e.g. `'superadmin'`).
7. Organization + owner atomic creation rolls back both rows if membership insertion fails.
8. `list_organizations_for_user` isolates User A's organizations from User B.
9. Database health returns HTTP 503 when connection fails.

---

## 6. Required PR Handoff Form

```text
Owner: Shresth (Database & Infrastructure)
Branch / base commit: shresthBranch / e537e991cd82f321f1493e3f0664e68968065f38
Owned paths modified:
  - services/api/alembic/versions/0002_phase2_constraints.py
  - services/api/app/models/user.py
  - services/api/app/models/organization.py
  - services/api/app/repositories/__init__.py
  - services/api/app/repositories/exceptions.py
  - services/api/app/repositories/user_repository.py
  - services/api/app/repositories/worker_repository.py
  - services/api/app/repositories/organization_repository.py
  - services/api/tests/db/conftest.py
  - services/api/tests/db/test_user_repository.py
  - services/api/tests/db/test_worker_repository.py
  - services/api/tests/db/test_organization_repository.py
  - services/api/tests/db/test_migration_and_integrity.py
  - docs/DATABASE_BASELINE_AND_HANDSHAKE.md
  - docs/PHASE_2_GATE_G2_REPORT.md
Contract version and API schema used: SS-P2-2026-10-27 v1.0
Migration revision: 0002_phase2_constraints (head)
Tests actually executed + results: 26/26 passed in 0.19s; web build passed
Demo/manual smoke steps:
  1. curl http://localhost:8000/api/v1/health
  2. curl http://localhost:8000/api/v1/health/db
  3. docker compose exec api python -m pytest tests/ -v
Changes requested in another owner's area: None. Shared integration ready for Priyanshu's routers.
Open blockers and risks: None. Zero data loss risk.
Ready for merge? YES (Gate G2 PASSED)
```
