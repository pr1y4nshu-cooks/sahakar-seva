# Business and Product Model

**Status: hypotheses for a pilot.** Nothing here is validated market evidence, and no revenue has been
collected. The detailed design behind this summary is in
[`architecture/REVENUE_AND_RETENTION_MODEL.md`](architecture/REVENUE_AND_RETENTION_MODEL.md).

## 1. The two-sided marketplace bypass problem

Marketplaces that connect local customers with local service workers face **disintermediation**: once
the two sides meet, they can transact off-platform and the marketplace earns nothing. Hiding contact
details (phone numbers, last names) is a common reaction, but it does not solve bypass — people simply
exchange details during the in-person visit, and heavy restriction degrades the experience for honest
users. SAHAKAR–SEVA does not try to prevent contact.

## 2. The approach: reduce bypass by adding value, not restriction

The platform makes **repeat on-platform booking more useful than going direct**, through features that
are hard to reproduce over a private phone call:

| Feature | Status in the current build |
|---|---|
| A versioned agreed-price record both parties see, with acceptance times | Implemented |
| Scheduling with slot-conflict prevention and booking history | Implemented (MVP) |
| Balanced allocation record produced on completion | Implemented (simulated) |
| Downloadable, independently verifiable receipts | Implemented; externally timestamped when a TSA is configured |
| Dispute submission with attached financial evidence, resolved by a human reviewer | Implemented |
| "Book again" with the same worker (current rate, new slot, new quote, worker consent) | Implemented |
| Organization booking/spending summary and CSV export | Implemented |

Explicitly **not** offered: insurance, guaranteed refunds, guaranteed payouts, replacement workers,
identity verification, or bank-confirmed payments.

## 3. Revenue model (truthful)

Registration, declaring skills, browsing/applying/posting jobs, receipts and disputes are **free**
(shown on `/pricing`).

**There is no fixed commission.** The platform has a versioned, configurable pricing engine
(`fee_policies`, migration `0006`) supporting percentage, fixed and hybrid charges, an explicit bearer
per charge (customer / worker / business / platform), optional min/max, promotional waivers, and
organization-specific terms — all under a hard 20% ceiling. Every booking records the exact policy,
version and line items of its accepted quote.

> The earlier **10% figure is an illustrative pilot example only**, labelled in code as _"Illustrative
> pilot example … (NOT final pricing)"_. Local development activates it so the demo can run (e.g.
> ₹700 = ₹630 payout + ₹70 fee). It is **not** a committed or permanent revenue model. Final pricing
> has not been decided and requires real customer testing.

A **business-tools subscription** is **planned, not available**: there is no billing code, no plan, and
no subscribe/pay button. Any subscription price shown anywhere is an illustrative calculator input, not
collected revenue.

## 4. Unit economics (illustrative calculator, not results)

`/economics` has two clearly separated parts:

1. **Recorded figures** (staff only): totals over completed bookings in the local demo database —
   created by test/seed scripts, **not market data and not cash revenue**.
2. **Scenario calculator** (browser-only): the reviewer types assumptions (bookings, average value,
   average platform charge, processing %, support cost, CAC, dispute rate/cost, fixed costs, assumed
   leakage, illustrative subscribers/price). The formula is shown on the page. Nothing is stored.

No off-platform leakage rate, acquisition cost, or dispute frequency has been measured.

## 5. Differentiation

Managed-service marketplaces typically set prices centrally, take a fixed cut, and own the customer
relationship. SAHAKAR–SEVA's distinguishing choices in this build are a **two-sided, versioned price
agreement** with per-party fee bearers, and **portable, independently verifiable receipts** rather than
an opaque internal statement. These are design choices demonstrated in code; they are not claims about
any specific competitor's internal practices.

## 6. Assumptions that still need validation

Which pricing model and level customers and workers will accept; real payment-processing costs with a
regulated provider; dispute frequency and review cost; customer acquisition cost; actual off-platform
leakage; whether organizations would pay for tools; and legal/tax treatment (GST, payment-aggregator
rules). Each needs real customer testing before any number here should be treated as a projection.
