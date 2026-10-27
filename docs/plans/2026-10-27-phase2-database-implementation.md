# Phase 2 Database, Migrations & Repositories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 2 database integrity constraints, Alembic migrations, SQLAlchemy repositories, transaction management, and automated database integration tests for SAHAKAR–SEVA.

**Architecture:** Additive Alembic migration adds DB-level CHECK constraints on status/type/role enum columns without modifying existing UUID primary keys or destroying data. High-reliability SQLAlchemy 2.0 repositories implement explicit transaction boundaries, safe provider identity mapping (`sub` -> `users.external_auth_id`), duplicate worker prevention, atomic organization+owner creation with rollback, and caller-isolated organization listings.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16 + PostGIS, Psycopg 3, Pytest.

**Spec:** `docs/SHRESTH_DATABASE_ANTIGRAVITY_PROMPT.md`, `docs/PHASE_2_TECHNICAL_CONTRACT.md`, and `docs/SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md`.

## Global Constraints

- Never rewrite existing UUID primary keys or alter existing Phase 1 timestamps/columns destructively.
- Preserve PostGIS extension and health check endpoints (`/health`, `/health/db`).
- All migrations must be additive and tested on both fresh and existing DB instances.
- Repositories must never trust unverified tokens or user-supplied target IDs; Priyanshu handles token verification and passes trusted `subject` and `user_id`.
- `external_auth_id` is unique and nullable (for legacy Phase 1 rows); do not automatically link email collisions to new subjects.
- Worker onboarding status defaults to `draft`; no user-facing approval logic in Phase 2.
- Organization and owner membership creation MUST be committed in one single atomic transaction.
- Exclusive edit scope: `services/api/app/models/**`, `services/api/app/db/**`, `services/api/app/repositories/**`, `services/api/alembic/**`, `services/api/tests/db/**`.

## Review Focus

1. **Email Collision with Different Auth Subject:** If an existing row in `users` has the same email but a null or different `external_auth_id`, `get_or_create_user_from_verified_identity` must raise `IdentityConflictError` rather than silently linking or overwriting.
2. **Concurrent First-Time User Sync:** If two concurrent requests arrive with the same verified provider `sub`, database uniqueness on `external_auth_id` prevents duplicate user rows and returns the single created user.
3. **Duplicate Worker Profile:** Calling `create_worker_profile_for_user` for an existing profile owner must raise `WorkerProfileExistsError` and guarantee at most one profile row per user.
4. **Organization Atomicity on Injected Failure:** If inserting the `organization_memberships` row fails after inserting `organizations`, the transaction rolls back both, leaving zero orphaned rows.
5. **Organization Isolation:** `list_organizations_for_user` returns only organizations where `user_id` has an active membership, including their exact role, never leaking other organizations.

---

### Task 1: Baseline Audit and Handshake Interface

**Files:**
- Create: `services/api/app/repositories/__init__.py`
- Create: `services/api/app/repositories/exceptions.py`
- Create: `docs/DATABASE_BASELINE_AND_HANDSHAKE.md`

**Interfaces:**
- Produces: `RepositoryError`, `UserNotFoundError`, `IdentityConflictError`, `WorkerProfileExistsError`, `WorkerProfileNotFoundError`, `OrganizationNotFoundError`

- [ ] **Step 1: Document baseline audit and handshake interfaces in `docs/DATABASE_BASELINE_AND_HANDSHAKE.md`**
Record baseline Git SHA, verified Docker status, table columns, PK types (all UUIDs), and repository function signatures for Priyanshu.

- [ ] **Step 2: Create `services/api/app/repositories/exceptions.py`**
Define typed exceptions:
```python
class RepositoryError(Exception):
    """Base exception for repository operations."""

class UserNotFoundError(RepositoryError):
    pass

class IdentityConflictError(RepositoryError):
    """Raised when an email collision occurs with a different external_auth_id."""

class WorkerProfileExistsError(RepositoryError):
    """Raised when a user already has a worker profile."""

class WorkerProfileNotFoundError(RepositoryError):
    pass

class OrganizationNotFoundError(RepositoryError):
    pass
```

- [ ] **Step 3: Expose exceptions in `services/api/app/repositories/__init__.py`**
Export all exceptions.

