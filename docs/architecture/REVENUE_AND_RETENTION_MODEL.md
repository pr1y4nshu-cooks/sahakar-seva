# Revenue and Retention Model

**Status:** hypotheses for a pilot. Nothing here is validated market evidence.

## 1. What is free

Registration, declaring skills, browsing and applying to jobs, posting jobs, receipts, disputes. Shown on `/pricing`.

## 2. Revenue line 1 — transparent, configurable booking charges (implemented, simulated)

**Final commercial pricing has not been decided.** The platform does not have a fixed commission. It has a versioned pricing engine (`fee_policies`, migration 0006) that supports:

- percentage charges, fixed charges and hybrids (percentage + fixed), with optional minimum and maximum per charge;
- an explicit bearer per charge: customer (added to the total), worker (deducted from payout), business (billed to the organization, organization bookings only), or platform (absorbed; modeled processing only);
- promotional waivers (time window, optional service-price limit), recorded with the waived amount;
- organization-specific terms (one active policy per organization), the hook for future business plans (`subscription_plan_code`; no billing exists);
- a per-policy charge ceiling, never above the 20% platform limit; prices that would breach it are refused.

Every booking keeps the policy, version, definition hash and line items of its accepted quote; changing the active policy affects only new quotes. `/pricing` renders the active policy record; nothing is hardcoded. Charges are recorded only on completion; cancellations record none; disputes may lead to a recorded reversal.

**Local development currently runs the "Illustrative pilot example — 10% worker-borne platform fee (NOT final pricing)".** It exists so the demo can run. The ₹500 = ₹450 + ₹50 and ₹700 = ₹630 + ₹70 figures in tests and demos come from that example. Other illustrative definitions are in `services/api/fee_policies/examples/` (fixed customer fee, hybrid split with limits, launch waiver, organization terms).

**Evaluating sustainability before adopting rates:** `/economics` has a policy simulator that sends a candidate definition to `POST /pricing/simulate` (the same engine bookings use). It shows the customer total, worker payout and platform charge for sample prices, flags refusals, and — for platform staff — re-prices recorded completed bookings hypothetically. Its average platform charge can feed the scenario calculator. Nothing is stored or activated by simulating.

## 3. Revenue line 2 — business tools subscription (planned, not available)

Possible tools: team-level service management, consolidated multi-site reports, scheduled repeat work. Labelled **"Planned — not currently available"**. There is no billing code, plan, Subscribe or Pay button. No subscription price has been set; any figure is an illustrative calculator input.

What organizations get today, free: booking/spending summary and CSV for their own job-post bookings (`/organizations`), and "Post a similar job" templates (`/my-jobs` → prefilled `/hire` form, reviewed before publishing).

## 4. Reducing bypass through value (not restriction)

Customers and workers meet in person; the platform does not try to stop contact. It makes repeat on-platform booking more useful than going direct:

| Feature | Status |
|---|---|
| Agreed price record both parties see, with version and acceptance times | Implemented |
| Scheduling, slot conflicts prevented, booking history | Implemented (MVP) |
| Balanced allocation record on completion | Implemented (simulated) |
| Downloadable, independently verifiable receipts | Implemented; RFC 3161 when TSA configured |
| Dispute submission with attached financial evidence; human reviewer decisions | Implemented |
| "Book again" with the same worker: current rate, new slot, new quote, worker consent | Implemented |
| Organization records and CSV | Implemented |

Explicitly not offered: insurance, guaranteed refunds, guaranteed payouts, replacement workers, identity verification, bank-confirmed payments. The "SAHAKAR Protected Booking" panel lists both columns.

## 5. Unit economics

`/economics` has two separated parts:

1. **Recorded figures** (staff only, `GET /economics/summary`): completed bookings, booking value, simulated fees and payouts, averages, effective fee, legacy vs ledger-backed, reversals. These are local demo records created by test scripts — not market data and not cash revenue.
2. **Scenario calculator** (anyone, browser only): bookings, average value, average platform charge per booking (from the simulator or typed), payment processing %, support cost, CAC, new customers, dispute rate and cost, fixed costs, **assumed** leakage, illustrative subscribers and price. Formula shown on the page. No leakage rate has been measured.

## 6. Assumptions that still need validation

Which pricing model and level customers and workers accept; real payment-processing costs with a regulated provider; dispute frequency and review cost; acquisition cost; actual off-platform leakage; whether organizations would pay for tools; legal/tax treatment (GST, payment aggregator rules).

## 7. Future payment-provider boundary

Not built in this sprint. A future record would hold: provider, provider transaction reference, booking reference, reported amount, currency, an authenticated provider event (verified webhook signature), capture status, settlement/payout status, and verification time — reconciled against the agreed quote and ledger. Browser-submitted amounts would never count as payment evidence, and no fake provider ids are stored. A regulated provider is required; no escrow, wallet or crypto custody.
