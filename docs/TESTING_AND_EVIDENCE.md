# Testing and Evidence

Results executed during the final hardening pass. Figures are from this machine against the working
tree at commit `947a5a6` (`shresthBranch`) **plus the uncommitted trust/pricing/demo work**. Anything
not run in this pass is marked **NOT TESTED** or **BLOCKED**; nothing here is reused from historical
reports.

## Environment

| Item | Value |
|---|---|
| OS | macOS (Darwin), Docker Desktop running |
| Python | 3.13 venv at `services/api/.venv` (project requires ≥ 3.12) |
| Node | v22.22.2 |
| Database | `postgis/postgis:16-3.4` via Docker Compose, host port `55432` |
| Isolated test DB | `sahakar_seva_test` (role `sahakar_test`), created by `services/api/scripts/create_test_database.sh` |
| Alembic head | `0007_demo_provenance` (applied by the test harness) |

## Backend — pytest

Commands:

```bash
cd services/api
# non-database subset (SQLite / pure):
.venv/bin/python -m pytest tests/api tests/test_health.py tests/test_config.py \
  tests/test_dev_auth.py tests/test_pricing_engine.py tests/test_trust_crypto.py \
  tests/test_trust_timestamping.py -q
# full suite against the isolated PostGIS test DB:
export TEST_DATABASE_URL=postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test
.venv/bin/python -m pytest
```

| Run | Result |
|---|---|
| Non-database subset | **182 passed** |
| Full suite (isolated PostGIS test DB) | **335 passed, 0 failed, 17 warnings** in ~33 s |

The 17 warnings are deprecation notices (Starlette TestClient httpx, `HTTP_422_UNPROCESSABLE_ENTITY`)
and SQLAlchemy's inability to introspect the PostGIS `geography` type during one metadata-diff check.
None indicate a failure.

Coverage of the ledger/evidence claims includes: `tests/test_trust_crypto.py` (hashing, Merkle,
inclusion proofs), `tests/db/test_trust_ledger.py` (balanced ledger + adversarial tampering),
`tests/db/test_trust_concurrency.py`, `tests/db/test_booking_concurrency.py` (overlap prevention),
`tests/db/test_fee_policies.py` + `tests/test_pricing_engine.py` (pricing), and
`tests/db/test_demo_seed.py` (synthetic dataset safety).

## Test database isolation — verified

`tests/db/conftest.py` + `app/db/testing.py` refuse any `TEST_DATABASE_URL` whose database name lacks
`test` or that equals `DATABASE_URL`, connect only to a database whose name contains `test`, wrap every
test in an outer transaction that is always rolled back, and fail the session if any row leaks. The
development database and its volume are never touched.

## Frontend — typecheck, tests, build

```bash
cd apps/web
npm run typecheck     # tsc -b --pretty false
npx vitest run
npm run build         # tsc -b && vite build
```

| Check | Result |
|---|---|
| `typecheck` | **Clean** (no type errors) |
| `vitest` | **68 passed** across 5 files |
| `build` | **Success** — vite v6.4.5, 1722 modules, `dist/` emitted (JS bundle ~689 kB / ~190 kB gzip) |

Note: the build warns that a chunk exceeds 500 kB (no code-splitting). This is a performance
observation, not a failure.

## Docker / migrations

- `docker compose up -d db` → PostGIS healthy.
- Test DB created idempotently; migrations applied to head `0007` by the harness.
- API container startup command applies `alembic upgrade head` before serving (compose.yml).

## Cryptographic verification and tamper rejection

- Verified: event-chain hashing, Merkle checkpoint roots, and RFC 9162 inclusion proofs recompute
  (`tests/test_trust_crypto.py`).
- Verified: adversarial edits to events/checkpoints/ledger are detected by `app/trust/integrity.py`
  (`tests/db/test_trust_ledger.py`); the offline verifier path is exercised by `tests/verifier_path.py`.
- The RFC 3161 timestamping logic is tested with a **test double** TSA (`tests/tsa_double.py`,
  `tests/test_trust_timestamping.py`), including signature/nonce/pinned-CA checks.

## Not tested in this pass (honest status)

| Item | Status | Why / how to run |
|---|---|---|
| Browser end-to-end flows | **NOT TESTED** | `scripts/browser_e2e.cjs`, `scripts/trust_browser_e2e.cjs`, `scripts/judge_demo_e2e.cjs`, `scripts/e2e_demo.py` exist and are documented in the runbooks; not executed here |
| Live Supabase login | **NOT TESTED** | The suite exercises `dev-auth` only; a dev-auth pass is **not** evidence that live Supabase login works |
| Live external TSA (real DigiCert network call) | **NOT TESTED** | Verified only against the test double. Configure `TSA_URL`+`TSA_CA_FILE` and run the anchor worker to exercise the real path |
| Test coverage percentage | **NOT MEASURED** | No coverage tool was run |
| GitHub-hosted CI | **NOT RUN ON GITHUB** | `.github/workflows/ci.yml` was added this pass but has not executed on GitHub Actions; its backend job mirrors the local commands above |

## Reproducing

All backend/frontend commands above are copy-pasteable. The CI workflow
(`.github/workflows/ci.yml`) runs the frontend checks and the backend suite against an ephemeral
PostGIS service, using the same isolated-test-DB mechanism, with no Supabase or TSA secrets.
