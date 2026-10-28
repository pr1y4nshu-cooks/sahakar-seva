# SAHAKAR–SEVA — Trust Ledger API Contract

**Status:** Implemented on `shresthBranch` (2026-10-28). Additive to the frozen Phase 2 contract and the MVP marketplace contract: no existing route, field or status code was removed or changed in meaning.
**Migrations:** `0005_transparency_and_trust` (down `0004_marketplace_core`) and `0006_configurable_fee_policies` (down `0005`).
**Error envelope:** unchanged — `{"error": {"code", "message", "details"}}`.
**Money:** integer paise. **Hashes:** lowercase hex SHA-256. **Payments:** simulated.

Formats and algorithms are specified in `docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md`.

## 1. Additive changes to existing routes

| Route | Change |
|---|---|
| `POST /bookings` | Optional `repeat_of_booking_id`. Must be the caller's own **completed** booking with the same worker (404 if not the caller's, 422 `REPEAT_NOT_ALLOWED` otherwise). The server writes quote v1 (`source=booking_request`) and the customer's acceptance in the same transaction. |
| `POST /jobs/{id}/applications/{aid}/select` | Writes quote v1 (`source=job_selection`, total = job budget) and records the selecting job manager's acceptance on the customer side. |
| `POST /bookings/{id}/accept` | Optional body `{"quote_version": n}`. 409 `QUOTE_VERSION_MISMATCH` if not the current version; 409 `QUOTE_VERSION_REQUIRED` if the price was revised (v > 1) and no version was sent; 409 `QUOTE_NOT_ACCEPTED` if the customer has not accepted the current version. Records the worker's acceptance and a `booking_confirmed` event. |
| `POST /bookings/{id}/{decline,cancel}` | Also records `booking_declined` / `booking_cancelled` events (fee assessed: 0). |
| `POST /bookings/{id}/complete` | In the **same transaction**: `booking_completed` event, the immutable settlement, a balanced ledger transaction, and a `simulated_settlement_recorded` event. Any failure rolls everything back. |
| `POST /bookings/{id}/disputes` | Optional `category` (`customer_total_differs`, `worker_payout_differs`, `unexpected_deduction`, `payment_evidence_mismatch`, `receipt_verification_failed`, `other_booking_issue`) and `receipt_event_hash` (must be one of this booking's events, else 422 `RECEIPT_EVENT_UNKNOWN`). The server attaches the current quote version and settlement ledger transaction. Records a `dispute_opened` event. |
| `POST /disputes/{id}/resolve` | Optional `ledger_correction`: `none` (default) or `full_reversal`. Reversal needs a posted, unreversed settlement (409 `NOTHING_TO_REVERSE` / `ALREADY_REVERSED`). Records `dispute_decision_recorded` and, for a reversal, a new reversing ledger transaction plus `ledger_reversal_posted`. Reviewer rules are unchanged (reviewers only, never a party). |
| `GET /bookings/mine`, `GET /bookings/{id}` | New fields: `agreement` (current quote), `evidence` (payment/ledger/chain/anchor status), `agreement_actions` (`revise_quote`, `accept_quote`, `repeat`, `download_receipt`), `repeat_of_booking_id`; `dispute` gains `category`, `related_quote_version`, `related_ledger_transaction_id`, `related_receipt_event_hash`, `ledger_correction`. `allowed_actions` and `price` are unchanged. |
| `GET /earnings/mine` | New `ledger_totals` and per-settlement `ledger_transaction_id`, `ledger_status`, `reversed`. `totals` is unchanged. |
| `GET /disputes/review-queue` | Items gain the dispute evidence fields and `has_simulated_settlement`. |

`agreement` (0006) also carries `service_price_paise`, `pricing_model`, `fee_policy_id`, `fee_policy_version`, `policy_definition_hash`, `is_example_policy`, `policy_label`, `line_items[]` (code, kind, label, bearer, calculation, computed and charged amount, `waived_by`). `price.price_paise` = customer total, `price.fee_paise` = party-borne charges, `price.fee_bps` = effective charge rate on the service price. Booking creation returns 503 `NO_ACTIVE_FEE_POLICY` or 422 `CHARGE_CEILING_EXCEEDED` when it cannot be priced.

`agreement.evidence_level`: `versioned` (quote rows exist), `legacy_snapshot` (a pre-0005 booking acted on after the migration; its stored price was recorded as a labelled snapshot with no customer acceptance claimed), `legacy` (no trust rows at all).

`evidence.anchor.status`: `LOCAL_ONLY`, `ANCHOR_PENDING`, `ANCHOR_SUBMITTED`, `EXTERNALLY_ANCHORED`, `ANCHOR_FAILED`, `PROOF_INVALID`, or `null` (legacy). It is the status of the checkpoint containing the booking's latest event; if that event is not yet checkpointed it is `ANCHOR_PENDING` (TSA configured) or `LOCAL_ONLY`.

## 2. New routes (all under `/api/v1`)

### Public (no authentication; no personal data)

| Route | Returns |
|---|---|
| `GET /fee-policy` | `{active_policy, examples, examples_note, rules}`. `active_policy` is the active default `fee_policies` record (id, version, label, `is_example`, `pricing_model`, ceiling, definition + hash, components with bearer and description, promotions) or `null`. `examples` evaluates illustrative service prices. `rules`: when charges apply, cancellations, disputes, existing agreements, bearer meanings, taxes not modeled, `payments_mode="simulated"`. |
| `GET /fee-policies` | Default-scope policy history (active and retired versions). |
| `GET /fee-policy/applicable?organization_id=` | Policy that would price a new booking (organization terms require owner/admin; 401/404 otherwise). |
| `POST /pricing/preview` | `{service_price_paise, origin?, organization_id?}` → evaluation under the active policy. Nothing is created. 503 `NO_ACTIVE_FEE_POLICY`, 422 `CHARGE_CEILING_EXCEEDED`. |
| `POST /pricing/simulate` | `{definition, sample_service_prices_paise[], origin?, for_organization?, include_recorded_bookings?}` → evaluation of an unsaved candidate policy. Re-pricing recorded bookings is staff-only (403). 422 `INVALID_FEE_POLICY`. Nothing is stored. |
| `GET /trust/anchoring` | Whether a TSA is configured, its name/URL, the SHA-256 fingerprint of the pinned trust anchor, what is sent, status meanings. |
| `GET /trust/checkpoints?limit=` | Latest checkpoints: range, Merkle root, digest, canonical body, anchor status. Hashes only. |
| `GET /trust/checkpoints/{index}` | One checkpoint, including the base64 DER RFC 3161 response and nonce when anchored. |

### Booking parties only (customer or worker of the booking; anyone else gets 404)

| Route | Notes |
|---|---|
| `GET /bookings/{id}/financial-record` | All quote versions with acceptances, settlement, ledger transactions with entries and totals, the booking's event list with checkpoint/anchor status. |
| `GET /bookings/{id}/receipt` | Portable receipt (`Content-Disposition: attachment`, `Cache-Control: no-store`). Contains no names, addresses, phone numbers or free text. |
| `POST /bookings/{id}/quote-revisions` | Body `{"service_price_paise": 5000..10000000}`. Only while `requested`. Creates version n+1 priced under the **same fee policy** as the previous version, with the proposer's acceptance, and mirrors it onto the booking. 409 `PRICE_LOCKED` after acceptance; 422 `QUOTE_UNCHANGED`. |
| `POST /bookings/{id}/quotes/{version}/accept` | Customer accepts the current version (workers accept through `/accept`, 409 `USE_BOOKING_ACCEPT`). 409 `QUOTE_VERSION_MISMATCH` for a stale version. |
| `GET /bookings/{id}/repeat-options` | Customer only. Worker's public profile, current rate, free future slots with prices at the current rate, the current fee policy, and the customer's own previous address. Booking again uses `POST /bookings` with `repeat_of_booking_id`. |

### Organization owners/admins only (members and outsiders get 404)

| Route | Notes |
|---|---|
| `GET /organizations/{id}/financial-summary` | Jobs posted, bookings created, completed bookings, agreed spend and platform fees for completed bookings, open agreed spend, and per-booking rows (job, skill, time, status, worker display name, quote version, breakdown). Only bookings from the organization's own job posts. |
| `GET /organizations/{id}/financial-report.csv` | The same rows as CSV (formula-injection safe). |

### Platform staff (users in `platform_reviewers`) only; 403 otherwise

| Route | Notes |
|---|---|
| `GET /trust/integrity` | Full recomputation of the event chain, checkpoints and ledger (`ok`, `problems[]`). |
| `GET /economics/summary` | Recorded demo totals: completed bookings, booking value, simulated fees and payouts, averages, effective fee, legacy vs ledger-backed settlements, reversals. |

## 3. Server-side CLIs (no API equivalent)

- `python -m app.cli.anchor --once | --status | --retry-failed`
- `python -m app.cli.verify_ledger [--json]`
- `python -m app.cli.fee_policy list | show | create --policy-id P --file F [--organization-id U] | activate --policy-id P --version N | bootstrap-example` (the only way to write pricing)
- `python -m app.cli.grant_reviewer` (unchanged)

## 4. Offline verifier

`python3 scripts/verify_receipt.py receipt.json [--tsa-ca ROOT.pem] [--compare older.json] [--json]` — exit 0 externally verified, 3 local only / unavailable, 1 failed, 2 usage error. It never contacts the API or the database.
