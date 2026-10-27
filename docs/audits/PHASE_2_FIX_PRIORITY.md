# SAHAKAR–SEVA — Phase 2 Fix Priority & Remediation Plan

**Audit Date:** 2026-10-27  
**Auditor:** Principal Software Architect & Security Auditor  
**Status:** Actionable Developer Guidance  

All confirmed issues are organized by strict remediation order to guide the engineering team efficiently.

---

## 1. Security & Data Integrity (Priority 1)

### Issue `SEC-01`: Docker Compose API Image Missing `python-jose`
- **Severity:** HIGH / OPERATIONAL BLOCKER
- **Location:** `services/api/Dockerfile`, `compose.yml`
- **Owner:** Shresth (Shared Custodian) & Priyanshu
- **Description:**
  The API container crashes on startup with `ModuleNotFoundError: No module named 'jose'` when started with default `docker compose up`. The dependency was added to `pyproject.toml` in commit `01dc0ab` after the original Docker image had been built. Because `compose.yml` mounts `./services/api:/app` over the pre-built container without triggering a pip reinstall, the container fails in production/local container environments.
- **Remediation:**
  1. Rebuild the docker image: `docker compose build api`.
  2. In `compose.yml`, update the startup command or container entrypoint to verify dependencies if running in reload dev mode, or ensure team documentation mandates `docker compose up --build`.

---

### Issue `SEC-02`: Missing `SUPABASE_JWT_SECRET` in `.env.example`
- **Severity:** MEDIUM / SECURITY DOCUMENTATION
- **Location:** `.env.example`
- **Owner:** Priyanshu
- **Description:**
  `services/api/app/core/security.py` line 83 supports Mode A HS256 cryptographic verification using `SUPABASE_JWT_SECRET`. However, `.env.example` only lists `SUPABASE_URL` and `SUPABASE_ANON_KEY`. Developers and operators configuring new environments have no notice that `SUPABASE_JWT_SECRET` is supported or required for offline signature checks.
- **Remediation:**
  Add `SUPABASE_JWT_SECRET=` with explanatory comments in `.env.example`.

---

## 2. Contract-Breaking Schema Changes (Priority 2)

*No contract-breaking schema changes were detected during the Phase 2 audit.*  
All Pydantic request and response schemas strictly enforce or conform to `docs/contracts/phase2.openapi.yaml`.

---

## 3. Required Backend Failures & Architecture Gaps (Priority 3)

### Issue `ARCH-01`: Service Layer Bypasses Agreed Database Repositories
- **Severity:** MEDIUM / ARCHITECTURAL INTEGRITY
- **Location:**
  - `services/api/app/services/user_service.py`
  - `services/api/app/services/worker_service.py`
  - `services/api/app/services/organization_service.py`
  - `services/api/app/repositories/`
- **Owner:** Priyanshu (with Shresth)
- **Description:**
  Per the Phase 2 Handshake Agreement in `docs/OWNERSHIP_MAP.md`, Shresth implemented canonical data-access functions in `app/repositories/user_repository.py`, `worker_repository.py`, and `organization_repository.py`. Priyanshu's service classes bypass these repositories entirely and execute direct SQLAlchemy ORM queries and commits. This introduces duplicated business and transaction logic.
- **Remediation:**
  Refactor `UserService`, `WorkerService`, and `OrganizationService` to delegate query and persistence operations to the canonical repository functions, translating repository domain exceptions (`UserNotFoundError`, `WorkerProfileExistsError`, `IdentityConflictError`) to HTTP exceptions in the service or router layer.

---

### Issue `ARCH-02`: Competing / Unused Auth & Repository Modules (`auth.py` and `user.py`)
- **Severity:** MEDIUM / DEAD CODE & CONFUSION
- **Location:**
  - `services/api/app/core/auth.py`
  - `services/api/app/repositories/user.py`
- **Owner:** Priyanshu
- **Description:**
  `app/core/auth.py` implements an RS256 JWKS fetcher and imports `UserRepository` from `app/repositories/user.py`. Neither file is used by any router in `app/api/v1/` (all routers use `app/core/security.py` and `app/services/`). Keeping these obsolete modules confuses developers and static analysis tools.
- **Remediation:**
  Deprecate and remove `services/api/app/core/auth.py` and `services/api/app/repositories/user.py` (or merge any JWKS capability into `services/api/app/core/security.py` if RS256 key rotation is required).

---

## 4. API & Frontend Integration Mismatches (Priority 4)

### Issue `INT-01`: Missing `apps/web/.env.example`
- **Severity:** LOW / INTEGRATION READINESS
- **Location:** `apps/web/.env.example`
- **Owner:** Dhwanit
- **Description:**
  `docs/OWNERSHIP_MAP.md` assigned `apps/web/.env.example` to Dhwanit. The frontend code requires `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`, but no example file exists in `apps/web/` to instruct developers how to set up the client.
- **Remediation:**
  Commit `apps/web/.env.example` containing:
  ```env
  VITE_API_BASE_URL=http://localhost:8000
  VITE_SUPABASE_URL=
  VITE_SUPABASE_ANON_KEY=
  ```

---

## 5. Missing Negative-Case Tests & Documentation Metadata (Priority 5)

### Issue `DOC-01`: OpenAPI Route Decorators Omit Error Response Declarations
- **Severity:** LOW / OPENAPI SCHEMA METADATA
- **Location:** `services/api/app/api/v1/` (`users.py`, `workers.py`, `organizations.py`)
- **Owner:** Priyanshu
- **Description:**
  The route handlers return contract-compliant errors (401, 404, 409, 422, 503) through `ContractCompliantRoute` and custom exception handlers, but the `@router.<method>` decorators omit `responses={401: {"model": ErrorResponse}, ...}`. Thus, auto-generated OpenAPI docs in Swagger UI only list 200/201.
- **Remediation:**
  Add standard response schemas to route decorators to ensure the generated documentation is comprehensive.

---

### Issue `CODE-01`: Typing Inconsistency for `allowed_origins` in `Settings`
- **Severity:** LOW / CODE HEALTH
- **Location:** `services/api/app/core/config.py`
- **Owner:** Shresth (Shared Custodian) / Priyanshu
- **Description:**
  `Settings.allowed_origins` is typed as `str`, but `get_settings()` dynamically mutates it to `list[str]`.
- **Remediation:**
  Change `Settings.allowed_origins: str | list[str]` or use a Pydantic field validator to parse comma-separated strings directly into `list[str]`.
