# SAHAKAR–SEVA — Full-Stack Integration Audit

**Audit date:** 2026-10-27
**Branch:** `shresthBranch` @ `90c52df` (working tree had uncommitted Phase 3A changes at audit start; preserved throughout, not committed)
**Method:** Live repository inspection, live Docker containers, live Postgres queries, full backend/frontend test execution, source-code reading (no claims taken on faith from prior reports).

---

## 1. Summary

No P0 (security/data-corruption/auth-bypass) defects were found. One P1 defect was found and fixed: the running development database was one migration behind the migration code in the repository. All previously-known P2/P3 items from the Phase 2 remediation report were re-verified and remain either fixed or correctly deferred pending a product/contract decision. One new P3 cosmetic item was found in the frontend placeholder pages.

| Severity | Count | Status |
|---|---|---|
| P0 | 0 | — |
| P1 | 1 | Fixed and verified |
| P2 | 2 | Documented, awaiting contract/owner decision (not touched — frozen contract / owner-only files) |
| P3 | 4 | Documented, cosmetic, left as-is per "minimal focused correction" rule |

---

## 2. Findings

### P1 — INT-02: Development database behind migration head

- **File/location:** Running `sahakar-seva-db-1` container, table `alembic_version`.
- **Root cause:** Shresth's Phase 3A migration (`services/api/alembic/versions/0003_skills_and_categories.py`) and supporting code (`app/db/seed.py`, `app/models/service_taxonomy.py`, `app/repositories/service_taxonomy_repository.py`) exist as uncommitted/untracked files in the working tree. The running `api` container had been started before this migration existed, so the dev database was still at `0002_phase2_constraints` while the code on disk declared `0003_skills_and_categories` as head.
- **Impact:** Any code path that imported `app.models.service_taxonomy` or queried the new tables would fail at runtime against the dev database (`relation "service_categories" does not exist"`). The DB test suite was unaffected because it runs against a separately-migrated isolated test database.
- **Correction:** Ran `docker compose exec api alembic upgrade head`. Verified the migration is additive-only by reading its source (explicit docstring: "Additive only... Existing users, worker_profiles, organizations and organization_memberships are not altered") before running it.
- **Validation:**
  - `docker compose exec api alembic current` → `0003_skills_and_categories (head)`.
  - Dev data row counts identical before/after: `users=389, worker_profiles=92, organizations=88, organization_memberships=88`.
  - Full backend test suite re-run after migration: `119 passed, 0 failed`.
  - Also ran `python -m app.db.seed` (documented in README as the normal post-migration step; insert-only, idempotent, verified via `--dry-run` first). Result: 3 categories, 6 skills inserted, matching `PHASE_3A_DATA_CONTRACT.md` §6 exactly.
- **Remaining blocker:** None. Resolved.

### P2 — Pre-existing, not touched (frozen contract / owner decision required)

1. **`GET /api/v1/health/db` 503 response body wraps the payload in a `detail` key** (`{"detail": {"status": "error", ...}}`) instead of the contract's flat shape. This was first flagged in the Phase 2 remediation report and is unchanged. The Phase 1 health-check behavior is pinned by existing tests, and `docs/contracts/phase2.openapi.yaml` is frozen — correcting this requires an explicit decision from Priyanshu (contract owner), not a unilateral fix during an audit.
2. **`services/api/requirements.txt` is stale** (missing `python-jose`, `cryptography`) and unused — `pyproject.toml` is the real install source for both the Dockerfile and local dev. Flagged in the remediation report as an owner (Shresth) decision to either regenerate or delete; left unchanged.

### P3 — Cosmetic, documented, not blocking

1. **`Hire.tsx` / `FindWork.tsx` hardcoded fake counts.** "12 workers found" and "24 jobs posted this week" are static strings with no backing data — they could be mistaken by a user for real marketplace activity. Recommend relabeling as "Preview" / removing the numbers once these screens are wired to real Phase 3B endpoints. Not fixed in this audit because it is UI copy on an already-approved placeholder, not a defect in implemented functionality, and changing copy on another developer's in-progress UI work falls outside "minimal, focused correction" for this audit.
2. **Duplicate contract file**: `docs/PHASE_2_TECHNICAL_CONTRACT.md` (root) vs `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md` (canonical, per `OWNERSHIP_MAP.md`). Unchanged since Phase 2 audit; cosmetic.
3. **Stray empty tracked file** at repo root: `change: status bubble update` (artifact of commit `5e0ecf8`). Harmless but should be `git rm`'d by its owner (Dhwanit) in a future cleanup commit.
4. **530 KB frontend JS chunk** exceeds Vite's 500 KB warning threshold. Documented as pre-existing in the Phase 2 remediation report; purely a future code-splitting opportunity, not a functional defect.

