# Trust Ledger — Security and Integrity Tests

All database tests run against the isolated `sahakar_seva_test` database (`TEST_DATABASE_URL`), inside rolled-back transactions. Tests that must COMMIT (`test_trust_concurrency.py`, `test_booking_concurrency.py`) delete exactly their own rows afterwards; the session leak check (now covering the six new tables) fails the run otherwise. No test uses a real TSA: external timestamping is tested against an isolated test TSA (`tests/tsa_double.py`: throw-away CA + TSA cert, responses signed by `openssl ts -reply`).

New test files: `tests/test_trust_crypto.py`, `tests/test_trust_timestamping.py`, `tests/db/test_trust_ledger.py`, `tests/db/test_trust_concurrency.py`, `tests/db/test_migration_0005.py` (66 tests), and `apps/web/src/trust.test.tsx` (19 tests).

## Configurable pricing (0006) → evidence

New files: `tests/test_pricing_engine.py` (82), `tests/db/test_fee_policies.py` (9), `tests/db/test_migration_0006.py` (3); web `trust.test.tsx` gained hybrid-receipt and policy-rendering cases. All policies in tests are illustrative inputs.

| Requirement | Test(s) |
|---|---|
| Percentage / fixed / hybrid / min-max | `test_percentage_worker_borne_example`, `test_fixed_customer_borne_fee_is_added_on_top`, `test_hybrid_with_min_and_max`, `test_fixed_customer_fee_booking_end_to_end`, `test_hybrid_waiver_and_platform_absorbed_charge_verify` |
| Promotional waivers recorded | `test_promotional_waiver_is_recorded_not_hidden`, hybrid E2E test |
| Explicit bearers (customer, worker, business, platform) | `test_split_bearers_and_processing_charge`, `test_business_borne_applies_only_to_organization_bookings`, `test_business_borne_fee_uses_organization_terms`, `test_platform_absorbed_processing_does_not_change_either_party` |
| Accepted breakdown immutable; policy change never re-prices | `test_policy_change_never_reprices_existing_bookings` (requested + revised + confirmed booking keeps old policy; new booking uses new), existing price-guard tests |
| Same agreement for both parties incl. policy id/version | `test_fixed_customer_fee_booking_end_to_end`, web `customer and worker see identical…`, `shows service price, each line item…`, trust_demo, browser E2E |
| Integer paise + reconciliation | `test_independent_verifier_engine_agrees_and_every_model_balances` (64 combos), DB CHECKs in `test_safety_ceilings_still_in_place` |
| Ledger/receipts/anchoring for every model | hybrid & business E2E tests (balanced entries, verifier pass, tamper fail), `test_anchoring_and_integrity_cover_policy_events` |
| Constraints not weakened | `test_safety_ceilings_still_in_place`, `test_ceiling_refuses_rather_than_clamps`, `test_ceiling_refusal_creates_nothing`, `test_invalid_policies_rejected` (9 cases incl. >20%, tax, platform-borne fee) |
| Policy versions immutable, single active | `test_policy_rows_are_immutable_and_single_active` |
| No active policy fails closed | `test_no_active_policy_fails_closed` |
| Pricing page shows the active policy, nothing hardcoded | web `pricing page renders whatever policy the backend says is active` (asserts no "10%"), `test_public_fee_policy_reports_the_active_policy_record`, browser E2E |
| Sustainability evaluation without activation | `test_preview_and_simulator` (nothing stored; staff-only recorded re-pricing), trust_demo, browser E2E |
| Migration additive and reversible | `test_migration_0006.py` |

Pre-existing test changes for 0006: head constants → `0006`; `test_migration_0005` upgrades to its own revision; DB fixture `api` activates the illustrative example policy inside the rolled-back transaction; the fee-policy response test was rewritten for the new shape; quote-revision tests send `service_price_paise`; the forged-receipt helper also forges the service price (the stronger verifier otherwise catches it earlier).

## Requirement → evidence (trust ledger, 0005)

