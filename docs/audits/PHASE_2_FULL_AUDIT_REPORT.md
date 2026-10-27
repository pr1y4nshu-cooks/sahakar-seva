# SAHAKAR–SEVA — Comprehensive Phase 2 Integration, Architecture & Product Compliance Audit

**Audit Date:** 2026-10-27  
**Auditor Roles:** Principal Software Architect, Senior Backend Engineer, Database Architect, Application Security Auditor, Independent Technical Reviewer  
**Repository Path:** `/Users/shresthchauhan/Downloads/hackathons/code yudh/sahakar-seva`  
**Team Members:** Dhwanit (Frontend), Priyanshu (Backend & Auth), Shresth (Database & Infrastructure)  
**Contract Baseline:** `docs/contracts/phase2.openapi.yaml` & `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md` (v1.0 Frozen)  

---

## 1. Executive Summary

A comprehensive, evidence-based integration and compliance audit was performed on the SAHAKAR–SEVA project following Phase 2 implementation. Phase 2 focuses on establishing **Unified Identity, Worker Profiles, Organization Tenancy, and Core Security**.

### Key Audit Findings:
1. **Core Functionality & Contract Conformance:**
   - All 9 required endpoints (2 health, 2 user, 3 worker profile, 2 organization) are implemented, mounted under `/api/v1`, and functionally operational.
   - Pydantic models strictly validate request bodies, reject empty updates, and forbid unexpected or privileged fields (`extra="forbid"`).
   - All 44 automated backend and database tests pass in 0.38 seconds.
   - All 3 frontend tests pass, and frontend TypeScript typechecking passes with 0 errors.
2. **Database & Migration Integrity:**
   - PostgreSQL 16 with PostGIS 3.4 is operational and verified.
   - Alembic revisions (`0001_foundation` and `0002_phase2_constraints`) apply cleanly, enforce primary key UUIDs, cascade deletions, table check constraints, and unique compound constraints.
3. **Security & Identity Architecture:**
   - Dual identity model (customer + worker under a single human identity) is correctly preserved in both database schemas and API endpoints.
   - Bearer authentication enforces Supabase identity verification, failing closed (HTTP 503) when unconfigured or unreachable.
   - Account-takeover protections (preventing conflicting email re-registrations with different identity subjects) are enforced with HTTP 409 `IDENTITY_CONFLICT`.
   - Multi-tenant data isolation is respected: users cannot access or alter other users' profiles, worker profiles, or organizations.
4. **Integration Discrepancies & Architectural Gaps:**
   - **Repository Bypass (ARCH-01):** Priyanshu's backend services (`UserService`, `WorkerService`, `OrganizationService`) bypass Shresth's canonical repository functions (`user_repository.py`, `worker_repository.py`, `organization_repository.py`), resulting in duplicate query logic.
   - **Dead Code Modules (ARCH-02):** Unused files `app/core/auth.py` and `app/repositories/user.py` remain in the codebase.
   - **Container Dependency Desynchronization (SEC-01):** The Docker Compose API container image was built before `python-jose` was added to `pyproject.toml`, resulting in a runtime `ModuleNotFoundError` during container boot unless rebuilt.
   - **Configuration Gaps (SEC-02, INT-01):** `SUPABASE_JWT_SECRET` is missing from root `.env.example`, and `apps/web/.env.example` is missing.

### Overall Phase 2 Verdict:
**CONDITIONAL PASS — Minor fixes required.**  
The functional and security foundations are solid, verified, and contract-compliant. Addressing the identified non-breaking architectural and operational cleanups will ensure safe progression to Phase 3.

---

## 2. Repository and Branch Status

