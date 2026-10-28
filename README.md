# SAHAKAR–SEVA

A hyperlocal marketplace for physical services that combines flexible worker participation, two-way
hiring and verifiable financial agreements.

One account can both **hire** help and **earn** by offering services. Local discovery is powered by
PostGIS. The distinctive layer is financial transparency: every booking produces a versioned,
two-sided price agreement, a balanced double-entry ledger entry, a hash-chained event record and a
**portable receipt that anyone can verify offline** — with an honest account of what that does and does
not prove.

> **Status:** hackathon build for local demonstration and review. **Payments are simulated — no real
> money moves.** Not production-hardened. See
> [`docs/PROJECT_CURRENT_STATE.md`](docs/PROJECT_CURRENT_STATE.md) for the verified feature inventory
> and limitations, and [`docs/JUDGE_REVIEW_GUIDE.md`](docs/JUDGE_REVIEW_GUIDE.md) to evaluate it in
> five minutes.

## The problem

- Local demand and supply for everyday physical work (assembly, repairs, cleaning) are hard to match
  efficiently.
- Flexible earning opportunities are limited and informal.
- Marketplaces suffer information asymmetry — customers and workers cannot easily see or trust the
  terms of a deal.
- There is a real risk of **hidden deductions**: a platform can quietly take an opaque cut.
- Two-sided marketplaces face **disintermediation** (bypass) once the parties meet.
- Keeping such a platform sustainable without exploiting either side is genuinely hard.

## The solution (what the current build actually does)

- **Unified hire/earn account** — one identity can request work and offer services.
- **Worker profiles and self-declared skills** — clearly labelled as self-declared, not verified.
- **PostGIS local discovery** — find workers (or nearby jobs) by locality and service radius.
- **Direct hiring and job posting** — request a worker directly, or post a job, collect applications
  and select an applicant; both converge on one booking lifecycle.
- **Booking lifecycle with worker acceptance** — request → confirm → in-progress → complete, with
  addresses revealed to the worker only after acceptance.
- **Configurable financial agreements** — a versioned pricing engine (no fixed commission) with
  per-charge bearer (customer/worker/business/platform), waivers and a hard 20% ceiling; both parties
  accept a specific quote version.
- **Financial ledger and receipts** — a balanced double-entry record on completion and a downloadable,
  independently verifiable receipt.
- **Verification and external anchoring** — local integrity always; optional RFC 3161 external
  timestamping of ledger checkpoints when a trusted timestamp authority is configured.
- **Repeat booking, organizations, and human-reviewed disputes.**

Every capability above is present in the current code. What is **simulated** (settlements/payments) or
**optional/unconfigured** (external timestamping) is labelled as such throughout.

## Architecture

- **Frontend:** React 18, TypeScript, Vite, Tailwind, React Router, TanStack Query.
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2, Psycopg 3, Alembic.
- **Database:** PostgreSQL 16 + PostGIS.
- **Auth:** Supabase bearer-token verification (HS256 secret, or server-side `/auth/v1/user`); a
  development-only local identity for demos (refused outside `APP_ENV=development`). Fails closed with
  `503` if neither is configured.
- **Ledger:** append-only SHA-256 hash chain (RFC 8785 canonical JSON), Merkle checkpoints with RFC
  9162 inclusion proofs, and a balanced double-entry ledger.
- **Anchoring:** RFC 3161 timestamping of checkpoint digests via a transactional outbox, verified
  against a **pinned** CA; only a 32-byte digest and a nonce ever leave the system.
- **Local infrastructure:** Docker Compose (`db`, `api`, `web`).

Diagrams and runtime flows: [`docs/architecture.md`](docs/architecture.md).

## Screenshots

Captured from the running app against the clearly-labelled synthetic demo dataset (every page shows the
"Demo marketplace — sample data · payments are simulated" banner). No real personal data, addresses,
tokens or passcodes are shown.

| Homepage | Worker discovery |
|---|---|
| [![Homepage](docs/assets/homepage.png)](docs/assets/homepage.png) | [![Worker discovery](docs/assets/worker-discovery.png)](docs/assets/worker-discovery.png) |

| Job board | Booking details (My Bookings) |
|---|---|
| [![Job board](docs/assets/job-board.png)](docs/assets/job-board.png) | [![Booking details](docs/assets/booking-details.png)](docs/assets/booking-details.png) |

| Financial agreement (transaction transparency) | Ledger explorer |
|---|---|
| [![Financial agreement](docs/assets/financial-agreement.png)](docs/assets/financial-agreement.png) | [![Ledger explorer](docs/assets/ledger-explorer.png)](docs/assets/ledger-explorer.png) |

| Receipt verification | Business dashboard |
|---|---|
| [![Receipt verification](docs/assets/receipt-verification.png)](docs/assets/receipt-verification.png) | [![Business dashboard](docs/assets/business-dashboard.png)](docs/assets/business-dashboard.png) |

## Quick start

Prerequisites: Docker Desktop, Node.js 20+, Python 3.12+.

