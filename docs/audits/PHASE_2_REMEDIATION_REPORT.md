# SAHAKAR–SEVA — Phase 2 Remediation Report

**Date:** 2026-10-27
**Branch:** `fix/phase2-audit-remediation` (created from `main` @ `29e2f5e`)
**Commit:** none created. Changes are left uncommitted for owner review.
**Verdict:** **CONDITIONAL PASS — Ready for Phase 3 once the bounded items in §14 are acknowledged**

---

## 1. Executive summary

I re-checked all seven audit findings against the source and the running environment. Six were still present, and SEC-01 was actively breaking the API: the running container was in a `ModuleNotFoundError: No module named 'jose'` reload failure, and `curl -m 5` to both health endpoints timed out. All seven are now fixed and covered by regression tests:

- **Backend tests:** 75 pass on the host (baseline was 44). In the container, 73 pass and 2 are skipped because the contract file isn't mounted there.
- **Frontend:** 3 tests pass, typecheck is clean, and the production build passes.
- **Docker:** the rebuilt API image starts with 0 restarts and both health endpoints return 200.
- **Database and contract:** the database is still at `0002_phase2_constraints`. The migrations and frozen contracts were not touched.

Live browser → Supabase → FastAPI authentication is **BLOCKED**. No Supabase credentials are configured in `.env` (all three keys are empty).

## 2. Repository baseline

| Item | Observed |
|---|---|
| Start branch / HEAD | `main` @ `29e2f5e` (matches the audit) |
| Working tree at start | Clean apart from untracked `docs/audits/` (the audit reports) |
| Unmerged teammate work | `origin/priyanshuBranch` has one extra commit (`da2629f`), which only adds a trailing newline to `tests/db/conftest.py`. No other branch is ahead of `main`. No conflicting parallel work was found. |
| Stray tracked file | `change: status bubble update` (empty file at the repo root, from commit `5e0ecf8`). Reported only, not removed. |

## 3. Documents reviewed

`docs/SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md`, `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md`, `docs/contracts/phase2.openapi.yaml`, `docs/OWNERSHIP_MAP.md`, `docs/DATABASE_BASELINE_AND_HANDSHAKE.md`, `docs/PHASE_2_GATE_G2_REPORT.md`, `docs/architecture.md`, `docs/api-contracts.md`, and all five `docs/audits/*` reports.

**Duplicate contract:** `docs/PHASE_2_TECHNICAL_CONTRACT.md` differs from `docs/contracts/…` only in the sign-off line, which is blank in the root copy. The `docs/contracts/` copy is canonical, per OWNERSHIP_MAP. Neither copy was modified.

## 4–5. Audit findings and re-verification

