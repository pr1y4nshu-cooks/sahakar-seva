# SAHAKAR–SEVA — Database Baseline Audit & Repository Interface Handshake

**Document ID:** SS-DB-AUDIT-2026-10-27  
**Owner:** Shresth (Database & Infrastructure)  
**Teammates:** Priyanshu (Backend API & Auth), Dhwanit (Frontend)  
**Baseline Commit SHA:** `e537e991cd82f321f1493e3f0664e68968065f38`  
**Status:** Baseline Audited; Handshake Defined; Gate G0 Verified  

---

## 1. Baseline Reproduction & Verification (Gate G0)

All Phase 1 services, database migrations, and health checks were independently verified on this clone:

| Component | Status | Verification Command & Result |
|---|---|---|
| **Git Working Tree** | Clean, branch `shresthBranch` | `git status` clean |
| **Docker Compose** | Up & Healthy | `sahakar-seva-db-1` (port 55432, healthy), `sahakar-seva-api-1` (port 8000), `sahakar-seva-web-1` (port 5173) |
| **Alembic Revision** | `0001_foundation (head)` | `docker compose exec api alembic current` -> `0001_foundation (head)` |
| **API Health** | 200 OK | `curl http://localhost:8000/api/v1/health` -> `{"status":"ok","service":"api"}` |
| **Database Health** | 200 OK | `curl http://localhost:8000/api/v1/health/db` -> `{"status":"ok","database":"connected"}` |
| **PostGIS Extension** | Enabled | `CREATE EXTENSION IF NOT EXISTS postgis` in `0001_foundation` active |
| **Backend Tests** | 2 Passed | `docker compose exec api python -m pytest` -> `2 passed in 0.07s` |
| **Frontend Build** | Passed | `docker compose exec web npm run build` -> `tsc -b && vite build` built in 1.09s |

---

## 2. Actual Phase 1 Schema Audit

Inspection of the running PostgreSQL 16 database confirms:

### `users`
- `id`: `UUID`, PRIMARY KEY, default `uuid4`
- `external_auth_id`: `character varying(255)`, nullable, UNIQUE (`users_external_auth_id_key`)
- `display_name`: `character varying(120)`, NOT NULL
- `email`: `character varying(320)`, NOT NULL, UNIQUE (`users_email_key`), indexed (`ix_users_email`)
- `created_at`: `timestamptz`, NOT NULL, default `now()`
- `updated_at`: `timestamptz`, NOT NULL, default `now()`

### `worker_profiles`
- `id`: `UUID`, PRIMARY KEY, default `uuid4`
- `user_id`: `UUID`, NOT NULL, UNIQUE (`worker_profiles_user_id_key`), FK `users(id)` ON DELETE CASCADE, indexed (`ix_worker_profiles_user_id`)
- `display_name`: `character varying(120)`, NOT NULL
- `bio`: `text`, nullable
- `onboarding_status`: `character varying(40)`, NOT NULL, default `'draft'`
- `created_at`: `timestamptz`, NOT NULL, default `now()`
- `updated_at`: `timestamptz`, NOT NULL, default `now()`

### `organizations`
- `id`: `UUID`, PRIMARY KEY, default `uuid4`
- `name`: `character varying(160)`, NOT NULL
- `organization_type`: `character varying(20)`, NOT NULL
- `created_at`: `timestamptz`, NOT NULL, default `now()`
- `updated_at`: `timestamptz`, NOT NULL, default `now()`

### `organization_memberships`
- `id`: `UUID`, PRIMARY KEY, default `uuid4`
- `organization_id`: `UUID`, NOT NULL, FK `organizations(id)` ON DELETE CASCADE
- `user_id`: `UUID`, NOT NULL, FK `users(id)` ON DELETE CASCADE, indexed (`ix_organization_memberships_user_id`)
- `membership_role`: `character varying(40)`, NOT NULL
- `created_at`: `timestamptz`, NOT NULL, default `now()`
- Composite Unique Constraint: `(organization_id, user_id)` named `uq_organization_membership`