| # | Requirement | Test(s) |
|---|---|---|
| 1 | ₹500 = ₹450 + ₹50 | `test_both_parties_see_one_identical_agreement[25000-…]`, `test_completion_posts_one_balanced_ledger_transaction` |
| 2 | ₹700 = ₹630 + ₹70 | `test_both_parties_see_one_identical_agreement[35000-…]`, `test_job_selection_creates_quote…`, existing `test_direct_hire_full_lifecycle…` |
| 3 | Debits = credits | `test_completion_posts_one_balanced_ledger_transaction`, `test_real_commit_of_completion_passes_deferred_balance_check` (real COMMIT) |
| 4 | Negative values rejected | `test_negative_invalid_and_over_cap_prices_rejected` (service, DB CHECK, API 422) |
| 5 | Fee ceiling enforced | same test + existing `test_fee_cap_and_rounding`; `test_fee_ceiling_check_still_applies…` |
| 6 | Invalid snapshot rejected | `test_negative_invalid_and_over_cap_prices_rejected` (allocation CHECK) |
| 7 | No duplicate posting | `test_no_duplicate_ledger_posting` (idempotent service; UNIQUE key and settlement) |
| 8 | Settlement/ledger atomicity | `test_settlement_and_ledger_are_atomic` (forced ledger failure → no settlement, no events, still `in_progress`) |
| 9 | Ledger tampering rejected/detected | `test_finalized_ledger_and_events_cannot_be_edited_or_unbalanced`, `test_real_commit…` (unbalanced insert refused at COMMIT), `test_database_chain_verifies_and_detects_tampering` |
| 10 | Adjustments cannot rewrite accepted quotes | `test_revised_quote_needs_renewed_acceptance_and_never_rewrites_history`, `test_fee_ceiling_check_still_applies_and_price_guard…` |
| 11 | Deterministic canonical serialization | `test_canonical_serialization_is_deterministic_and_rfc8785`, `test_verifier_fallback_canonicalization_equals_jcs…`, `test_profile_rejects_ambiguous_values`, web `canonicalizes like RFC 8785` |
| 12 | Hash-chain continuity | `test_event_hash_byte_layout_and_domain_separation`, `test_hash_chain_continuity_detects_edit_and_reorder` |
| 13–15 | Changed customer amount / worker payout / fee detected | `test_database_chain_verifies_and_detects_tampering`, `test_offline_verifier_accepts_genuine_and_rejects_tampered_receipts`, web `detects a tampered …` |
| 16 | Removed / reordered events | `test_database_chain_verifies…` (sequence gap + checkpoint range + Merkle), `test_hash_chain_continuity…`, CLI "removed event" case, `--compare` case |
| 17 | Concurrent appends | `test_concurrent_event_appends_get_distinct_sequences_and_one_chain` (two threads, overlapping transactions) |
| 18 | Checkpoint recomputation | `test_checkpoint_recomputes_and_body_is_immutable`, `test_merkle_*`, `test_checkpoint_digest_recomputation…` |
| 19 | Offline verifier passes genuine proof | `test_offline_verifier_accepts_genuine…` (LOCAL), `test_external_anchor_verified_only_with_genuine_evidence` (EXTERNAL with test-TSA root) |
| 20 | Offline verifier fails tampered proof | `test_offline_verifier_accepts_genuine_and_rejects_tampered_receipts` (11 cases incl. both hidden-deduction variants, fully re-hashed forgery caught by `--compare`) |
| 21 | False/unsigned timestamp rejected | `test_trust_timestamping.py` (other CA, forged signature, wrong digest, wrong nonce, junk, no anchor, HTTP 200 non-TSR), receipt cases with a foreign-TSA token and a claim without token |
| 22 | TSA unavailable never "externally verified" | `test_unavailable_or_lying_tsa_never_yields_externally_anchored` (ANCHOR_PENDING → ANCHOR_FAILED, bounded retries; lying TSA → PROOF_INVALID), web `never shows an external-timestamp claim…` |
| 23 | Direct hiring | existing `test_direct_hire_full_lifecycle…`, E2E |
| 24 | Job posting / selection | existing tests + `test_job_selection_creates_quote…` |
| 25 | Booking conflicts | existing `test_booking_concurrency.py`, double-booking tests |
| 26 | Settlement uniqueness | existing tests (UNIQUE booking_id) + `test_no_duplicate_ledger_posting` |
| 27 | Dispute authorization | existing `test_dispute_requires_independent_authorised_reviewer`, `test_financial_dispute_with_reviewer_reversal_is_traceable` (party-reviewer 403) |
| 28 | Organization role isolation | existing `test_organization_job_permissions`, `test_organization_financial_summary_is_owner_admin_only` |
| 29 | Repeat booking with consent | `test_repeat_booking_creates_a_fresh_booking_needing_worker_consent` |
| 30 | APIs and migrations compatible | all 152 pre-existing tests unchanged in assertions; `test_migration_0005.py` (rows preserved, no backfill, clean downgrade); `test_models_match_migrated_schema` |
| 31 | Both participants see identical values | web `customer and worker see identical authoritative values`; browser E2E |
| 32 | Receipts download | web `downloads the receipt from the API as a file`; browser E2E (real download) |
| 33 | Verification errors shown | web `shows verification errors clearly`; browser E2E |
| 34 | No false anchor claims | web anchor test; browser verifier never claims external |
| 35 | Pricing page = backend | web `pricing page shows the backend policy values` (12% mock); browser E2E vs live `/fee-policy`; `test_public_fee_policy_matches_backend_configuration` |
| 36 | Simulated earnings wording | web `describes settlements as simulated…` |
| 37 | Business metrics real or labelled | `test_economics_is_staff_only_and_uses_recorded_values`, org summary test, web scenario test |

Other security checks: receipts contain no address/email/notes (`test_offline_verifier…`); public checkpoints contain no booking ids or emails (`test_public_checkpoints_expose_hashes_only`); stranger gets 404 for receipts, financial records, repeat options and quote revisions; economics and integrity endpoints are staff-only; CSV neutralises formula injection; TSA request contains only version, imprint, nonce, certReq (`test_request_contains_only_the_digest_and_nonce`).

## Changes to pre-existing tests (none weaken an assertion)

- Head-revision constants updated from `0004_marketplace_core` to `0005_transparency_and_trust` (`test_migration_0003.py`, `test_migration_and_integrity.py`); `test_migration_0004.py` now upgrades to its own revision explicitly instead of `head`.
- `tests/db/conftest.py` leak check extended to the six new tables.
- `test_booking_concurrency.py` cleanup also removes the trust rows its accept now creates.
- `scripts/e2e_demo.py` check "database rejects a fee above the 20% ceiling" now also accepts the new price-guard rejection (the update targets a confirmed booking, which the guard blocks before the CHECK runs). The CHECK itself is now asserted directly by `test_fee_ceiling_check_still_applies…`.

## Defects found by these tests during the sprint

1. The deferred ledger-balance trigger referenced `NEW.transaction_id` from a function shared by two tables; PL/pgSQL failed at runtime. Ordinary tests never commit, so only a forced `SET CONSTRAINTS ALL IMMEDIATE` exposed it. Split into per-table wrappers before any dev-DB migration; `test_real_commit_of_completion…` now commits for real.
2. `test_migration_0005` first ran migrations against the shared `public` schema of the test DB (search_path order). Fixed to follow the scratch-schema pattern; leaked rows were removed from the test DB only.
3. Host test runs picked up the developer's TSA settings from `.env`; trust tests now start from "no TSA" explicitly.