- **Default Branch:** `main`
- **Current HEAD Commit:** `29e2f5e` (`Merge pull request #5 from pr1y4nshu-cooks/dhwanitBranch`)
- **Key Commits Leading to Phase 2 Integration:**
  - `4db2fe8`: `feat(db): implement Phase 2 database schema, migrations, and repositories` (Shresth)
  - `01dc0ab`: `feat(api): implement Phase 2 auth verification and API endpoints` (Priyanshu)
  - `b29d034`: `Merge pull request #4 from pr1y4nshu-cooks/priyanshuBranch` into `main`
  - `b74dfd2`: `Merge dhwanitBranch into main: integrate frontend Phase 2 and resolve backend conflicts`
  - `5e0ecf8`: `change: status bubble update` (Dhwanit)
  - `d982480`: `chore: update gitignore`
  - `29e2f5e`: `Merge pull request #5 from pr1y4nshu-cooks/dhwanitBranch`
- **Active Branches:**
  - `main` (active local HEAD)
  - `shresthBranch`
  - `remotes/origin/main`
  - `remotes/origin/priyanshuBranch`
  - `remotes/origin/dhwanitBranch`
  - `remotes/origin/shresthBranch`
- **Working Tree Status:** Clean (`git status -s` shows no unstaged or untracked changes).

---

## 3. Documents Reviewed

| Document | Path | Purpose |
|---|---|---|
| Master Blueprint | `docs/SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md` | Core product vision, multi-sided marketplace rules, cooperative model |
| Technical Contract | `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md` | Frozen Phase 2 interface, data structures, error handling rules |
| Duplicate Contract | `docs/PHASE_2_TECHNICAL_CONTRACT.md` | Root duplicate of technical contract |
| OpenAPI Specification | `docs/contracts/phase2.openapi.yaml` | Machine-readable API specification (v1.0 Frozen) |
| Database Baseline | `docs/DATABASE_BASELINE_AND_HANDSHAKE.md` | Baseline constraints and audit checkpoints |
| Ownership Map | `docs/OWNERSHIP_MAP.md` | Team file boundaries and repository handshake agreements |
| Phase 2 Gate Report | `docs/PHASE_2_GATE_G2_REPORT.md` | Gate G2 readiness report |
| Developer Prompts | `docs/SHRESTH_DATABASE_ANTIGRAVITY_PROMPT.md`, `docs/PRIYANSHU_BACKEND_ANTIGRAVITY_PROMPT.md`, `docs/DHWANIT_FRONTEND_ANTIGRAVITY_PROMPT.md` | Developer execution prompts |
| Database Plan | `docs/plans/2026-10-27-phase2-database-implementation.md` | Shresth's database implementation plan |

---

## 4. Source-of-Truth Conflicts

1. **Duplicate Contract Files:**
   `docs/PHASE_2_TECHNICAL_CONTRACT.md` exists at both `docs/` and `docs/contracts/`. `docs/contracts/` is the canonical location referenced in `OWNERSHIP_MAP.md`.
2. **Competing Authentication Modules:**
   - `services/api/app/core/security.py`: Active implementation using `VerifiedUser` and HMAC-SHA256 / Supabase REST verification.
   - `services/api/app/core/auth.py`: Inactive legacy implementation using `SupabaseJWKS` (RS256) and class-based repository.
3. **Competing Data Access Implementations:**
   - `services/api/app/repositories/user_repository.py`, `worker_repository.py`, `organization_repository.py`: Shresth's canonical handshake implementation.
   - `services/api/app/repositories/user.py`: Priyanshu's early class-based repository.
   - `services/api/app/services/`: Direct inline SQLAlchemy queries bypassing repositories.

---

## 5. Current Implementation Inventory

