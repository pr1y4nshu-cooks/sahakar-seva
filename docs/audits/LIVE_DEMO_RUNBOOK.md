# SAHAKAR–SEVA — Live Demo Runbook

Local hackathon demo. All data is real PostgreSQL/PostGIS data. **Payments are simulated; no money moves.**
Demo sign-in uses the **local development identity** provider, not Supabase (see "Identity" below).

## 1. Start

```bash
cd "/Users/shresthchauhan/Downloads/hackathons/code yudh/sahakar-seva"
sh scripts/dev_up.sh          # docker compose up, alembic upgrade head, idempotent taxonomy seed, health checks
```

`dev_up.sh` pins `POSTGRES_USER/PASSWORD/DB` to the local Docker database for that command only. This matters because the root `.env` currently points `POSTGRES_*`/`DATABASE_URL` at a remote Supabase Postgres, and a plain `docker compose up` would hand those credentials to the local containers.

| Service | URL |
|---|---|
| Web | **http://127.0.0.1:5173** (use `127.0.0.1`; see Troubleshooting) |
| API | http://127.0.0.1:8000 |
| Swagger | http://127.0.0.1:8000/docs |
| DB | `localhost:55432` (`sahakar_seva`) |

## 2. Required environment (root `.env`, git-ignored)

| Variable | Demo value | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Dev identity is refused in any other environment |
| `DEV_AUTH_ENABLED` | `true` | Enables `POST /api/v1/dev-auth/token` |
| `DEV_AUTH_SECRET` | random, ≥ 32 chars | Signs dev tokens. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DEV_AUTH_PASSCODE` | your choice, ≥ 8 chars | Shared demo "password". Do not put it in slides or docs |
| `VITE_AUTH_MODE` | `dev` | Web container uses the dev identity flow |
| `PLATFORM_FEE_BPS` / `PLATFORM_FEE_CAP_BPS` | `1000` / `1500` | 10% pilot fee, 15% cap |

Changes take effect after `docker compose up -d api web` (or re-run `dev_up.sh`).

## 3. Demo accounts

There is no seeded account. Sign in at `/login` with **any** `name@demo.sahakar.test` email and the `DEV_AUTH_PASSCODE` as the password. The account is created on first sign-in. Use a separate browser profile or incognito window per person:

- Worker: `ravi@demo.sahakar.test`
- Customer A: `asha@demo.sahakar.test`
- Customer B / org owner: `meena@demo.sahakar.test`
- Reviewer: `reviewer@demo.sahakar.test`. Sign in once, then grant rights server-side:
  `docker compose exec api python -m app.cli.grant_reviewer --email reviewer@demo.sahakar.test`

## 4. Worker scenario (Ravi)

1. `/earn` → create the worker profile. The status shows **Draft (Not verified)**.
2. Skills: tap **+ Desk Assembly**. It is labelled "Self-declared skill".
3. Service area: **Koramangala**, radius **5 km**, rate **₹350/h** → Save. Customers will only ever see "Koramangala" and a distance.
4. Availability: pick a slot two days ahead, 2 h → **Add slot** (it shows as "Free").
5. Refresh the page. Everything is still there.

## 5. Direct hire (Asha → Ravi)

1. `/hire` → **Find a worker**: Service = Furniture Assembly, location = **HSR Layout**, radius 5 km → **Search workers**.
2. Ravi appears about 4.3 km away, labelled "Not verified — self-declared profile". His free slot shows **₹700** (2 h × ₹350).
3. Choose the slot, enter an address, then **Request booking**.
4. Ravi → `/bookings`: the request shows "address shared after you accept" → **Accept booking**. It is now confirmed and the address is visible.
5. Negative check: search from **Whitefield** with radius 25 km. Ravi does not appear, because Whitefield is outside his 5 km service radius.

## 6. Job posting (Meena → Ravi)

1. Meena → `/hire` → **Post a job**: Desk Assembly, BTM Layout, private address, start time, 3 h, budget ₹1,500 → Publish.
2. Ravi → `/find-work`: the job is listed with locality, distance and budget, but no address → **Apply**.
3. Meena → `/my-jobs` → Applications → **Select**. A booking request is sent.
4. Ravi → `/bookings` → **Accept booking** (same lifecycle as a direct hire). Other applicants become *rejected*.
5. Organization variant: Meena creates a cooperative in `/organizations`. **Post on behalf of** then appears in the job form.

## 7. Earnings and dispute

1. Ravi → **Start work** on the direct booking. Asha → **Confirm work completed**.
2. Both see the breakdown **₹700 = ₹70 platform fee + ₹630 worker payout** under the banner **SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED**. Ravi's `/earn` → Earnings (simulated) shows ₹630.
3. Meena → on the job booking → **Report a problem** → describe it → Open dispute. The booking becomes *disputed*.
4. Reviewer → **Review** (nav) → `/disputes/review` → pick an outcome, write a reason → **Record decision**. Both parties now see the decision and reason. No automatic penalty is applied to the worker.

## 8. Scripted verification (optional, before presenting)

```bash
DEV_AUTH_PASSCODE='<value from .env>' python3 scripts/e2e_demo.py          # 35 API checks, all scenarios
CHROME_ARGS="--host-resolver-rules=MAP localhost 127.0.0.1" \
PLAYWRIGHT_CORE=$HOME/.npm/_npx/af752b90495482d7/node_modules/playwright-core \
DEV_AUTH_PASSCODE='<value>' node scripts/browser_e2e.cjs                    # 13 real-browser checks
```

Each run creates new, uniquely tagged `@demo.sahakar.test` users in the dev DB. It never modifies existing rows.

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Login says "Invalid API key", or a "Dev fixtures active" badge appears | You are hitting a **host** Vite server on `[::1]:5173` (started outside Docker, in Supabase mode with no anon key), not the Docker web container. Use **http://127.0.0.1:5173**, or stop the host `npm run dev`. |
| Blank page | Check the browser console. Empty `VITE_SUPABASE_URL` is now handled (`lib/supabase.ts`). |
| API exits with `invalid interpolation syntax` | Fixed in `alembic/env.py` (passwords containing `%`). If it recurs, check that `POSTGRES_*` points at the local DB; use `dev_up.sh`. |
| API refuses to start: `DEV_AUTH_ENABLED is only permitted…` | Intended behaviour. Set `APP_ENV=development`, or disable dev auth. |
| Search returns 0 workers | The worker needs a skill, a service area **covering the customer's locality**, and (if you set a time) a free slot covering it. |
| `SLOT_IN_USE` when removing a slot | A booking holds it. Decline or cancel the booking first. |
| Port busy | `lsof -nP -iTCP:5173 -sTCP:LISTEN` (same for 8000 and 55432). |
| DB tests | `sh services/api/scripts/create_test_database.sh`, then `TEST_DATABASE_URL=postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_seva_test pytest` in `services/api`. |
