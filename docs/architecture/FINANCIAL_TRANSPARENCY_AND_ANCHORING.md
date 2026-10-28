# Financial Transparency and Independent Anchoring

**Scope:** migration `0005_transparency_and_trust`; code in `services/api/app/trust/`, `app/services/trust_service.py`, `scripts/verify_receipt.py`, `apps/web/src/lib/receiptVerify.ts`.

## 1. Problem and claim

Judges asked what stops the platform from telling a worker that a ₹500 job was ₹400, paying ₹360, and keeping ₹140. The product claim is now:

> Customers and workers receive the same itemized booking agreement. Financial changes are recorded in a tamper-evident ledger, and independently witnessed commitments can be verified separately.

It is not claimed that a bank or payment provider confirmed any amount. Payments are simulated.

## 2. Threat model

| Actor / failure | What we defend | How |
|---|---|---|
| Platform shows the worker a different total than the customer agreed | Both screens read one quote row; receipts commit the quote in a hash chain | `price_quote_versions` is the only source; worker and customer receipts contain identical committed events |
| Application bug or rogue code edits a posted amount | Append-only tables | Triggers reject UPDATE/DELETE/TRUNCATE; deferred trigger rejects unbalanced ledger transactions at COMMIT; booking price guard |
| Silent price change after agreement | Versioned quotes + acceptance | New version required, both acceptances required, `accept` must name the version |
| Operator with database superuser rewrites history consistently and recomputes every hash | Detectable against evidence outside the operator's control | RFC 3161 tokens from an external TSA over checkpoint digests; receipts already held by participants (`--compare`) |
| TSA outage or forged/misconfigured TSA response | Never over-claim | Status stays pending/failed/`PROOF_INVALID`; only a fully verified token gives `EXTERNALLY_ANCHORED` |
| Data leakage via proofs | Minimal disclosure | TSA receives 32 bytes + nonce; receipts carry no names/addresses/phones/free text; public endpoints expose hashes only |

**Trusted:** the external TSA (DigiCert) for time attestation; the pinned root certificate obtained independently; SHA-256; OpenSSL and `asn1crypto`/`rfc8785` implementations; the participant's own retained receipt.
**Not trusted for independent assurance:** the SAHAKAR API, its database, its server, and anything inside a receipt that is not bound to an external token or an earlier copy.

**Out of scope / limits:** a superuser can disable triggers (that is why external anchoring exists); events written but not yet checkpointed and anchored are only locally tamper-evident; the platform could refuse to record an event at all (participants then lack a receipt — this is visible, not hidden); TSA revocation (CRL/OCSP) is not checked; receipts are not signed by the platform, so origin authentication rests on the TSA token and participant copies, not on a platform key.

## 3. Quote and acceptance semantics

- Every new booking gets quote **v1** at creation: direct hire service price = worker hourly rate × slot minutes (server-computed), source `booking_request`, accepted by the customer; job hire service price = job budget, source `job_selection`, accepted by the job manager who selected the applicant.
- The quote is priced by the fee policy **active at that moment** (organization-specific terms if the job belongs to an organization that has them, else the default policy) — see §3a. The quote stores the service price, customer total, worker payout, platform charges, modeled processing charges, tax (0, not modeled), every line item with its bearer, the effective charge rate, the policy ceiling, the policy id/version and the policy definition hash.
- While `requested`, either party may propose a new **service price** → version n+1 with the proposer's acceptance, priced under the **same policy as the previous version** (agreed terms do not switch mid-negotiation). Older versions are never modified.
- Confirmation requires the customer's acceptance of the current version (not required for labelled `legacy_snapshot`) and the worker's `accept` naming that version.
- After `requested`, the price is locked: API returns `PRICE_LOCKED`; `trg_bookings_price_guard` rejects changes to the booking's price columns. Activating a different policy never re-prices an existing booking.

## 3a. Configurable fee policies (migration 0006)

**No rate is hardcoded.** Live pricing comes only from the `fee_policies` table. A policy version is immutable (trigger); status moves `draft → active → retired`; at most one active default policy and one per organization (partial unique indexes). Policies are created and activated only with the server CLI `python -m app.cli.fee_policy`; activation retires the previous policy of the same scope and writes a `fee_policy_activated` event (with the definition hash) to the hash chain. If no policy is active, bookings fail closed with 503 `NO_ACTIVE_FEE_POLICY`.

