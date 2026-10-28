# Judge Review Guide

The first document to read after the [README](../README.md). It gives a five-minute evaluation path
and a claim→evidence map tying every notable claim to source, API, tests and docs. Written for human
and automated reviewers alike.

This guide does not tell you how to rate the project, and it does not ask you to overlook anything.
The limitations are listed in [`PROJECT_CURRENT_STATE.md`](PROJECT_CURRENT_STATE.md) and
[`SECURITY_AND_TRUST_MODEL.md`](SECURITY_AND_TRUST_MODEL.md); please weigh them.

## Five-minute evaluation path

**What it is.** A hyperlocal marketplace for physical services with a unified hire/earn account,
PostGIS-based local discovery, a full booking lifecycle, and — the distinctive part — a verifiable
financial-agreement layer: versioned two-sided price quotes, a balanced double-entry ledger, a
hash-chained event log with Merkle checkpoints, and portable receipts that verify offline.

**What differentiates it.** Honest, verifiable financial transparency: the system proves internal
consistency with cryptography **and openly states what that does not prove** (payments are simulated;
a local ledger is not proof of a real bank payment). External RFC 3161 timestamping is implemented for
independent assurance when configured.

**Start the app (fresh clone).**

```bash
cp .env.example .env
# For the demo identity, set in .env:  APP_ENV=development, DEV_AUTH_ENABLED=true,
# DEV_AUTH_SECRET=<48+ random chars>, DEV_AUTH_PASSCODE=<your choice>, VITE_AUTH_MODE=dev
sh scripts/dev_up.sh                 # compose up, migrate to head, seed taxonomy, activate example policy
python3 scripts/seed_demo.py --apply # synthetic, clearly-labelled demo dataset (local dev DB only)
```

Open **http://127.0.0.1:5173** · API **http://127.0.0.1:8000** · Swagger **/docs**.

**Use the seeded demo.** Sign in at `/login` with any `name@demo.sahakar.test` email and your
`DEV_AUTH_PASSCODE`. Visit `/demo` for the guided hub. Full scripts:
[`audits/LIVE_DEMO_RUNBOOK.md`](audits/LIVE_DEMO_RUNBOOK.md) (marketplace) and
[`audits/TRUST_LEDGER_DEMO_RUNBOOK.md`](audits/TRUST_LEDGER_DEMO_RUNBOOK.md) (pricing/ledger/receipts).

**Journeys to run.**
1. Direct hire: `/hire` → search workers (PostGIS radius) → request a slot → worker accepts on
   `/bookings` → start → complete → see the `SIMULATED PAYMENT` breakdown.
2. Job posting: `/hire` post a job → worker applies on `/find-work` → select on `/my-jobs` → shared
   booking lifecycle.
3. Dispute: open a problem on a booking → resolve it as a reviewer on `/disputes/review`.

**Open and inspect the ledger.** On a completed booking, open `/bookings/:id/transparency` (or
`GET /api/v1/bookings/{id}/financial-record`) to see quotes, acceptances, events and ledger entries.

**Verify an exported receipt.** Download via `GET /api/v1/bookings/{id}/receipt`, then:

```bash
python3 scripts/verify_receipt.py receipt.json           # offline; no server, no DB
```

**Demonstrate tampering detection.** Use the `/demo/tamper` page, or:

```bash
python3 scripts/tamper_receipt.py receipt.json > tampered.json
python3 scripts/verify_receipt.py tampered.json          # VERIFICATION FAILED
python3 scripts/verify_receipt.py tampered.json --compare receipt.json   # detects divergence
```

**Where the tests are.** `services/api/tests/` (backend, 335 passing) and `apps/web/src/*.test.tsx`
(frontend, 68 passing). Executed results: [`TESTING_AND_EVIDENCE.md`](TESTING_AND_EVIDENCE.md).

**Where the limitations are.** [`PROJECT_CURRENT_STATE.md`](PROJECT_CURRENT_STATE.md) §Known
limitations and [`SECURITY_AND_TRUST_MODEL.md`](SECURITY_AND_TRUST_MODEL.md) §§1, 10.