---

## 3. Re-verified historical fixes (Phase 2 remediation, confirmed still holding)

| ID | Claim | Verification performed this audit |
|---|---|---|
| SEC-01 | `python-jose` importable, container builds and starts | `docker compose ps` shows `api` Up, `RestartCount=0`; health endpoints 200 |
| SEC-02 | `SUPABASE_JWT_SECRET` documented in `.env.example` | Confirmed present (blank) with Mode A/B documentation |
| ARCH-01 | Services delegate to repositories, no inline SQL | Read `user_service.py`, `worker_service.py`, `organization_service.py` directly — all three call `app.repositories.*` exclusively |
| ARCH-02 | Dead code removed | `app/core/auth.py` and `app/repositories/user.py` confirmed absent |
| INT-01 | `apps/web/.env.example` exists | Confirmed present with 3 documented `VITE_*` vars |
| DOC-01 | OpenAPI declares error responses | Not re-verified byte-for-byte in this audit (no contract change occurred); prior test suite covering this (`test_openapi_contract.py`) still passes |
| CODE-01 | `allowed_origins` parsed via validator, not mutated | Config file unchanged since remediation; not re-read line-by-line this audit, but config-dependent tests (`tests/test_config.py`) pass |

---

## 4. Database test isolation — verified safe, not just claimed

This was Phase 2 remediation's unresolved issue #1. Verified end-to-end in this audit:

1. Recorded dev DB baseline: `users=389, worker_profiles=92, organizations=88, organization_memberships=88`.
2. Ran `sh services/api/scripts/create_test_database.sh` — idempotent, created `sahakar_test` role and `sahakar_seva_test` database, did not touch the dev database or its Docker volume.
3. Ran the full test suite with `TEST_DATABASE_URL` pointed at the isolated database: **119 passed, 0 failed.**
4. Re-checked dev DB row counts: **identical to baseline.**
5. Read `app/db/testing.py`: `assert_safe_test_database_url()` rejects a missing URL, a non-PostgreSQL URL, a database name without `"test"`, and any URL whose normalized `host:port:database` matches a protected (dev/prod) URL — including the `127.0.0.1`/`localhost` alias case.
6. Read `tests/db/conftest.py`: every test runs inside an outer transaction with `join_transaction_mode="create_savepoint"`, so repository `commit()` calls only release a SAVEPOINT; the outer transaction is always rolled back. A session-scoped fixture also diffs row counts across all seven tracked tables before/after the whole suite and fails the run if anything leaked.

**Conclusion:** the isolation mechanism is real, tested, and verified non-destructive against live dev data — not merely documented.

---

## 5. Tests executed and results

| Suite | Command | Result |
|---|---|---|
| Backend (all) | `TEST_DATABASE_URL=... pytest tests/` | 119 passed, 0 failed, 8 pre-existing deprecation warnings |
| Frontend unit | `npm run test -- --run` | 24 passed (2 files) |
| Frontend typecheck | `npm run typecheck` | 0 errors |
| Frontend build | `npm run build` | Success, 1.37s, 530 KB chunk warning (cosmetic) |
| Docker | `docker compose ps` / `docker inspect` | All 3 containers Up, `RestartCount=0` |
| Live endpoints | `curl` against health, health/db, users/me | 200 / 200 / 401 `AUTH_REQUIRED` as expected |

---

## 6. Remaining blockers (real defects vs. missing future features)

**Real defects remaining:** none identified beyond the P2 items above, both of which require an owner/product decision rather than a unilateral code change.

**Missing future features (not defects):** worker discovery, bookings, job postings, skills API routes, payments, reviews, disputes, notifications, cooperative governance tooling. These are correctly out of scope for the current phase and are not counted as integration defects.

**Environmental limitation (not a code defect):** live Supabase authentication cannot be exercised locally because `.env` has no Supabase credentials. This has been true historically and remains true; the system correctly fails closed (503 `AUTH_NOT_CONFIGURED`) rather than allowing an insecure fallback.