```bash
git clone <this-repo-url>
cd sahakar-seva
cp .env.example .env
```

For the local demo identity (no Supabase account needed), set in `.env`:

```bash
APP_ENV=development
DEV_AUTH_ENABLED=true
DEV_AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
DEV_AUTH_PASSCODE=choose-a-passcode   # >= 8 characters
VITE_AUTH_MODE=dev
```

Start everything, apply migrations, seed the service taxonomy, and health-check:

```bash
sh scripts/dev_up.sh
```

Seed the synthetic, clearly-labelled demo dataset (local development database only):

```bash
python3 scripts/seed_demo.py --apply
```

- Web: **http://127.0.0.1:5173**  ·  API: **http://127.0.0.1:8000**  ·  Swagger: **/docs**

Sign in at `/login` with any `name@demo.sahakar.test` email and your `DEV_AUTH_PASSCODE`.

> **Development auth vs production identity.** The local `dev-auth` provider exists only for demos; it
> is refused unless `APP_ENV=development` and requires a strong secret/passcode. It is **not** identity
> verification and is separate from the production Supabase path. Do not use it outside local demos.

External timestamping is **off by default** (receipts are then "local integrity only"). To enable it,
set `TSA_URL` + `TSA_CA_FILE` together (see `.env.example`).

## Demonstration

A five-minute click-through: `/hire` → find a worker (PostGIS search) → request a slot → accept on
`/bookings` → start → complete → view the `SIMULATED PAYMENT` breakdown → open
`/bookings/:id/transparency` → download the receipt → verify it offline with
`python3 scripts/verify_receipt.py receipt.json` → try `/demo/tamper` to see detection.

Full guide: [`docs/JUDGE_REVIEW_GUIDE.md`](docs/JUDGE_REVIEW_GUIDE.md). Detailed runbooks:
[`docs/audits/LIVE_DEMO_RUNBOOK.md`](docs/audits/LIVE_DEMO_RUNBOOK.md) and
[`docs/audits/TRUST_LEDGER_DEMO_RUNBOOK.md`](docs/audits/TRUST_LEDGER_DEMO_RUNBOOK.md).

## Tests

Executed on the current working tree (see
[`docs/TESTING_AND_EVIDENCE.md`](docs/TESTING_AND_EVIDENCE.md) for environment and caveats):

```bash
# Backend (isolated PostGIS test database)
docker compose up -d db
sh services/api/scripts/create_test_database.sh
cd services/api
export TEST_DATABASE_URL=postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test
pytest                       # 335 passed, 0 failed

# Frontend
cd ../../apps/web
npm install
npm run typecheck            # clean
npm run test                 # 68 passed
npm run build                # success
```

## Limitations (honest)

- **Payments are simulated**; there is no bank/UPI integration. The ledger proves internal
  consistency, not that money moved.
- **Live Supabase login is not exercised** by the test suite; demos use the development identity.
- **External TSA anchoring is off by default** and the live DigiCert network path is not exercised by
  tests (verified against a test double).
- **No worker identity/eligibility verification** — profiles are self-declared.
- **No production operations** (monitoring, backups, rate limiting, abuse controls).
- **No subscription billing** and **no regulatory/tax readiness** (GST, payment-aggregator rules).

See [`docs/SECURITY_AND_TRUST_MODEL.md`](docs/SECURITY_AND_TRUST_MODEL.md) for the full trust model,
including a direct answer to the "you could fake payments in your own database" objection.

## Documentation

- [`docs/DOCUMENTATION_INDEX.md`](docs/DOCUMENTATION_INDEX.md) — map of current vs historical docs
- [`docs/PROJECT_CURRENT_STATE.md`](docs/PROJECT_CURRENT_STATE.md) — source of truth
- [`docs/JUDGE_REVIEW_GUIDE.md`](docs/JUDGE_REVIEW_GUIDE.md) — 5-minute path + evidence map
- [`docs/architecture.md`](docs/architecture.md) — architecture and flows
- [`docs/SECURITY_AND_TRUST_MODEL.md`](docs/SECURITY_AND_TRUST_MODEL.md) — threat/trust model
- [`docs/BUSINESS_MODEL.md`](docs/BUSINESS_MODEL.md) — product and revenue model
- [`docs/TESTING_AND_EVIDENCE.md`](docs/TESTING_AND_EVIDENCE.md) — executed test results
- [`docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md`](docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md) — ledger/receipt formats
- API contracts: [`docs/contracts/MVP_MARKETPLACE_CONTRACT.md`](docs/contracts/MVP_MARKETPLACE_CONTRACT.md), [`docs/contracts/TRUST_LEDGER_API_CONTRACT.md`](docs/contracts/TRUST_LEDGER_API_CONTRACT.md)
- Security policy: [`SECURITY.md`](SECURITY.md)

## License

No license has been chosen yet. Until a `LICENSE` file is added by the project owners, all rights are
reserved; do not assume permission to reuse this code.
