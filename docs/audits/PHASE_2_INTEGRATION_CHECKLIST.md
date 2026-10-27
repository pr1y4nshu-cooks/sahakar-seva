# SAHAKAR–SEVA — Phase 2 Developer Integration Checklist

**Audit Date:** 2026-10-27  
**Auditor:** Principal Software Architect & QA Lead  
**Teammates:** Dhwanit (Frontend), Priyanshu (Backend & Auth), Shresth (Database & Repositories)  

---

## 1. Developer Action Checklist

### Priyanshu (Backend, Authentication & Contracts)

- [ ] **SEC-02: Add `SUPABASE_JWT_SECRET` to `.env.example`**
  - Add `SUPABASE_JWT_SECRET=` with comments explaining Mode A (local cryptographic HMAC-SHA256 signature check) vs Mode B (remote Supabase Auth REST verification).
  - *Validation:* `grep SUPABASE_JWT_SECRET .env.example`
- [ ] **ARCH-01: Connect Services to Canonical Repositories**
  - Update `services/api/app/services/user_service.py` to use `app.repositories.user_repository`.
  - Update `services/api/app/services/worker_service.py` to use `app.repositories.worker_repository`.
  - Update `services/api/app/services/organization_service.py` to use `app.repositories.organization_repository`.
  - *Validation:* `pytest services/api/tests/` (all 44 tests must continue to pass).
- [ ] **ARCH-02: Remove Obsolete/Dead Code**
  - Delete or reconcile unused `services/api/app/core/auth.py`.
  - Delete unused `services/api/app/repositories/user.py`.
  - *Validation:* `git status` confirming removal; `pytest` passes with no import errors.
- [ ] **DOC-01: Add Error Response Schemas to Route Decorators**
  - In `users.py`, `workers.py`, and `organizations.py`, add `responses={401: ..., 404: ..., 409: ..., 422: ..., 503: ...}` so FastAPI Swagger docs reflect all failure modes.
  - *Validation:* Run API and check `http://localhost:8000/docs` or `services/api/.venv/bin/python -c "from app.main import app; print(app.openapi()['paths']['/api/v1/users/me']['get']['responses'])"`.

---

### Shresth (Database, Migrations & Shared Custodian)

- [ ] **SEC-01: Update and Rebuild Docker Container**
  - Rebuild API Docker container to include `python-jose`: `docker compose build api`.
  - Verify container startup: `docker compose up -d` followed by `docker compose ps` and `curl http://localhost:8000/api/v1/health`.
  - *Validation:* Container status is `Up` and does not restart with `ModuleNotFoundError`.
- [ ] **CODE-01: Fix `allowed_origins` Typing in Settings**
  - Update `services/api/app/core/config.py` to handle comma-separated string parsing into `list[str]` via Pydantic validator rather than mutating an instance attribute in `get_settings()`.
  - *Validation:* Run backend tests and verify `settings.allowed_origins` is type-safe.
- [ ] **DB-01: Confirm Migration & Constraint Integrity**
  - Ensure `0001_foundation` and `0002_phase2_constraints` stay locked and unedited.
  - *Validation:* `services/api/.venv/bin/pytest services/api/tests/db/` (all tests pass).

---

### Dhwanit (Frontend & UI Integration)

- [ ] **INT-01: Commit `apps/web/.env.example`**
  - Create `apps/web/.env.example` with:
    ```env
    VITE_API_BASE_URL=http://localhost:8000
    VITE_SUPABASE_URL=https://your-project.supabase.co
    VITE_SUPABASE_ANON_KEY=your-anon-key
    ```
  - *Validation:* `test -f apps/web/.env.example`
- [ ] **UI-01: Verify Real Supabase Login Flow with Backend**
  - Test browser token flow end-to-end against local API (`localhost:8000`).
  - *Validation:* Run `npm run test` and `npm run typecheck` in `apps/web/`.

---

## 2. Standard Validation Commands

Run these commands in order from project root before requesting final Phase 2 sign-off:

```bash
# 1. Backend & Database Tests (all 44 tests)
services/api/.venv/bin/pytest services/api/tests/

# 2. Database Migration Status
docker exec sahakar-seva-db-1 psql -U sahakar -d sahakar_seva -c "SELECT version_num FROM alembic_version;"
# Expected: 0002_phase2_constraints

# 3. Docker Compose Build & Smoke Test
docker compose build api
docker compose up -d
curl -s http://localhost:8000/api/v1/health | grep '"status":"ok"'
curl -s http://localhost:8000/api/v1/health/db | grep '"database":"connected"'

# 4. Frontend Vitest & TypeScript Check
cd apps/web && npm run test && npm run typecheck && cd ../..
```

---

## 3. Merge Readiness Matrix

| Component | Owner | Readiness Status | Remaining Action |
|---|---|---|---|
| **Database Models & Alembic** | Shresth | **READY** | None. PostGIS, constraints, models fully verified. |
| **Database Repositories** | Shresth | **READY** | Tested and verified in `tests/db/`. |
| **Backend API Endpoints** | Priyanshu | **READY (CONDITIONAL)** | Connect service layer to Shresth's repositories (`ARCH-01`). |
| **Authentication & Security** | Priyanshu | **READY (CONDITIONAL)** | Document `SUPABASE_JWT_SECRET` (`SEC-02`), clean obsolete `auth.py` (`ARCH-02`). |
| **Frontend Application** | Dhwanit | **READY (CONDITIONAL)** | Add `apps/web/.env.example` (`INT-01`). |
| **Docker Compose Environment**| Shared | **READY (CONDITIONAL)** | Rebuild container image with `python-jose` (`SEC-01`). |