- [ ] **Step 4: Verify exceptions can be imported**
Run: `docker compose exec api python -c "from app.repositories import IdentityConflictError, WorkerProfileExistsError; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**
`git add docs/DATABASE_BASELINE_AND_HANDSHAKE.md services/api/app/repositories`
`git commit -m "docs: baseline audit and repository exception definitions"`

---

### Task 2: Additive Alembic Migration for Data Constraints

**Files:**
- Create: `services/api/alembic/versions/0002_phase2_constraints.py`
- Modify: `services/api/app/models/user.py`
- Modify: `services/api/app/models/organization.py`

**Interfaces:**
- Consumes: `0001_foundation`
- Produces: Database CHECK constraints on `worker_profiles.onboarding_status`, `organizations.organization_type`, `organization_memberships.membership_role`

- [ ] **Step 1: Write `services/api/alembic/versions/0002_phase2_constraints.py`**
Define revision `0002_phase2_constraints` with down_revision `0001_foundation`:
- Add CHECK constraint `ck_worker_profiles_onboarding_status`: `onboarding_status IN ('draft', 'pending_review', 'approved', 'restricted')`
- Add CHECK constraint `ck_organizations_organization_type`: `organization_type IN ('business', 'cooperative')`
- Add CHECK constraint `ck_organization_memberships_role`: `membership_role IN ('owner', 'admin', 'member')`
Downgrade drops the 3 check constraints cleanly.

- [ ] **Step 2: Update SQLAlchemy models in `user.py` and `organization.py`**
Add `CheckConstraint` definitions to `WorkerProfile`, `Organization`, and `OrganizationMembership` `__table_args__`.

- [ ] **Step 3: Run Alembic upgrade in the running container**
Run: `docker compose exec api alembic upgrade head`
Expected: Output showing upgrade `0001_foundation -> 0002_phase2_constraints`.

- [ ] **Step 4: Verify Alembic current and DB check constraints**
Run: `docker compose exec api alembic current`
Run: `docker compose exec -T db psql -U sahakar -d sahakar_seva -c "\d worker_profiles"`
Expected: Current is `0002_phase2_constraints (head)` and check constraints are listed.

- [ ] **Step 5: Verify health check still returns 200**
Run: `curl -s http://localhost:8000/api/v1/health/db`
Expected: `{"status":"ok","database":"connected"}`

- [ ] **Step 6: Commit**
`git add services/api/alembic/versions/0002_phase2_constraints.py services/api/app/models/`
`git commit -m "feat(db): add phase 2 check constraints migration and model definitions"`

---

### Task 3: User Repository Implementation

**Files:**
- Create: `services/api/app/repositories/user_repository.py`
- Modify: `services/api/app/repositories/__init__.py`
- Create: `services/api/tests/db/test_user_repository.py`

**Interfaces:**
- Produces:
  - `get_user_by_id(db: Session, user_id: UUID) -> User | None`
  - `get_user_by_external_auth_id(db: Session, external_auth_id: str) -> User | None`
  - `get_user_by_email(db: Session, email: str) -> User | None`
  - `get_or_create_user_from_verified_identity(db: Session, subject: str, email: str, display_name_hint: str) -> User`
  - `update_own_user_display_name(db: Session, user_id: UUID, display_name: str) -> User`

- [ ] **Step 1: Write integration tests in `services/api/tests/db/test_user_repository.py`**
Test:
1. `get_or_create_user_from_verified_identity` creates new user if subject is unknown and email is free.
2. `get_or_create_user_from_verified_identity` returns existing user idempotently when called with same subject.
3. `get_or_create_user_from_verified_identity` raises `IdentityConflictError` if email exists for another `external_auth_id` or unlinked user.
4. `update_own_user_display_name` updates display name and updates `updated_at`.
5. `update_own_user_display_name` raises `UserNotFoundError` if user ID does not exist.

- [ ] **Step 2: Run test to verify it fails**
Run: `docker compose exec api python -m pytest tests/db/test_user_repository.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement `services/api/app/repositories/user_repository.py`**
Implement the user repository functions with:
- Normalized email comparison (strip and lower).
- Sub-transaction / savepoint handling for concurrent collision safety on `external_auth_id` and `email`.
- Typed exceptions `IdentityConflictError` and `UserNotFoundError`.

- [ ] **Step 4: Run test to verify it passes**
Run: `docker compose exec api python -m pytest tests/db/test_user_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
`git add services/api/app/repositories/user_repository.py services/api/app/repositories/__init__.py services/api/tests/db/test_user_repository.py`
`git commit -m "feat(db): implement user repository with safe identity mapping"`

---

### Task 4: Worker Profile Repository Implementation

**Files:**
- Create: `services/api/app/repositories/worker_repository.py`
- Modify: `services/api/app/repositories/__init__.py`
- Create: `services/api/tests/db/test_worker_repository.py`

**Interfaces:**
- Produces:
  - `get_worker_profile_by_user(db: Session, user_id: UUID) -> WorkerProfile | None`
  - `create_worker_profile_for_user(db: Session, user_id: UUID, display_name: str, bio: str | None = None) -> WorkerProfile`
  - `update_worker_profile_for_user(db: Session, user_id: UUID, display_name: str | None = None, bio: str | None = None, clear_bio: bool = False) -> WorkerProfile`