Definition (`sahakar-seva/fee-policy/v1`, validated in `app/trust/pricing.py`): `label`, `description`, `is_example`, `components[]`, `promotions[]`, `max_total_charge_bps` (≤ 2000), `subscription_plan_code` (label for future organization plans; no billing exists).

Component: `code`, `kind` (`platform_fee` | `processing_charge`; `tax` is rejected until an approved tax model exists), `label`, `bearer` (`customer` | `worker` | `business` | `platform`), `percent_bps`, `fixed_paise`, optional `min_paise`/`max_paise`, `applies_to_origins`, `organization_bookings` (`any`/`only`/`never`).

```
computed  = round_half_up(service × percent_bps / 10000) + fixed_paise, clamped to [min_paise, max_paise]
amount    = 0 if an active promotion waives the component (waived amount still recorded), else computed
customer_total = service + Σ customer- and business-borne amounts
worker_payout  = service − Σ worker-borne amounts          (≥ 0)
platform charges = Σ party-borne platform_fee;  processing = Σ party-borne processing_charge
customer_total − worker_payout = platform charges + processing          (enforced; DB CHECKs)
Σ party-borne ≤ service × max_total_charge_bps / 10000  → otherwise REFUSED (422 CHARGE_CEILING_EXCEEDED)
```

