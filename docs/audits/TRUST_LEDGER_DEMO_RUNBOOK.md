# Trust Ledger — Demo Runbook

All demos use the local stack, the local development identity and real PostgreSQL. Payments are simulated. Tampering is done only on copies of downloaded receipts.

## 0. Start

```bash
cd "/Users/shresthchauhan/Downloads/hackathons/code yudh/sahakar-seva"
docker compose build api          # once, after pulling this change (new Python deps)
sh scripts/dev_up.sh              # local Docker DB only; applies 0005; health checks
```

Open **http://127.0.0.1:5173**. External timestamps need, in the root `.env`:

```
TSA_URL=http://timestamp.digicert.com
TSA_NAME=DigiCert Timestamp Authority
TSA_CA_FILE=trust/tsa/digicert-trusted-root-g4.pem
ANCHOR_WORKER_ENABLED=true
```

Without them everything works and receipts show "Local integrity only". Check: `curl -s http://127.0.0.1:8000/api/v1/trust/anchoring`.

Verifier dependencies on the host: `python3 -m pip install -r scripts/requirements-verifier.txt` (or use `services/api/.venv/bin/python`) plus the `openssl` command.

## 1. One-command rehearsal

```bash
export DEV_AUTH_PASSCODE='<value from .env>'
services/api/.venv/bin/python scripts/trust_demo.py          # 29 API checks, Demos 1–6, files in /tmp/sahakar-trust-demo
CHROME_ARGS="--host-resolver-rules=MAP localhost 127.0.0.1" \
PLAYWRIGHT_CORE=$HOME/.npm/_npx/af752b90495482d7/node_modules/playwright-core \
node scripts/trust_browser_e2e.cjs                            # 20 browser checks
```

## 2. Live script (UI)

Accounts: worker `ravi@demo.sahakar.test`, customer `asha@…`, org owner `meena@…`, reviewer `reviewer@…` (grant with `docker compose exec api python -m app.cli.grant_reviewer --email reviewer@demo.sahakar.test`). Password = `DEV_AUTH_PASSCODE`. Use separate browser profiles.

**Demo 1 — Transparent price.** Say first: "amounts use an illustrative example policy; final pricing isn't decided." Ravi: `/earn`, Desk Assembly, Koramangala 5 km, **₹250/h**, a 2 h slot. Asha: `/hire` → Furniture Assembly, HSR Layout → pick the ₹500 slot. Point at "Before you confirm" (priced by the server's active policy): service ₹500, each line item with who bears it, customer total, worker payout ₹450, platform ₹50, processing none, taxes not modeled, policy id/version, cancellation terms, Protected Booking (with the "Not included" line). Request. Both open `/bookings`: identical breakdown, same booking, **Quote v1**, "Customer accepted v1".

**Demo 2 — Completion and ledger.** Ravi: Accept booking → Start work. Asha: Confirm work completed. Evidence shows "Simulated — no real money…" and "ledger balanced". Open **Ledger & event record**: debit ₹500 = credits ₹450 + ₹50; six hash-chained events. Optional proof of immutability:
```bash
docker compose exec db psql -U sahakar -d sahakar_seva -c "UPDATE financial_ledger_entries SET amount_paise=36000"
# ERROR: financial_ledger_entries is append-only: UPDATE is not permitted
```

**Demo 3 — Hidden deduction attempt.** Both download the receipt. Copy Ravi's file and edit `summary.customer_total_paise` → 40000 and `summary.worker_share_paise` → 36000 (or use `/tmp/sahakar-trust-demo/tampered-worker-receipt.json`). `/verify` → upload → **Verification failed** with reasons. CLI:
```bash
services/api/.venv/bin/python scripts/verify_receipt.py /tmp/sahakar-trust-demo/tampered-worker-receipt.json   # exit 1
```

**Demo 4 — Independent verification.** Wait ~20–40 s; the booking shows "External timestamp verified · <time>". Download again, then:
```bash
curl -sO https://cacerts.digicert.com/DigiCertTrustedRootG4.crt
openssl x509 -inform DER -in DigiCertTrustedRootG4.crt -out g4.pem
openssl x509 -in g4.pem -noout -fingerprint -sha256   # 55:2F:7B:DC:…:99:88
services/api/.venv/bin/python scripts/verify_receipt.py receipt.json --tsa-ca g4.pem      # EXTERNALLY TIMESTAMPED AND VERIFIED
services/api/.venv/bin/python scripts/verify_receipt.py receipt.json --compare first-copy.json
```
Without a TSA (or before anchoring) the CLI prints "Local integrity verified — independent timestamp not yet available." Say so; do not imply more.

**Demo 5 — Retention.** Ravi adds another slot. Asha → completed booking → **Book Ravi again** → pick slot → Request repeat booking: new booking, quote v1 at the current rate, worker must accept; the old booking is unchanged. Show history and **Report a problem** with category "Worker payout differs". Reviewer `/disputes/review` → outcome, reason, optional "Record a full reversal" → both parties see the decision; the ledger shows the original and the reversing transaction.

**Demo 6 — Revenue.** Signed out: `/pricing` shows the **active policy record** (locally the illustrative example, clearly labelled "not final pricing"), its line items and bearers, ceiling, examples, history, simulated payments and the planned subscription with no button. `/economics` → **Fee policy simulator**: try a fixed customer fee, a hybrid with min/max, or a waiver → Evaluate → table; "Use average…" feeds the calculator. Nothing is saved. Meena: create a cooperative, post and complete a job for it, then `/organizations` → Booking and spending records → Download CSV; `/my-jobs` → Post a similar job. Reviewer: `/economics` → recorded figures vs scenario calculator (assumptions labelled).

## 2a. Switching the demo to another (illustrative) pricing model

Only if you want to show that pricing is configurable. Existing bookings keep their quotes.

```bash
docker compose exec api python -m app.cli.fee_policy create --policy-id example-fixed-fee --file fee_policies/examples/fixed-customer-booking-fee.json
docker compose exec api python -m app.cli.fee_policy activate --policy-id example-fixed-fee --version 1
docker compose exec api python -m app.cli.fee_policy list
```

A new ₹500 booking then shows customer total ₹525, worker payout ₹500, platform ₹25, on both screens and in the receipt. `scripts/trust_demo.py` assumes the 10% example and exits with code 2 (without checking amounts) under any other policy. To return: create a new version of `illustrative-pilot-example` from `fee_policies/examples/percentage-worker-borne.json` and activate it.

## 3. Operations

```bash
docker compose exec api python -m app.cli.anchor --status
docker compose exec api python -m app.cli.anchor --once
docker compose exec api python -m app.cli.anchor --retry-failed
docker compose exec api python -m app.cli.verify_ledger
```

## 4. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: rfc8785` in API | `docker compose build api && sh scripts/dev_up.sh` |
| Status stays "External timestamp pending" | TSA not configured or unreachable: `anchor --status` shows `last_error`. Booking completion is unaffected. |
| `PROOF_INVALID` | The response failed verification (wrong root, wrong TSA). Check `TSA_CA_FILE`. |
| CLI: "install asn1crypto" | Use `services/api/.venv/bin/python` or install `scripts/requirements-verifier.txt`. |
| Old booking shows "Legacy record" | Expected for pre-0005 bookings; no evidence is invented for them. |