```
sahakar-seva/
├── apps/
│   └── web/
│       ├── src/
│       │   ├── components/ (Button, Card, Input, Layout, StatusState)
│       │   ├── lib/ (api.ts, auth.tsx, supabase.ts)
│       │   ├── pages/ (Dashboard, Earn, Home, Login, Organizations, Placeholder, Profile, Signup)
│       │   └── App.tsx, main.tsx, index.css
│       ├── package.json, vite.config.ts, vitest.config.ts, tsconfig.json
│       └── Dockerfile
├── services/
│   └── api/
│       ├── alembic/
│       │   ├── versions/ (0001_foundation.py, 0002_phase2_constraints.py)
│       │   └── env.py, alembic.ini
│       ├── app/
│       │   ├── api/
│       │   │   ├── router.py (Aggregator)
│       │   │   └── v1/ (health.py, users.py, workers.py, organizations.py, error_handler.py)
│       │   ├── core/ (config.py, logging.py, security.py, auth.py [unused])
│       │   ├── db/ (base.py, session.py)
│       │   ├── models/ (user.py, organization.py, __init__.py)
│       │   ├── repositories/ (user_repository.py, worker_repository.py, organization_repository.py, exceptions.py, user.py [unused])
│       │   ├── schemas/ (user.py, worker.py, organization.py, error.py, __init__.py)
│       │   ├── services/ (user_service.py, worker_service.py, organization_service.py, __init__.py)
│       │   └── main.py
│       ├── tests/
│       │   ├── api/ (test_auth_security.py, test_openapi_contract.py, test_organizations.py, test_users.py, test_workers.py)
│       │   ├── db/ (test_user_repository.py, test_worker_repository.py, test_organization_repository.py, test_migration_and_integrity.py)
│       │   └── test_health.py, conftest.py
│       ├── Dockerfile, pyproject.toml
├── docs/ (contracts/, plans/, blueprints, baseline docs, audits/)
├── compose.yml, .env.example, .gitignore
```

---

## 6. Phase 2 Requirements Compliance

| Requirement | Contract Specification | Implementation Status | Evidence / Notes |
|---|---|---|---|
| **Unified User Model** | Single user account can act as customer, worker, and org member | **COMPLIANT** | `users` table acts as base; `worker_profiles` has 1-to-1 FK; `organization_memberships` allows multiple org roles. |
| **Worker Profile Creation** | Draft onboarding status, optional bio, max 500 chars | **COMPLIANT** | `POST /api/v1/worker-profiles` creates with `draft`, validates bio. Tested in `test_workers.py`. |
| **Worker Profile Retrieval** | Get own profile; 404 if not found | **COMPLIANT** | `GET /api/v1/worker-profiles/me` returns 404 before creation, 200 after. |
| **Worker Profile Modification** | Update display name, update/clear bio; cannot self-promote status | **COMPLIANT** | `PATCH /api/v1/worker-profiles/me` forbids `onboarding_status`. Verified in `test_workers.py`. |
| **Organization Tenancy** | Business & cooperative orgs with owner membership | **COMPLIANT** | `POST /api/v1/organizations` atomically creates org and owner membership. |
| **Organization Listing** | Scoped strictly to caller's memberships | **COMPLIANT** | `GET /api/v1/organizations/mine` filters by caller `user_id`. Verified in `test_organizations.py`. |
| **PostGIS Readiness** | Extension enabled in database | **COMPLIANT** | `0001_foundation` enables PostGIS; verified live via `SELECT PostGIS_Version()`. |
| **Strict Phase Boundaries** | No premature Phase 3+ features (bookings, jobs, payments) | **COMPLIANT** | Zero speculative tables or routes created; frontend disables marketplace links. |

---

## 7. API Route Comparison