### Pre-Freeze Analysis & Observations
1. **Primary Key Alignment:** ALL primary keys are already PostgreSQL native `UUID` types. No primary key rewrite is needed.
2. **Nullable Provider Identity:** `external_auth_id` is already nullable and unique, allowing existing Phase 1 users to exist while enforcing uniqueness for all mapped Supabase auth subjects.
3. **Missing DB Check Constraints:** While `onboarding_status`, `organization_type`, and `membership_role` columns exist as `varchar`, they lack explicit SQL CHECK constraints restricting permitted enum values.
4. **Action:** Migration `0002_phase2_constraints` will be added to strictly enforce:
   - `worker_profiles.onboarding_status IN ('draft', 'pending_review', 'approved', 'restricted')`
   - `organizations.organization_type IN ('business', 'cooperative')`
   - `organization_memberships.membership_role IN ('owner', 'admin', 'member')`
   Because all tables currently contain 0 rows, this migration has zero data loss risk.

---

## 3. Repository Handshake Agreement with Priyanshu (Backend API)

### Transaction and Session Lifecycle
- FastAPI dependencies (`get_db`) provide a scoped SQLAlchemy `Session` per HTTP request.
- Read operations and simple updates are executed within the request session.
- Multi-row operations (`create_organization_with_owner`) use atomic subtransaction savepoints so that any insert failure immediately rolls back all staged entities without committing partial state.

### Typed Exceptions (`app.repositories.exceptions`)
- `RepositoryError`: base exception class.
- `UserNotFoundError`: raised when querying a non-existent user ID for updates.
- `IdentityConflictError`: raised by `get_or_create_user_from_verified_identity` if the verified email already belongs to a user with a different `external_auth_id` (preventing account takeover). Priyanshu maps this to HTTP `409 IDENTITY_CONFLICT`.
- `WorkerProfileExistsError`: raised when attempting to create a second worker profile for a user who already has one. Priyanshu maps this to HTTP `409 WORKER_PROFILE_EXISTS`.
- `WorkerProfileNotFoundError`: raised when updating a profile that does not exist. Priyanshu maps to HTTP `404 RESOURCE_NOT_FOUND`.
- `OrganizationNotFoundError`: raised if an organization ID is not found.

### Repository Signatures (`services/api/app/repositories/`)

#### 1. User Repository (`app.repositories.user_repository`)
```python
def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    ...

def get_user_by_external_auth_id(db: Session, external_auth_id: str) -> User | None:
    ...

def get_user_by_email(db: Session, email: str) -> User | None:
    ...

def get_or_create_user_from_verified_identity(
    db: Session,
    subject: str,
    email: str,
    display_name_hint: str
) -> User:
    """
    Safely resolves or creates an application user from a verified token identity.
    - If subject matches existing external_auth_id, returns user.
    - If subject not found, checks normalized email. If email belongs to another subject, raises IdentityConflictError.
    - If email is unassigned, atomically inserts new User with external_auth_id=subject.
    - Catches race-condition unique constraint violations on concurrent first requests and returns the winner.
    """
    ...

def update_own_user_display_name(db: Session, user_id: UUID, display_name: str) -> User:
    """
    Updates own user's display_name. Validates existence and commits change.
    Raises UserNotFoundError if not found.
    """
    ...
```

#### 2. Worker Profile Repository (`app.repositories.worker_repository`)
```python
def get_worker_profile_by_user(db: Session, user_id: UUID) -> WorkerProfile | None:
    ...

def create_worker_profile_for_user(
    db: Session,
    user_id: UUID,
    display_name: str,
    bio: str | None = None
) -> WorkerProfile:
    """
    Creates a new worker profile for user with onboarding_status='draft'.
    Raises WorkerProfileExistsError if a profile already exists for this user.
    """
    ...

def update_worker_profile_for_user(
    db: Session,
    user_id: UUID,
    display_name: str | None = None,
    bio: str | None = None,
    clear_bio: bool = False
) -> WorkerProfile:
    """
    Updates worker profile editable fields (display_name, bio).
    Strictly forbids status modifications.
    Raises WorkerProfileNotFoundError if profile does not exist.
    """
    ...
```

#### 3. Organization Repository (`app.repositories.organization_repository`)
```python
def create_organization_with_owner(
    db: Session,
    user_id: UUID,
    name: str,
    organization_type: str
) -> tuple[Organization, OrganizationMembership]:
    """
    Atomically creates an organization and the creator's owner membership.
    If either fails, the transaction is rolled back and neither row is persisted.
    """
    ...

def list_organizations_for_user(
    db: Session,
    user_id: UUID
) -> list[tuple[Organization, str]]:
    """
    Lists all organizations where user_id has a membership, returning tuples of
    (Organization, membership_role). Does NOT disclose organizations where user is not a member.
    """
    ...

def get_organization_with_role(
    db: Session,
    organization_id: UUID,
    user_id: UUID
) -> tuple[Organization, str] | None:
    ...
```