Percentage, fixed and hybrid models are all this formula. Bearers: `business` only for organization bookings (billed to the organization); `platform` only for processing charges (absorbed; changes neither party's numbers). `pricing_model` is derived (`percentage`, `fixed`, `hybrid`, `no_charge`). The definition hash is `SHA-256("SAHAKAR-SEVA:fee-policy:v1" ‖ 0x00 ‖ JCS(definition))`.

**Safety constraints reviewed (none weakened):** the 2000 bps ceiling stays on `bookings.fee_bps`, `settlements.fee_bps`, `price_quote_versions.fee_bps`, and is added on `fee_policies.max_total_charge_bps`. `fee_bps` now means the effective party-borne charge rate on the service price, rounded up (always ≤ the policy ceiling ≤ 2000). `fee_paise + payout_paise = price_paise` on bookings and settlements still holds (`price_paise` = customer total, `fee_paise` = party-borne charges). The only CHECK changes in 0006 add allowed values (three ledger accounts, one event type).

`PLATFORM_FEE_BPS` / `PLATFORM_FEE_CAP_BPS` are now only inputs to `bootstrap-example`, which activates a policy labelled "Illustrative pilot example … (NOT final pricing)" when none is active (local development). Example definitions: `services/api/fee_policies/examples/` (all `is_example: true`).

## 4. Canonical serialization and hashing (format v1)

- **Canonical JSON:** RFC 8785 (JCS) via the `rfc8785` package (Trail of Bits). Profile restriction enforced on write and read: integers within ±(2⁵³−1), no floats, ASCII object keys. Within this profile JCS equals `JSON.stringify` with recursively sorted keys (used by the browser verifier) and `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` (CLI fallback); tests assert the equivalence.
- **Payload hash:** `SHA-256("SAHAKAR-SEVA:financial-event-payload:v1" ‖ 0x00 ‖ JCS(payload))`
- **Event hash:** `SHA-256("SAHAKAR-SEVA:financial-event:v1" ‖ 0x00 ‖ uint64_be(sequence) ‖ previous_event_hash[32] ‖ payload_hash[32])`
- **Genesis:** `previous_event_hash` of sequence 1 is 32 zero bytes.
- Domain separators are NUL-terminated and each hash has at most one variable-length field (last), so encodings are unambiguous.

Event payload fields: `format`, `event_id`, `event_type`, `occurred_at` (UTC, microseconds), `booking_id`, `booking_event_index`, `booking_previous_event_hash`, `currency`, `actor {role, user_id}`, `data`. Event types: `quote_created`, `quote_revised`, `quote_accepted`, `booking_confirmed`, `booking_declined`, `booking_cancelled`, `booking_completed`, `simulated_settlement_recorded`, `dispute_opened`, `dispute_decision_recorded`, `ledger_reversal_posted`.

There are two chains: the **global chain** (sequence + previous hash; detects reordering and gaps in the whole log) and a **per-booking chain** inside each payload (index + previous booking event hash; lets a receipt be verified alone).

**Concurrency:** `append_event` takes `pg_advisory_xact_lock`, reads the head, and inserts; the lock is held to COMMIT, so sequence order equals commit order. UNIQUE on `sequence`, `previous_event_hash` and `event_hash` is the backstop. A two-thread test proves adjacent sequences and no fork.

## 5. Ledger posting rules

Posted atomically with the settlement inside the completion transaction (idempotency key `booking-settlement:<booking_id>`, UNIQUE settlement id and source event). Entries are derived from the accepted quote for every pricing model (`pricing.ledger_entries`):

| Account | Direction | Amount |
|---|---|---|
| `simulated_customer_payment_clearing` | debit | customer total − business-borne |
| `simulated_business_payment_clearing` | debit | business-borne charges (organization bookings) |
| `simulated_platform_promotion_expense` | debit | platform-absorbed charges |
| `simulated_worker_entitlement` | credit | worker payout |
| `simulated_platform_fee_allocation` | credit | platform charges |
| `simulated_processing_charge_allocation` | credit | modeled processing (party- and platform-borne) |

Zero-amount entries are omitted; debits = credits = transaction amount (deferred DB trigger). Example with the illustrative 10% worker-borne policy on a ₹500 service: debit ₹500, credit worker ₹450, credit platform ₹50. Example with an illustrative ₹25 customer-borne fixed fee: debit ₹525, credit worker ₹500, credit platform ₹25.

A reversal (`simulated_settlement_reversal`, key `reversal:<tx_id>`) swaps directions and references the original. The original settlement and entries stay. This is a demonstration accounting model: it is not a bank receivable, recognised revenue, or a transfer.

## 6. Checkpoints and Merkle construction

A checkpoint covers the contiguous sequence range after the previous checkpoint. Before creating it the worker re-verifies those events. Merkle tree per RFC 9162 §2.1.1 over `event_hash` leaves: `leaf = SHA-256(0x00 ‖ h)`, `node = SHA-256(0x01 ‖ L ‖ R)`; inclusion proofs verified per RFC 9162 §2.1.3.2.

Checkpoint body: `format`, `hash_alg`, `checkpoint_index`, `first_sequence`, `last_sequence`, `event_count`, `merkle_root`, `merkle_construction`, `last_event_hash`, `previous_checkpoint_digest` (genesis zeros), `created_at`.
`checkpoint_digest = SHA-256("SAHAKAR-SEVA:checkpoint:v1" ‖ 0x00 ‖ JCS(body))`. This digest is the RFC 3161 message imprint. Checkpoints form their own chain.

## 7. External timestamp protocol (RFC 3161)

- **Outbox:** the checkpoint row is the outbox entry. The in-process worker (`ANCHOR_WORKER_ENABLED`, every 20 s) or `python -m app.cli.anchor --once`: (1) short transaction creates the checkpoint; (2) short transaction claims one due checkpoint with `FOR UPDATE SKIP LOCKED`, stores a fresh 63-bit nonce, sets `ANCHOR_SUBMITTED`, commits; (3) HTTP POST of a DER `TimeStampReq` (`application/timestamp-query`) with **no transaction open**; (4) verification; (5) short transaction records the result. Bounded exponential backoff (`ANCHOR_RETRY_BASE_SECONDS`, max 1 h), `ANCHOR_MAX_ATTEMPTS` (5), stale `ANCHOR_SUBMITTED` (>5 min) is retried, `--retry-failed` re-queues.
- **Request:** built with `asn1crypto`: version 1, SHA-256 imprint, nonce, `certReq=true`. Nothing else.
- **Verification** (`app/trust/timestamping.py`, repeated independently in the CLI): HTTP 200 and correct content type are necessary but never sufficient; status granted; token is CMS SignedData with TSTInfo; imprint algorithm SHA-256 and value equal the checkpoint digest; nonce equals the request nonce; exactly one signer whose certificate has a **critical** `timeStamping` EKU and was valid at genTime; then `openssl ts -verify -digest <hex> -CAfile <pinned root> -attime <genTime>` checks the CMS signature, the chain to the pinned root, the signer purpose and the ESS signing-certificate binding. Certificates inside the response are used only as untrusted chain material.
- **States:** `LOCAL_ONLY` (no TSA configured), `ANCHOR_PENDING`, `ANCHOR_SUBMITTED`, `EXTERNALLY_ANCHORED` (only after all checks pass; DB CHECK requires token, genTime and verified_at; trigger makes the row final), `ANCHOR_FAILED` (unreachable after max attempts), `PROOF_INVALID` (a response failed verification). A booking completes regardless of the TSA.

## 8. Trust-anchor configuration and key handling

- `TSA_URL`, `TSA_NAME`, `TSA_CA_FILE` must be set together (startup validation). Local demo: `http://timestamp.digicert.com`, root `services/api/trust/tsa/digicert-trusted-root-g4.pem` (public CA certificate; not a secret; whitelisted in `.gitignore`).
- **DigiCert Trusted Root G4 SHA-256:** `552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988` — identical in the file downloaded from `https://cacerts.digicert.com/DigiCertTrustedRootG4.crt` and in the Mozilla/certifi root bundle (checked 2026-10-28). Verifiers should obtain the root themselves and compare.
- HTTP transport to the TSA is standard practice: the token is signed, so transport integrity is not relied on.
- No private keys exist in this design. The test TSA (tests only) generates throw-away keys in a pytest temp directory.

## 9. Proof bundle (receipt v1) and verification

`GET /bookings/{id}/receipt` → `receipt_format`, `generated_at`, `generated_for_role`, `evidence_level`, `notice`, `summary` (booking id, quote version, service price, all amounts, fee policy id/version, pricing model, policy definition hash), `booking` (id, origin, status, skill id, times, repeat link), `agreement`, `settlement`, `ledger_transaction_ids`, `events[]` (sequence, type, previous hash, full payload, payload hash, event hash, Merkle inclusion proof), `checkpoints[]` (body, digest, status, RFC 3161 response DER base64, nonce, genTime, server-side anchor fingerprint), `hashing`, `verification`, `privacy`.

**Verifier results:** `EXTERNALLY TIMESTAMPED AND VERIFIED` (every event inside a checkpoint whose token verified against the root *you* passed with `--tsa-ca`), `LOCAL INTEGRITY VERIFIED` ("Local integrity verified — independent timestamp not yet available."), `EXTERNAL EVIDENCE UNAVAILABLE` (legacy), `VERIFICATION FAILED`. Checks include every hash, both chains, displayed-vs-committed amounts and policy reference, the policy definition hash, **recomputation of every line item and total from the committed policy definition** (independent engine in the CLI and in the browser), the ceiling, allocation, acceptance binding to the quote event hash, settlement = quote, ledger balance, checkpoint digests, Merkle inclusion and position, token imprint/nonce/signature/chain, and claims of anchoring without a token. `--compare older.json` fails if any event the participant held earlier is missing or different.

The browser verifier at `/verify` performs the local checks with WebCrypto and never reports external verification.

## 10. Privacy boundaries

- TSA: 32-byte digest + random nonce only.
- Receipts (participant-authorised download): random UUIDs, amounts, times, skill id; no names, addresses, phones, notes or dispute text. Dispute free text is never committed to the chain.
- Public checkpoint endpoints: hashes, ranges, timestamps; no booking ids.
- Organization reports: only the organization's own job-post bookings, worker display name and that booking's breakdown.

## 11. Historical data

No backfill. 0004-era bookings and settlements remain as stored and are labelled **legacy** (no quote acceptance, ledger or hash-chain evidence claimed). If a legacy booking is acted on after 0005 (accept, complete), its stored price is recorded as a `legacy_snapshot` quote (`fee_policy_id=legacy-mvp-snapshot`) without a customer acceptance; new events from that point are real evidence.
