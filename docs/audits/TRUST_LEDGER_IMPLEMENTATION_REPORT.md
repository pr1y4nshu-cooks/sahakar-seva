# Trust Ledger — Implementation Report

**Date:** 2026-10-28 · **Branch:** `shresthBranch` · **Base commit:** `947a5a6` (MVP) · **Status:** implemented and verified locally; **not committed or pushed** (awaiting approval).

## 0. Revenue model correction (2026-10-28, migration 0006)

The 10% fee / 15% cap / ₹500 = ₹450 + ₹50 figures were examples, not the business model. Changes:

- **No hardcoded rate.** Pricing comes only from the active row of a new versioned `fee_policies` table, created and activated with `python -m app.cli.fee_policy` (no write API). Activation is recorded in the hash chain. No active policy → bookings fail closed (503).
- **Pricing engine** (`app/trust/pricing.py`): percentage, fixed and hybrid charges; min/max; promotional waivers; bearers customer / worker / business / platform; modeled processing charges; tax components rejected until a tax model is approved; per-policy ceiling ≤ 20%, breaches refused.
- **Immutable agreements:** each quote stores service price, totals, line items, policy id/version and definition hash, and commits the full policy definition to the event chain. New policies never re-price existing bookings; revisions stay on the booking's original policy.
- **Ledger** postings derived from the quote for every model (three new simulated accounts). Settlements keep `fee + payout = gross`.
- **Verification:** the offline CLI and the browser verifier independently re-implement the engine and recompute every line item from the committed definition; tests check the CLI engine against the server engine over 64 combinations.
- **Constraints reviewed:** all 20% CHECKs kept (plus one new on `fee_policies`); only allowed-value sets widened. Historical rows untouched (dev DB before/after 0006: 41 bookings, 23 settlements, ₹14,500 settled — unchanged; backup `~/sahakar-backups/sahakar_seva_pre_0006_20261028025207.dump`).
- **Local dev** runs `illustrative-pilot-example v1` ("10% worker-borne platform fee (NOT final pricing)"), activated by `bootstrap-example` in `dev_up.sh`. Five illustrative definitions are in `services/api/fee_policies/examples/`.
- **UI:** shared breakdown now shows service price, each line item with bearer, customer total, worker payout, platform and processing charges, taxes, policy id/version (and "illustrative example" label). `/hire` preview is priced by the server. `/pricing` renders the active policy record and history. `/economics` adds a candidate-policy simulator.
- **New endpoints:** `GET /fee-policies`, `GET /fee-policy/applicable`, `POST /pricing/preview`, `POST /pricing/simulate`; `GET /fee-policy` response reshaped; quote revisions take `service_price_paise`.

Final results after the correction are in §7.

## 1. Baseline verified before changes

- Branch `shresthBranch`, clean tree, `HEAD = origin/shresthBranch = 947a5a6`.
- Root `.env` `DATABASE_URL` points to the local Docker DB (`localhost:55432`); the remote Supabase URL is commented out. `scripts/dev_up.sh` pins `POSTGRES_*` to the local DB; the API container uses `db:5432/sahakar_seva`.
- Alembic head `0004_marketplace_core`; backend tests **152 passed**.
- Dev DB backed up before migrating: `~/sahakar-backups/sahakar_seva_pre_0005_20261028015401.dump` (pg_dump custom format).
- Dev DB counts before → after migration: users 407 → 407, worker_profiles 97 → 97, organizations 90 → 90, jobs 6 → 6, bookings 8 → 8, settlements 4 → 4, disputes 2 → 2. Later growth comes only from tagged `@demo.sahakar.test` demo runs. The 8 original bookings remain legacy records with no quote rows.

## 2. What was built

| Slice | Implemented |
|---|---|
| A Pricing & agreement | Versioned immutable quotes (`price_quote_versions`), acceptances (`quote_acceptances`), version-bound worker accept, revisions with renewed acceptance, price lock (API + trigger), legacy labelling |
| B Ledger | `financial_ledger_transactions` / `_entries`, balanced 3-entry posting atomic with the settlement, idempotency, reversal transactions, append-only + deferred balance triggers |
| C Event chain | `financial_events`: global SHA-256 chain + per-booking chain, RFC 8785 canonical JSON, advisory-lock serialisation, server integrity verifier + CLI |
| D Anchoring | Merkle (RFC 9162) checkpoints, transactional outbox, RFC 3161 client/verifier (asn1crypto + OpenSSL, pinned root), honest six-state status, retries, CLI, in-process worker |
| E Portable proof | Receipt v1 download, standalone offline verifier (`scripts/verify_receipt.py`) with `--tsa-ca` and `--compare`, browser verifier `/verify` (local only) |
| F/G UI | Trust panel on `/bookings` for both parties (breakdown, acceptances, evidence, ledger table, events, receipt, verify, revise, accept revision), pre-confirmation breakdown on `/hire`, earnings ledger status on `/earn` |
| H Disputes | Financial categories, attached quote/ledger/receipt evidence, chain events, reviewer full reversal (history kept) |
| I Retention | "Book again" (new booking, current rate, worker consent), SAHAKAR Protected Booking panel (with what is *not* included), org dashboard + CSV, "Post a similar job" template |
| J Revenue | Public `/pricing` from `GET /fee-policy`, planned subscription (no button), `/economics` recorded (staff) vs scenario calculator |

## 3. Database (`0005_transparency_and_trust`, additive)

