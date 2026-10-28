# Security and Trust Model

This document states plainly what SAHAKAR–SEVA trusts, what each kind of actor can attempt, and —
most importantly — the exact difference between an **internally consistent local ledger** and an
**independently verified external financial fact**. It directly answers the hidden-payment objection
raised in review.

Scope reminder: this is a hackathon build. Payments are **simulated**. It must not handle real money
or real personal data as-is. See [`PROJECT_CURRENT_STATE.md`](PROJECT_CURRENT_STATE.md) for status.

## 1. The hidden-payment objection, answered directly

> _"You could just write any number into your own database and call it a payment."_

Correct — and the system is built to **not** claim otherwise. Three honest statements define the trust
model:

1. **The ledger proves internal consistency, not payment.** The hash chain, Merkle checkpoints and
   double-entry ledger prove that the agreed price breakdown and its allocations were recorded
   consistently and have not been altered **relative to themselves**. They do not, and cannot, prove
   that money moved.
2. **A party who can rewrite every row can rewrite every hash.** A privileged database operator (or a
   compromised API) could delete the chain and re-emit a new, self-consistent chain with different
   numbers. Internal hashes alone cannot detect this, because the attacker controls all the inputs.
3. **Independent trust requires evidence the operator cannot forge after the fact.** Two such pieces
   exist in this build:
   - an **RFC 3161 timestamp** issued by a third-party TSA over a checkpoint digest, verified against
     a **pinned** CA (`TSA_CA_FILE`). It proves the checkpoint digest existed by the TSA's clock, so a
     later rewrite cannot reproduce the same timestamped digest; and
   - a **participant-held receipt** downloaded earlier. `scripts/verify_receipt.py --compare` detects
     any later divergence between what the customer/worker kept and what the server now says.

What a verified receipt means, stated exactly (from `scripts/verify_receipt.py`): the agreed price
breakdown and allocations were recorded consistently and, if externally timestamped, that the
checkpoint digest existed by the TSA's time. **It does not prove real money changed hands.** Real
proof of payment would require an authenticated event from a regulated payment provider (a verified
webhook signature, provider transaction reference, capture/settlement status), reconciled against the
quote and ledger — a boundary that is designed but not built (see
[`architecture/REVENUE_AND_RETENTION_MODEL.md §7`](architecture/REVENUE_AND_RETENTION_MODEL.md)).

## 2. What the system trusts

- **The API process and its database**, for correctness of business workflows. The ledger reduces,
  but does not eliminate, trust in the operator — that is the purpose of external timestamping and
  participant-held receipts.
- **The pinned TSA root certificate** (`TSA_CA_FILE`), when external anchoring is configured. A
  certificate embedded in a TSA response is never trusted on its own.
- **Supabase**, for production identity, when configured. Tokens are verified server-side on every
  protected request.

## 3. Adversaries and what they can attempt

| Actor | Can attempt | Mitigation in this build |
|---|---|---|
| Malicious customer | Underpay/renege on the agreed price; see a worker's address before accepting; book a slot to block a worker; forge a dispute | Price is a versioned, two-sided accepted quote recorded immutably; address is hidden until the worker accepts; duplicate/overlap requests rejected; disputes go to a human reviewer with attached evidence |
| Malicious worker | Accept overlapping jobs; change the price after acceptance; claim a different payout | DB exclusion constraint prevents overlapping confirmed bookings; price revisions create a new quote version requiring the other party's acceptance; settlement reconciles to the accepted quote or is refused (`SETTLEMENT_MISMATCH`) |
| Compromised API | Emit false events; rewrite history | Detected only with external evidence the attacker cannot forge after the fact: RFC 3161 timestamps and earlier participant receipts (§1) |
| Privileged DB operator | Rewrite rows and hashes to a new self-consistent chain | Same as above — this is explicitly called out as the limit of an internal ledger |
| Public/anonymous user | Scrape personal data via public endpoints | Public endpoints (`/marketplace/overview`, `/jobs/open`, demo receipts) expose locality + distance only, never addresses or personal data; protected endpoints require a verified token |

## 4. Booking authorization and data isolation

- Every booking view resolves the caller's role (customer vs worker) from the row; other users' data
  is not returned, and "not yours" and "not found" return the same response so bookings do not leak by
  probing ids.
- Exact addresses are shown to the worker only after acceptance (`confirmed`/`in_progress`/
  `completed`/`disputed`); otherwise an explanatory reason is returned instead of the address.
- Organization reporting endpoints are restricted to owner/admin membership.
- Reviewer-only dispute endpoints require a server-granted reviewer role
  (`app/cli/grant_reviewer.py`), not a client claim.

## 5. Payment simulation (explicit labelling)

Settlements carry `is_simulated = true` and the constant label
`SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED`. Earnings, booking views and receipts all surface this
label. No code path moves money, and no fake payment-provider identifiers are stored.

## 6. Privacy

- Addresses are collected only for bookings and gated by booking state (§4).
- Public/demo surfaces expose locality and distance, not coordinates or addresses.
- Synthetic demo users use `@demo.sahakar.test` and fictional localities; the seeder refuses to run
  outside a local development database. Demo data is labelled synthetic in the API (`is_synthetic_demo`).

## 7. Development authentication isolation

The local `dev-auth` identity provider exists for demos without Supabase. It is **fail-safe by
configuration**:

- The API refuses to start with `dev-auth` enabled unless `APP_ENV=development`.
- It requires `DEV_AUTH_SECRET` ≥ 32 chars and `DEV_AUTH_PASSCODE` ≥ 8 chars.
- Tokens are rejected whenever `DEV_AUTH_ENABLED` is false, and only `@demo.sahakar.test` emails are
  accepted.

This guarantees production mode cannot silently enable demo identities. `dev-auth` is **not** evidence
that live Supabase login works; that path is configured separately and not exercised by the test suite.

## 8. Secret management

- No secrets are committed. `.env` and `.env.*` are git-ignored (`!.env.example` is kept); `*.pem`,
  `*.key` are ignored, except the **public** TSA root certificate under `services/api/trust/tsa/`.
- `VITE_*` values are embedded in the public browser bundle; only public anon/publishable keys belong
  there — never a service-role key or JWT secret. This is stated in `apps/web/.env.example`.
- Server-only auth values (`SUPABASE_JWT_SECRET`, etc.) are passed to the API container from the root
  `.env`, never to the browser.
- The CA cert is pinned by path and its SHA-256 fingerprint is documented; a cert inside a TSA
  response is never trusted alone.

## 9. CORS and configuration hardening

- `ALLOWED_ORIGINS` must be an explicit list; the wildcard `*` is rejected because credentials are
  allowed.
- A hard fee ceiling of 2000 bps (20%) is enforced in config **and** by a database CHECK; prices that
  would breach a policy's ceiling are refused.
- TSA settings must be provided together (`TSA_URL` + `TSA_CA_FILE`), so anchoring cannot run without a
  pinned verifier.

## 10. Risks still awaiting production controls

- Real payment integration (regulated provider, verified webhooks, reconciliation) — designed, not built.
- Identity/eligibility verification of workers — none; profiles are self-declared.
- Operational controls: rate limiting, abuse/fraud detection, monitoring, backups, key rotation.
- External anchoring is off by default; without it, receipts are "local integrity only".
- Regulatory/tax treatment (GST, payment-aggregator rules) — not addressed.
- Dependency and supply-chain hardening beyond pinned version ranges.

Reporting process: see [`../SECURITY.md`](../SECURITY.md).
