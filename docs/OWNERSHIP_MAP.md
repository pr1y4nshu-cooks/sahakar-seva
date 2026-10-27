# SAHAKAR–SEVA — Phase 2 Ownership Map & Baseline Audit

**Baseline Commit:** `23e2a1f353a5c0ff06cf3d06d22d5dcc0386e410`  
**Date:** 2026-10-27  
**Contract Version:** 1.0 Frozen (`docs/contracts/phase2.openapi.yaml` & `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md`)

## 1. Baseline Audit Verification Results

| Component | Status | Details |
|---|---|---|
| **Git Default Branch** | `main` | Head at `23e2a1f` (Merge PR #2) |
| **Alembic Revision** | `0001_foundation` | Head revision, PostGIS enabled |
| **Primary Key Types** | `UUID` (v4) | `users.id`, `worker_profiles.id`, `organizations.id`, `organization_memberships.id` all use UUID PKs |
| **users.email** | `String(320)` | `nullable=False`, `unique=True`, indexed |
| **users.external_auth_id**| `String(255)` | `nullable=True`, `unique=True` |
| **worker_profiles.onboarding_status** | `String(40)` | `nullable=False`, `server_default='draft'` |
| **organization_memberships** | `(org_id, user_id)` | `UniqueConstraint('organization_id', 'user_id', name='uq_organization_membership')` |
| **Backend Baseline Tests** | `PASSED` | `test_health` (200), `test_database_health` (503 when DB offline) |
| **Auth Signing Mode** | `Configurable` | Remote Supabase Auth `get_user` API + JWKS asymmetric RS256 + HS256 secret support |

## 2. File Ownership Map

### Priyanshu — FastAPI Backend API, Auth & Contracts (Owner)
- `docs/contracts/phase2.openapi.yaml`
- `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md`
- `docs/OWNERSHIP_MAP.md`
- `services/api/app/schemas/**`
  - `schemas/__init__.py`
  - `schemas/error.py`
  - `schemas/user.py`
  - `schemas/worker.py`
  - `schemas/organization.py`
- `services/api/app/core/security.py` (Auth token verifier and dependencies)
- `services/api/app/services/**`
  - `services/__init__.py`
  - `services/user_service.py`
  - `services/worker_service.py`
  - `services/organization_service.py`
- `services/api/app/api/v1/**`
  - `api/v1/health.py` (Phase 1 preserved)
  - `api/v1/users.py`
  - `api/v1/workers.py`
  - `api/v1/organizations.py`
- `services/api/app/api/router.py` (API router aggregator)
- `services/api/tests/api/**` (API endpoint & auth test suite)

### Shresth — Database, Infrastructure & Shared Custodian
- `services/api/app/models/**`
- `services/api/app/db/**`
- `services/api/app/repositories/**`
- `services/api/alembic/**`
- `services/api/tests/db/**`
- **Shared Custodian Files** (Changes require reviewed patch requests):
  - `services/api/app/main.py`
  - `services/api/app/core/config.py`
  - `services/api/pyproject.toml` / `requirements.txt`
  - `.env.example`
  - `compose.yml`

### Dhwanit — Frontend Web Application
- `apps/web/**`
- `apps/web/.env.example`
- Frontend tests & UI components

## 3. Repository Handshake Agreement (Priyanshu <-> Shresth)

Canonical repository signatures to be implemented in `services/api/app/repositories/`:
1. `get_or_create_user_from_verified_identity(db: Session, external_auth_id: str, email: str, display_name: str | None = None) -> User`
2. `update_own_user_display_name(db: Session, user_id: UUID, display_name: str) -> User`
3. `create_worker_profile_for_user(db: Session, user_id: UUID, display_name: str, bio: str | None = None) -> WorkerProfile`
4. `get_worker_profile_by_user(db: Session, user_id: UUID) -> WorkerProfile | None`
5. `update_worker_profile_for_user(db: Session, user_id: UUID, display_name: str | None = None, bio: str | None = None, clear_bio: bool = False) -> WorkerProfile`
6. `create_organization_with_owner(db: Session, user_id: UUID, name: str, organization_type: str) -> tuple[Organization, OrganizationMembership]`
7. `list_organizations_for_user(db: Session, user_id: UUID) -> list[tuple[Organization, str]]`

Typed exceptions:
- `WorkerProfileExistsError` -> mapped to HTTP 409 `WORKER_PROFILE_EXISTS`
- `IdentityConflictError` -> mapped to HTTP 409 `IDENTITY_CONFLICT`
- `NotFoundError` -> mapped to HTTP 404 `RESOURCE_NOT_FOUND`