Refer to [PHASE_2_ROUTE_MATRIX.md](file:///Users/shresthchauhan/Downloads/hackathons/code%20yudh/sahakar-seva/docs/audits/PHASE_2_ROUTE_MATRIX.md) for full endpoint-by-endpoint details.

- **Route Coverage:** 9 out of 9 endpoints implemented.
- **Path Prefixes:** All mounted strictly under `/api/v1`.
- **Status Codes:** Conform to the contract (`200 OK`, `201 Created`, `401 Unauthorized`, `404 Not Found`, `409 Conflict`, `422 Unprocessable Content`, `503 Service Unavailable`).
- **Error Payloads:** Normalized via `ContractCompliantRoute` to `{"error": {"code": "...", "message": "...", "details": ...}}`.

---

## 8. Authentication & Security Findings

1. **Authentication Provider:**
   - Supabase Auth is the authority. Tokens are provided as `Authorization: Bearer <token>`.
2. **Verification Modes in `security.py`:**
   - **Mode A (Cryptographic HMAC-SHA256):** When `SUPABASE_JWT_SECRET` is set, verifies signatures locally using `python-jose`, checking `alg == HS256`, `aud == "authenticated"`, and `exp`.
   - **Mode B (REST Verification):** When `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set, calls `GET {SUPABASE_URL}/auth/v1/user` via HTTP.
   - **Fail-Closed:** When neither is configured or remote calls fail, raises `HTTP 503 AUTH_NOT_CONFIGURED` or `AUTH_PROVIDER_UNAVAILABLE`.
3. **Account Takeover Prevention:**
   - Incoming identity subject (`sub`) is permanently bound to `users.external_auth_id`.
   - If a token presents an email that belongs to an existing user with a different or null `external_auth_id`, the system raises `HTTP 409 IDENTITY_CONFLICT`. Tested in `test_identity_conflict_on_email_collision`.
4. **Authorization & Tenant Isolation:**
   - Users can only fetch/update their own profile via `/me`.
   - Users cannot see or manage organizations they do not belong to.
   - Worker profile queries strictly filter by caller `user_id`.
5. **CORS Configuration:**
   - `CORSMiddleware` configured in `main.py` using `settings.allowed_origins` (`http://localhost:5173`, `http://localhost:4173`).

---

## 9. Database and Migration Findings

Refer to [PHASE_2_DATABASE_AUDIT.md](file:///Users/shresthchauhan/Downloads/hackathons/code%20yudh/sahakar-seva/docs/audits/PHASE_2_DATABASE_AUDIT.md) for table schemas and constraint definitions.

- **Schema State:** Head revision is `0002_phase2_constraints`.
- **Primary Keys:** UUID v4 across all tables.
- **Constraints:**
  - `users.email` UNIQUE
  - `users.external_auth_id` UNIQUE
  - `worker_profiles.user_id` UNIQUE (enforces 1-to-1)
  - `organization_memberships` UNIQUE (`organization_id`, `user_id`)
  - Check constraints for worker onboarding status, organization type, and membership roles.
- **Transaction Atomicity:**
  - Creating an organization and owner membership occurs inside a single database transaction. Tested via negative test hook in `test_organization_transaction_atomicity`.
- **Referential Integrity:**
  - `ON DELETE CASCADE` configured on all foreign keys.

---

## 10. Backend/Database Integration Findings

### The Handshake Discrepancy (ARCH-01):
In `docs/OWNERSHIP_MAP.md`, Shresth and Priyanshu agreed upon a repository handshake interface. Shresth implemented and tested these in `app.repositories.*`.
However, Priyanshu's service classes (`UserService`, `WorkerService`, `OrganizationService`) re-implemented the query logic using inline SQLAlchemy queries rather than calling the repository layer.
- **Impact:** While all tests pass because the services execute valid SQL against the same models, having duplicate logic defeats the purpose of the repository layer abstraction and creates maintainability debt.
- **Resolution:** Refactor services to call Shresth's repository functions.

---

## 11. Frontend Integration Readiness

- **Status:** Dhwanit's frontend implementation in `apps/web/` is substantially complete for Phase 2.
- **API Client:** `apps/web/src/lib/api.ts` cleanly wraps all 9 endpoints with typed responses matching the backend Pydantic models.
- **Auth Provider:** `apps/web/src/lib/auth.tsx` provides Supabase session tracking, sign-in, and sign-up.
- **Pages Implemented:**
  - `Home.tsx`: Hero section, service cards, CTA buttons.
  - `Dashboard.tsx`: Account overview, worker profile status, organization list, quick links.
  - `Profile.tsx`: Display name update calling `PATCH /api/v1/users/me`.
  - `Earn.tsx`: Worker profile onboarding (draft creation, bio editing).
  - `Organizations.tsx`: Creation of businesses and cooperatives, membership listing.
  - `Login.tsx`, `Signup.tsx`: Supabase authentication forms.
- **Phase Boundary Discipline:** Marketplace actions (hiring workers, posting jobs) are styled as disabled cards with "Soon" badges and clear Phase 2 informational banners.
- **Missing Asset:** `apps/web/.env.example` must be added.

---

## 12. Runtime and Test Results

### 12.1 Backend & Database Test Suite
Command: `services/api/.venv/bin/pytest services/api/tests/`
```
============================= test session starts ==============================
rootdir: /Users/shresthchauhan/Downloads/hackathons/code yudh/sahakar-seva/services/api
configfile: pyproject.toml
testpaths: tests
collected 44 items

tests/test_health.py ..                                                  [  4%]
tests/api/test_auth_security.py ......                                   [ 18%]
tests/api/test_openapi_contract.py .                                     [ 20%]
tests/api/test_organizations.py ...                                     [ 27%]
tests/api/test_users.py ......                                          [ 40%]
tests/api/test_workers.py ..                                            [ 45%]
tests/db/test_migration_and_integrity.py ......                         [ 59%]
tests/db/test_organization_repository.py .........                      [ 79%]
tests/db/test_user_repository.py .........                              [100%]

======================== 44 passed, 6 warnings in 0.38s ========================
```

### 12.2 Frontend Test Suite & Typecheck
Command: `npm run test && npm run typecheck` in `apps/web/`
```
 RUN  v2.1.9 /Users/shresthchauhan/Downloads/hackathons/code yudh/sahakar-seva/apps/web

 ✓ src/App.test.tsx (3 tests)

 Test Files  1 passed (1)
      Tests  3 passed (3)
   Duration  863ms

> tsc -b --pretty false
(0 errors)
```

### 12.3 Docker Container Verification
- `sahakar-seva-db-1`: PostgreSQL 16 + PostGIS 3.4 **Up & Healthy** on port 55432.
- `sahakar-seva-web-1`: Node 22 Vite dev server **Up** on port 5173.
- `sahakar-seva-api-1`: Required rebuild (`docker compose build api`) due to `python-jose` dependency addition.

---

## 13. Long-Term Product Compatibility (Step 12 Evaluation)

The foundation was evaluated against the 15 roadmap requirements of SAHAKAR–SEVA:

| Roadmap Capability | Architectural Classification | Architectural Rationale |
|---|---|---|
| **1. Customer & worker under one identity** | **Supported by existing architecture** | `users` is the master identity; `worker_profiles` is an optional 1-to-1 extension. |
| **2. Individual worker discovery** | **Supported with ordinary future extension** | Worker profile table exists; needs discovery indexes/endpoints in Phase 3. |
| **3. Skills and service categories** | **Supported with ordinary future extension** | Requires category and worker-skill junction tables in Phase 3. |
| **4. Worker availability** | **Supported with ordinary future extension** | Requires calendar/schedule table linked to `worker_profiles.id`. |
| **5. Geographical radius via PostGIS** | **Supported by existing architecture** | PostGIS is active in Postgres; future migrations can add `geometry(Point, 4326)` columns and spatial GIST indexes. |
| **6. Direct hiring** | **Supported with ordinary future extension** | Requires booking entity linking customer `user_id` to worker `worker_profile_id`. |
| **7. Customer job posting** | **Supported with ordinary future extension** | Requires `jobs` table with owner `user_id` and location geometry. |
| **8. Worker applications** | **Supported with ordinary future extension** | Requires `job_applications` table linking `job_id` and `worker_profile_id`. |
| **9. Shared booking lifecycle** | **Supported with ordinary future extension** | Modular monolith state machine can be built on standard relational tables. |
| **10. Transparent pricing** | **Supported with ordinary future extension** | Pricing rules and quote entities can be attached to bookings/jobs. |
| **11. Simulated & provider payment records** | **Supported with ordinary future extension** | Payment ledger tables can record status without changing identity models. |
| **12. Complaints & human review** | **Supported with ordinary future extension** | Dispute tickets can link to bookings and users. |
| **13. Business accounts** | **Supported by existing architecture** | `organizations` table has `organization_type = 'business'`. |
| **14. Cooperative memberships** | **Supported by existing architecture** | `organizations` has `organization_type = 'cooperative'` and role-based memberships. |
| **15. Worker-protective policies** | **Supported with ordinary future extension** | Schema supports cooperative governance and worker onboarding verification. |

**Assessment Summary:** Zero items require significant redesign. Zero items are blocked. The modular monolith foundation cleanly supports the roadmap.

---

## 14. Risks & Discrepancy Register

| Issue ID | Title | Severity | Location | Expected | Actual | Owner | Phase 2 Blocker? |
|---|---|---|---|---|---|---|---|
| **SEC-01** | Docker API image missing `python-jose` | **HIGH** | `compose.yml`, `Dockerfile` | Container starts cleanly | Container crashes on `import jose` unless rebuilt | Shresth / Priyanshu | No (Local dev image rebuild resolves) |
| **ARCH-01** | Services bypass canonical repositories | **MEDIUM** | `app/services/`, `app/repositories/` | Services call repository functions | Services use inline queries | Priyanshu | No (Non-breaking internal refactor) |
| **ARCH-02** | Dead code modules (`auth.py`, `user.py`) | **MEDIUM** | `app/core/auth.py`, `app/repositories/user.py` | Single clean auth & repo structure | Unused duplicate files present | Priyanshu | No |
| **SEC-02** | Missing `SUPABASE_JWT_SECRET` in `.env.example` | **MEDIUM** | `.env.example` | Documented secret for Mode A | Missing from example file | Priyanshu | No |
| **INT-01** | Missing `apps/web/.env.example` | **LOW** | `apps/web/.env.example` | Frontend example env committed | Missing | Dhwanit | No |
| **DOC-01** | OpenAPI decorators omit error responses | **LOW** | `app/api/v1/*.py` | Decorator declares 401/404/409/422/503 | Only 200/201 declared | Priyanshu | No |
| **CODE-01**| `allowed_origins` mutated in `get_settings` | **LOW** | `app/core/config.py` | Parsed via Pydantic validator | Mutated from str to list | Shresth / Priyanshu | No |

---

## 15. Remediation Recommendations

1. **Immediate Pre-Phase 3 Cleanup:**
   - Execute `docker compose build api` to refresh the container image.
   - Refactor `UserService`, `WorkerService`, and `OrganizationService` to call `app.repositories.*`.
   - Delete obsolete `app/core/auth.py` and `app/repositories/user.py`.
   - Add `SUPABASE_JWT_SECRET=` to `.env.example`.
   - Commit `apps/web/.env.example`.
2. **Phase 3 Preparation:**
   - Define Category and Skill tables with Alembic revision `0003_skills_and_categories`.
   - Define PostGIS point columns for worker location and customer job sites.

---

## 16. Final Acceptance Verdict

### **CONDITIONAL PASS — Minor fixes required**

**Rationale:**  
The Phase 2 implementation of SAHAKAR–SEVA is architecturally sound, adheres strictly to the approved Phase 2 contract, passes all 44 backend/database automated tests and all frontend tests, maintains strict tenant isolation, and provides a robust foundation for Phase 3. The issues identified do not compromise database integrity, security, or contract compliance, but represent technical debt and container environment configuration that should be cleaned up according to [PHASE_2_FIX_PRIORITY.md](file:///Users/shresthchauhan/Downloads/hackathons/code%20yudh/sahakar-seva/docs/audits/PHASE_2_FIX_PRIORITY.md).