- [ ] **Step 1: Write integration tests in `services/api/tests/db/test_worker_repository.py`**
Test:
1. `create_worker_profile_for_user` creates profile with `onboarding_status="draft"`.
2. Second call to `create_worker_profile_for_user` for same user raises `WorkerProfileExistsError`.
3. `get_worker_profile_by_user` returns profile for user or `None`.
4. `update_worker_profile_for_user` updates `display_name` and `bio`.
5. `update_worker_profile_for_user` with `clear_bio=True` sets bio to `None`.
6. DB check constraint rejects illegal `onboarding_status` if directly inserted.

- [ ] **Step 2: Run test to verify it fails**
Run: `docker compose exec api python -m pytest tests/db/test_worker_repository.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `services/api/app/repositories/worker_repository.py`**
Implement the worker profile functions:
- Enforce `onboarding_status="draft"` on create.
- Catch unique constraint violation on `user_id` and raise `WorkerProfileExistsError`.
- Ensure no status updates are permitted through `update_worker_profile_for_user`.

- [ ] **Step 4: Run test to verify it passes**
Run: `docker compose exec api python -m pytest tests/db/test_worker_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
`git add services/api/app/repositories/worker_repository.py services/api/app/repositories/__init__.py services/api/tests/db/test_worker_repository.py`
`git commit -m "feat(db): implement worker profile repository with draft enforcement"`

---

### Task 5: Organization Repository Implementation

**Files:**
- Create: `services/api/app/repositories/organization_repository.py`
- Modify: `services/api/app/repositories/__init__.py`
- Create: `services/api/tests/db/test_organization_repository.py`

**Interfaces:**
- Produces:
  - `create_organization_with_owner(db: Session, user_id: UUID, name: str, organization_type: str) -> tuple[Organization, OrganizationMembership]`
  - `list_organizations_for_user(db: Session, user_id: UUID) -> list[tuple[Organization, str]]`
  - `get_organization_with_role(db: Session, organization_id: UUID, user_id: UUID) -> tuple[Organization, str] | None`

- [ ] **Step 1: Write integration tests in `services/api/tests/db/test_organization_repository.py`**
Test:
1. `create_organization_with_owner` creates organization and owner membership in the same transaction.
2. Injected failure during membership insert leaves NEITHER organization nor membership in the DB (atomic rollback).
3. `list_organizations_for_user` returns caller's organizations with role `owner`.
4. User A's organizations are excluded from User B's `list_organizations_for_user`.
5. Check constraint on `organization_type` rejects invalid types (`"corporation"` fails, `"business"` and `"cooperative"` succeed).

- [ ] **Step 2: Run test to verify it fails**
Run: `docker compose exec api python -m pytest tests/db/test_organization_repository.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `services/api/app/repositories/organization_repository.py`**
Implement:
- `create_organization_with_owner`: atomic creation in single subtransaction/session transaction, with rollback on error.
- `list_organizations_for_user`: joins `Organization` and `OrganizationMembership` filtering strictly by `user_id == caller_id`.

- [ ] **Step 4: Run test to verify it passes**
Run: `docker compose exec api python -m pytest tests/db/test_organization_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
`git add services/api/app/repositories/organization_repository.py services/api/app/repositories/__init__.py services/api/tests/db/test_organization_repository.py`
`git commit -m "feat(db): implement organization repository with atomic owner transaction"`

---

### Task 6: Full Integration Gate G0-G2 Verification and Report

**Files:**
- Create: `services/api/tests/db/test_migration_and_integrity.py`
- Create: `docs/PHASE_2_GATE_G2_REPORT.md`

- [ ] **Step 1: Write migration integrity test**
Test:
1. Fresh database -> head upgrade succeeds.
2. 0001 -> 0002 upgrade succeeds with existing rows preserved.
3. PostGIS extension is active (`SELECT PostGIS_Version()`).
4. Database health endpoint `/api/v1/health/db` responds 200 when connected and 503 when down.

- [ ] **Step 2: Run all database tests and health tests**
Run: `docker compose exec api python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Run frontend production build to guarantee zero shared breakages**
Run: `docker compose exec web npm run build`
Expected: Build passes with 0 errors.

- [ ] **Step 4: Write `docs/PHASE_2_GATE_G2_REPORT.md`**
Document:
- Baseline reproduction results and Git commit SHA.
- Schema audit confirmation (all PKs UUIDs, table columns, constraints).
- Migration `0002_phase2_constraints` safety and rollback procedure.
- Repository signatures and typed exceptions for Priyanshu.
- Test commands and logs.
- Gate G0 and G2 sign-off status: READY FOR API MERGE.

- [ ] **Step 5: Commit and verify status**
`git add services/api/tests/db/ docs/PHASE_2_GATE_G2_REPORT.md`
`git commit -m "docs: complete phase 2 gate G2 verification and test report"`