| ID | Re-verification evidence | Status before fix |
|---|---|---|
| SEC-01 | `docker compose logs api` showed `ModuleNotFoundError: No module named 'jose'`; health curls timed out (rc=28) | Confirmed, unresolved (actively broken) |
| SEC-02 | `.env.example` had no `SUPABASE_JWT_SECRET`; `security.py` read it via `os.getenv` only, so a value in `.env` was ignored by local runs, and Compose never passed it to the container | Confirmed, plus a related config gap |
| ARCH-01 | All three services used inline `select()`/`commit()` and never imported `app.repositories` | Confirmed |
| ARCH-02 | `grep` found no imports of `app.core.auth` or `app.repositories.user` in app, tests, or alembic | Confirmed (dead code) |
| INT-01 | `apps/web/.env.example` was absent; the source uses exactly `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Confirmed |
| DOC-01 | Generated OpenAPI listed only 200/201 (+ FastAPI's default 422 `HTTPValidationError`, which does not match the runtime envelope) | Confirmed |
| CODE-01 | `allowed_origins: str` was mutated into a `list` inside `get_settings()` | Confirmed |

## 6–8. Changes implemented (files, owners, reasons)

| File | Owner | Change and reason |
|---|---|---|
| `services/api/app/core/config.py` | Shresth (shared) | **CODE-01:** `allowed_origins: Annotated[list[str], NoDecode]` with a `mode="before"` validator. It parses the comma-separated value, trims whitespace, drops empty segments, rejects empty config, and rejects `*` (credentials are allowed). `get_settings()` no longer mutates anything. **SEC-02:** adds `supabase_jwt_secret: str \| None`. |
| `services/api/pyproject.toml` | Shresth (shared) | `pydantic-settings>=2.7` (the minimum that provides `NoDecode`; installed version is 2.16.1). |
| `services/api/app/core/security.py` | Priyanshu | One line: the JWT secret is now `os.getenv(...) or settings.supabase_jwt_secret`. Verification logic, algorithms, and fail-closed behaviour are unchanged. |
| `.env.example` | Shresth (shared) | **SEC-02:** blank `SUPABASE_JWT_SECRET=` plus comments documenting Mode A (HS256, legacy only) vs Mode B (`/auth/v1/user`), precedence, and fail-closed behaviour. |
| `compose.yml` | Shresth | Passes `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` (default blank) to `api`. Without this, the container could never verify tokens. |
| `apps/web/.env.example` (new) | Dhwanit | **INT-01:** the three `VITE_*` variables, with a warning against service-role/secret keys. |
| `services/api/app/services/{user,worker,organization}_service.py` | Priyanshu | **ARCH-01:** these now delegate to `user_repository`, `worker_repository`, and `organization_repository`, and translate repository exceptions into the existing HTTP exceptions (`IDENTITY_CONFLICT`, `WORKER_PROFILE_EXISTS`, `RESOURCE_NOT_FOUND`). Public method names and return shapes are unchanged, so routes needed no logic changes. The test-only `_membership_failure_hook` parameter was removed; the failure is now injected in the test instead. |
| `services/api/app/core/auth.py`, `services/api/app/repositories/user.py` | Priyanshu | **ARCH-02:** deleted (`git rm`) after the reference check. |
| `services/api/app/api/v1/responses.py` (new), `users.py`, `workers.py`, `organizations.py` | Priyanshu | **DOC-01:** each decorator now has `responses=error_responses(...)` using `ErrorResponse`, with exactly the codes from the frozen contract. This is documentation only; runtime behaviour is unchanged. |
| `services/api/Dockerfile` | Shresth | **SEC-01:** a build-time `RUN python -c "import …, jose"`, so a missing dependency fails `docker compose build` instead of crashing the container at runtime. |
| `services/api/.dockerignore` (new) | Shresth | Keeps `.venv`, caches, `*.egg-info`, and `.env*` out of the build context and image. |
| `README.md` | Shresth (shared) | Documents the auth modes, the frontend env file, and the rebuild-after-dependency-change step. |
| `services/api/tests/api/conftest.py` | Priyanshu | The SQLite fixture now uses SQLAlchemy's documented pysqlite SAVEPOINT recipe and `join_transaction_mode="create_savepoint"`. **Why:** the repositories use `begin_nested()` + `commit()`, and under pysqlite's default transaction handling those commits leaked across tests (this showed up as a false 409 in `test_users_isolation_two_different_subjects`). The fixture now isolates tests the same way PostgreSQL does. |
| `tests/api/test_organizations.py` | Priyanshu | The atomicity test now injects the failure inside the repository (the real code path). Added an API-level rollback test. |
| `tests/api/test_openapi_contract.py` | Priyanshu | Added DOC-01 tests (error codes match the contract, `ErrorResponse` envelope, success schemas unchanged, runtime 401 payload validates). The contract file is now located by walking up parent directories, and the tests skip when it is absent (inside the container). |
| `tests/test_config.py` (new), `tests/api/test_auth_config.py` (new), `tests/api/test_service_repository_integration.py` (new) | Priyanshu / Shresth | Regression tests for CODE-01, SEC-02, and ARCH-01 (see §11). |

**Not modified:** `alembic/**` (verified with `git diff --quiet HEAD -- services/api/alembic`), `app/models/**`, `app/repositories/**`, `app/schemas/**`, `app/main.py`, `docs/contracts/**`, all frontend source, and the original audit reports.

**Behavioural notes from ARCH-01:** these come from the canonical repositories and are deliberate.

- Emails are stored lowercase and trimmed, and the collision check is now case-insensitive. That is stricter against account takeover. Existing users are still matched by `external_auth_id` first.
- A bio that is only whitespace is stored as `null`.

No API field, status code, or error code changed.

## 9. API route compatibility

All 9 routes are registered with unchanged paths and methods. Generated OpenAPI (live `curl -m 5 localhost:8000/openapi.json`):

```
GET   /api/v1/health               ['200']
GET   /api/v1/health/db            ['200']
GET   /api/v1/users/me             ['200','401','409','503']
PATCH /api/v1/users/me             ['200','401','422','503']
POST  /api/v1/worker-profiles      ['201','401','409','422','503']
GET   /api/v1/worker-profiles/me   ['200','401','404','503']
PATCH /api/v1/worker-profiles/me   ['200','401','404','422','503']
POST  /api/v1/organizations        ['201','401','422','503']
GET   /api/v1/organizations/mine   ['200','401','503']
```

These match the frozen `phase2.openapi.yaml` for every protected route. This is enforced by `test_protected_routes_document_contract_error_responses`.

**Pre-existing discrepancy, not changed:** on failure, `GET /health/db` returns `{"detail":{"status":"error","database":"unavailable"}}`. The contract specifies `{"status":"error","database":"unavailable"}` with no `detail` wrapper, and the 503 is not declared in the generated OpenAPI. The Phase 1 behaviour is pinned by `tests/test_health.py`, and the contract says to keep health behaviour unchanged. Fixing it needs an approved contract decision (Priyanshu).

## 10. Database compatibility

| Check | Result |
|---|---|
| `alembic current` / `alembic heads` (container) | `0002_phase2_constraints (head)` for both |
| `alembic_version` table | `0002_phase2_constraints` |
| Server / PostGIS | PostgreSQL 16.4 / PostGIS 3.4.3 |
| Constraints present | `ck_worker_profiles_onboarding_status`, `ck_organizations_organization_type`, `ck_organization_memberships_role`, `uq_organization_membership`, `users_email_key`, `users_external_auth_id_key`, `worker_profiles_user_id_key`, plus FKs/PKs |
| Volume | `sahakar_seva_postgres_data` preserved; only the `api` container was recreated (`--no-deps`) |

## 11. Security regression results

| Check | Evidence | Result |
|---|---|---|
| Missing token → 401 `AUTH_REQUIRED` | live curl + tests | PASS |
| All 7 protected routes without a token → 401 | live curl loop | PASS |
| No verifier configured → 503 `AUTH_NOT_CONFIGURED` (fail closed) | live curl + `test_missing_verification_configuration_fails_closed` | PASS |
| Forged signature / expired / wrong audience → 401 | container E2E smoke (real HS256, real Postgres) + unit tests | PASS |
| `alg: none` unsigned token → 401 | `test_unsigned_alg_none_token_is_rejected` | PASS |
| Identity takeover (same email, new `sub`) → 409; original binding unchanged; email not echoed | E2E smoke + `test_identity_conflict_does_not_leak_email` | PASS |
| Repeated `/users/me` → exactly one user row | E2E (DB count = 1) + test | PASS |
| Duplicate worker profile → 409, still one row | E2E + test | PASS |
| Self-approval / `user_id` / `is_admin` / `role` in body → 422, no change; status stays `draft` | E2E + tests | PASS |
| User B cannot read or modify A's worker profile or see A's orgs | E2E + tests | PASS |
| Org + owner membership atomic; injected failure → 500 `INTERNAL_ERROR`, zero rows | repository + API-level tests | PASS |
| CORS: allowed origin echoed; foreign origin denied; `*` rejected at config | live preflight (200 / 400) + tests | PASS |
| Secrets in diff / tracked `.env` | diff scan; `git ls-files` | None |
| Secrets in frontend bundle | `dist` only contains the Supabase SDK's literal `sb_secret_` prefix check (library code), no key values | PASS |
| Live Supabase browser → FastAPI flow | No credentials configured | **BLOCKED** |

E2E smoke data was created only under the `@remediation.test` email domain and was deleted afterwards in a single transaction (verified count = 0).

## 12. Docker verification

- `docker compose build api`: success. The build-time import check (including `jose`) passed.
- `docker compose up -d --no-deps --force-recreate api`: `Up`, `RestartCount=0`.
- `python -c "import jose"` in the container: `python-jose 3.5.0`.
- `/api/v1/health` returned `{"status":"ok","service":"api"}` and `/api/v1/health/db` returned `{"status":"ok","database":"connected"}`.
- The web container (`:5173`) answered 200. The DB container was healthy and was not restarted.

## 13. Test results

| Command | Result |
|---|---|
| `services/api/.venv/bin/pytest services/api/tests/` (baseline, before changes) | 44 passed |
| same, after remediation | **75 passed**, 8 warnings, 0 failed |
| `docker compose exec -T api python -m pytest tests/` | 73 passed, 2 skipped (contract YAML not mounted in container), 0 failed |
| `npm run test` (apps/web) | 3 passed |
| `npm run typecheck` | 0 errors |
| `npm run build` | built in 1.21 s (JS chunk 499 kB, just under Vite's 500 kB warning) |

The 8 warnings are all deprecations: Starlette's `httpx` TestClient notice, and `HTTP_422_UNPROCESSABLE_ENTITY` used in `error_handler.py:38`. No warning is hidden by a filter.

## 14. Unresolved issues (confirmed)

1. **DB integration tests pollute the dev database (pre-existing, Shresth).** `tests/db/*` use `SessionLocal` against `DATABASE_URL`, and the repositories `commit()`, so every run leaves rows behind. Users went from 304 to 338 during this session. That is acceptable for local dev but unsafe against any shared DB. **Recommended fix:** point `TEST_DATABASE_URL` at a dedicated test database, or use a savepoint fixture.
2. **`/health/db` 503 body shape vs contract** (§9). Needs a contract decision.
3. **`services/api/requirements.txt` is stale.** It lacks `python-jose` and `cryptography`. It is not used by the Dockerfile or the docs (`pyproject.toml` is the install source), so it was left unchanged rather than regenerated with unreviewed version pins. Shresth should either regenerate it or delete it.
4. **Asymmetric (RS256/ES256 JWKS) local verification is not supported.** The deleted `auth.py` attempted it but was unused and had defects (an async JWKS fetch, `jwt.algorithms.RSAAlgorithm`, which does not exist in python-jose). Projects with asymmetric signing keys are still supported securely through Mode B (server-side `get_user`). Adding JWKS verification is a future enhancement, not a Phase 2 defect.
5. Deprecation cleanup (`HTTP_422_UNPROCESSABLE_CONTENT`), the stray root file `change: status bubble update`, and the duplicate root contract copy are cosmetic and left for their owners.

## 15. Environmental limitations

- No Supabase project credentials, so live provider auth and signup email confirmation could not be exercised (**BLOCKED**).
- The host venv runs Python 3.13 and the container runs 3.12 (`requires-python>=3.12`). Both pass.
- The API container mounts only `services/api`, so contract-YAML tests skip there and are enforced by the host run.

## 16. Phase 3 readiness

The architecture is ready. `users` is a single identity, `worker_profiles` is an optional 1:1 extension, and organizations have scoped roles. PostGIS 3.4 is enabled, the service → repository → model layering is now consistent, and there is one auth path. These Phase 3 items need design decisions, not rework:

- Location columns and a privacy model for worker service areas and job sites (approximate vs exact, GIST indexes).
- Category/skill tables, and an eligibility model separate from `onboarding_status`.
- A shared booking state machine fed by both direct-hire and job-application funnels.
- A test-database isolation strategy (item 14.1) before adding transactional booking tests.

No Phase 3 code, tables, migrations, or routes were created.