## Evidence map (claim → source → API → tests → docs)

Paths are stable module/file identifiers (no line numbers, which drift).

### Claim: overlapping worker bookings are prevented
- **Constraint:** `ex_bookings_worker_no_overlap` exclusion constraint — migration
  `services/api/alembic/versions/0004_marketplace_core.py` (backed by `btree_gist`).
- **Service:** `app/services/booking_service.py` → `transition(... "accept")` row-locks the worker
  profile and re-checks overlap before committing.
- **Tests:** `tests/db/test_booking_concurrency.py`.

### Claim: the agreed price is a versioned, two-sided record
- **Source:** `app/services/trust_service.py` (`create_quote`, `accept_quote`, quote-revision flow);
  `app/trust/pricing.py` (fee policy evaluation).
- **API:** `POST /bookings/{id}/quote-revisions`, `POST /bookings/{id}/quotes/{version}/accept`,
  `GET /bookings/{id}/financial-record`.
- **Tests:** `tests/db/test_trust_ledger.py`, `tests/db/test_fee_policies.py`,
  `tests/test_pricing_engine.py`.

### Claim: settlements are simulated and clearly labelled
- **Source:** `app/services/booking_service.py` (`_record_settlement`, `is_simulated=True`);
  `app/models/marketplace.py` (`SIMULATED_PAYMENT_LABEL`).
- **Tests:** `tests/db/test_marketplace.py`.

### Claim: the financial ledger is balanced (double-entry)
- **Source/verifier:** `app/trust/integrity.py` → `verify_ledger` (debits == credits == amount).
- **Tests:** `tests/db/test_trust_ledger.py`.

### Claim: the event log is a tamper-evident hash chain
- **Source:** `app/trust/chain.py` (append-only, advisory-locked), `app/trust/crypto.py` (SHA-256,
  domain separation, RFC 8785 canonical JSON).
- **Tests:** `tests/test_trust_crypto.py`, `tests/db/test_trust_ledger.py`.

### Claim: receipt tampering is detected
- **Verifier:** `scripts/verify_receipt.py` (independent re-implementation; does not import server
  code), frontend `apps/web/src/lib/receiptVerify.ts`.
- **Proof format:** `docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md` §4.
- **Adversarial:** `scripts/tamper_receipt.py`, `tests/db/test_trust_ledger.py`,
  `tests/verifier_path.py`, `scripts/audit/*`.

### Claim: independent timestamping is supported
- **Source:** `app/trust/timestamping.py` (RFC 3161 request/verify, pinned CA), `app/trust/anchoring.py`
  (outbox state machine).
- **Tests:** `tests/test_trust_timestamping.py` with a test-double TSA (`tests/tsa_double.py`).
- **Status if unconfigured:** `LOCAL_ONLY` — nothing is sent anywhere. Real DigiCert network path is
  **NOT exercised** by the suite (see `TESTING_AND_EVIDENCE.md`).

### Claim: a local ledger is not proof of a real payment
- **Honest scope note in code:** `app/trust/integrity.py` module docstring and
  `scripts/verify_receipt.py` header ("does NOT prove real money changed hands").
- **Docs:** [`SECURITY_AND_TRUST_MODEL.md`](SECURITY_AND_TRUST_MODEL.md) §1.

### Claim: public endpoints do not leak personal data
- **Source:** `app/api/v1/demo.py` (`/marketplace/overview`, `/jobs/open` — locality + distance only).
- **Booking address gating:** `app/services/booking_service.py` (`ADDRESS_VISIBLE_TO_WORKER`).

### Claim: development auth cannot run in production
- **Source:** `app/core/config.py` (`validate_policies`: `dev-auth` refused unless
  `APP_ENV=development`, secret/passcode length enforced).
- **Tests:** `tests/test_dev_auth.py`, `tests/test_config.py`.

### Claim: the demo seeder is safe and synthetic
- **Source:** `app/cli/seed_demo.py`, `app/demo/` (refuses non-dev / remote / Supabase / test DBs; no
  reset/delete; idempotent).
- **Tests:** `tests/db/test_demo_seed.py`.