New tables: `financial_events`, `price_quote_versions`, `quote_acceptances`, `financial_ledger_transactions`, `financial_ledger_entries`, `anchor_checkpoints`.
New nullable columns: `bookings.repeat_of_booking_id`; `disputes.category`, `related_quote_version`, `related_ledger_transaction_id`, `related_receipt_event_hash`, `ledger_correction` (+ CHECKs).
Triggers: append-only (UPDATE/DELETE/TRUNCATE) on the five trust tables; deferred constraint triggers for ledger balance; checkpoint guard (body immutable, no delete, anchored = final); booking price guard.
Historical migrations 0001–0004 untouched. Downgrade tested.

## 4. API

See `docs/contracts/TRUST_LEDGER_API_CONTRACT.md`. New: `GET /fee-policy`, `GET /trust/anchoring`, `GET /trust/checkpoints`, `GET /trust/checkpoints/{index}`, `GET /trust/integrity` (staff), `GET /economics/summary` (staff), `GET /bookings/{id}/financial-record`, `GET /bookings/{id}/receipt`, `POST /bookings/{id}/quote-revisions`, `POST /bookings/{id}/quotes/{version}/accept`, `GET /bookings/{id}/repeat-options`, `GET /organizations/{id}/financial-summary`, `GET /organizations/{id}/financial-report.csv`. Additive fields/bodies on existing booking, dispute and earnings routes. OpenAPI paths 36 → 49.

## 5. Frontend

New: `components/trust/{TrustPanel,ReceiptVerifier,OrgDashboard}.tsx`, `lib/{trust,receiptVerify}.ts`, pages `/pricing`, `/verify`, `/economics`. Changed: Bookings, Hire (preview + template), MyJobs, Organizations, Earn earnings, DisputeReview, Layout (Pricing link), App routes. No secrets in the bundle (searched `dist/` for secret names and the dev secret value: 0 matches).

## 6. External anchoring — actual status

Configured in the local `.env` (git-ignored) with the public **DigiCert** TSA (`http://timestamp.digicert.com`) and the pinned DigiCert Trusted Root G4 (SHA-256 `552f7bdc…c89988`, matched in two independent sources). On the live dev stack **16 of 16 checkpoints are `EXTERNALLY_ANCHORED`**, each token verified by the server and again by the offline CLI against the pinned root (`trust_demo.py`: "RFC 3161 token verified"). `verify_ledger`: OK, 156 events, 16 checkpoints, 19 ledger transactions. Failure paths (unreachable, lying TSA, wrong root) are tested with an isolated test TSA. Without TSA settings the system runs `LOCAL_ONLY`.

## 7. Test evidence (final run after the revenue-model correction, 2026-10-28)

| Check | Result |
|---|---|
| Backend `pytest` on host, isolated test DB | **312 passed** (152 MVP baseline + 66 trust + 94 pricing/policy) |
| Backend inside API container (verifier copied in) | 310 passed, 2 skipped (pre-existing: contract YAML not mounted) |
| Frontend `npm run typecheck` | 0 errors |
| Frontend `vitest` | **51 passed** |
| `npm run build` | OK (pre-existing >500 kB chunk warning) |
| `scripts/e2e_demo.py` (MVP API E2E) | **35/35** |
| `scripts/trust_demo.py` (Demos 1–6 + candidate-policy simulation, live API + DigiCert) | **29/29** |
| `scripts/browser_e2e.cjs` (MVP browser) | **13/13** |
| `scripts/trust_browser_e2e.cjs` (trust + pricing browser, mobile + desktop) | **20/20** |
| Offline verifier on a live receipt with `--tsa-ca` DigiCert root | EXTERNALLY TIMESTAMPED AND VERIFIED (6/6 events) |
| Offline verifier on a hybrid/waiver/platform-absorbed receipt | LOCAL INTEGRITY VERIFIED; tampered variants fail |
| `app.cli.verify_ledger` on dev DB | OK |
| `alembic current` | `0006_configurable_fee_policies (head)` |

## 8. Demo scenarios passed

1 Transparent ₹500 price (both views identical, same quote v1) · 2 Completion, balanced ledger, DB refuses edits · 3 Hidden ₹400/₹360 deduction detected on receipt copies (display-only and payload edits; fully re-hashed forgery caught by checkpoint/TSA and by `--compare`) · 4 Offline verification: local and **externally timestamped by DigiCert** · 5 Repeat booking with consent, history, protection terms, dispute route · 6 Public fee policy, org dashboard with recorded data, staff-only economics, planned subscription.

## 9. Known risks and limits

- Payment evidence is **simulated**.
- Pricing levels, bearers and models are undecided; the active local policy is an illustrative example. Nothing is provider-confirmed; no money moves.
- A DB superuser can disable triggers; only checkpointed **and** anchored events are protected against such an operator. Events between checkpoints (≈20 s) are locally tamper-evident only.
- Omission: the platform could refuse to record events or issue a receipt; this is detectable by participants (missing receipt/acceptance), not prevented.
- RFC 3161 checks do not include revocation (CRL/OCSP). The verifier needs the `openssl` CLI and `asn1crypto` for token checks.
- Receipts are not platform-signed; origin rests on TSA tokens and participant copies.
- Global chain serialises financial writes (fine for pilot scale).
- Pricing model and level, leakage and subscription demand are unvalidated assumptions.
- Supabase auth still unverified end-to-end; demos use the local development identity.
- `.env` now enables the DigiCert TSA locally; remove the four `TSA_*`/`ANCHOR_*` lines to return to local-only.

## 10. Suitability

Suitable for a hackathon demonstration on this MacBook: the trust claims shown in the UI are backed by working code, tests and live external timestamps. Not production-ready (simulated payments, dev identity, no revocation checking, no regulated provider).

## 11. Git

Uncommitted changes on `shresthBranch` only; nothing committed, pushed or merged. `.env` and `apps/web/.env.local` remain git-ignored. `.gitignore` gained `!services/api/trust/tsa/*.pem` so the public root certificate can be committed.
