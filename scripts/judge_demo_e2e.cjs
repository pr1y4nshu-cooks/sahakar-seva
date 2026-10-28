// Judge-demo browser verification against the REAL local stack (web :5173 -> API :8000 -> Docker PostgreSQL).
//   PLAYWRIGHT_CORE=<playwright-core path> DEV_AUTH_PASSCODE=... CHROME_ARGS="--host-resolver-rules=MAP localhost 127.0.0.1" node scripts/judge_demo_e2e.cjs
// Requires the demo dataset (python3 scripts/seed_demo.py --apply). Seeded personas are only READ; scenarios that create
// data (repeat booking, job application) use fresh, tagged @demo.sahakar.test identities so the dataset stays pristine.
const fs = require('fs'); const path = require('path'); const { spawnSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const ROOT = path.resolve(__dirname, '..');
const WEB = process.env.WEB || 'http://localhost:5173', API = process.env.API || 'http://localhost:8000/api/v1', PASS = process.env.DEV_AUTH_PASSCODE;
const TAG = Math.random().toString(36).slice(2, 8), OUT = '/tmp/sahakar-judge-demo'; fs.mkdirSync(OUT, { recursive: true });
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PY = fs.existsSync(`${ROOT}/services/api/.venv/bin/python`) ? `${ROOT}/services/api/.venv/bin/python` : 'python3';
const ROOT_PEM = `${ROOT}/services/api/trust/tsa/digicert-trusted-root-g4.pem`;
const OPENSSL = ['/opt/homebrew/bin/openssl', '/usr/local/opt/openssl@3/bin/openssl'].find(fs.existsSync) || 'openssl';
const res = []; const check = (n, ok, d = '') => { res.push(!!ok); console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${n}${d ? ' — ' + d : ''}`); };
const num = (t) => Number(String(t).replace(/[^0-9.]/g, ''));
const ravi1 = (page) => page.locator('div.rounded-3xl', { has: page.locator('h3', { hasText: /^Ravi Kumar$/ }) }).first();
async function api(method, p, tok, body) { const r = await fetch(API + p, { method, headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: 'Bearer ' + tok } : {}) }, body: body ? JSON.stringify(body) : undefined }); const t = await r.text(); return [r.status, t ? JSON.parse(t) : {}]; }
const tok = async (email, name) => (await api('POST', '/dev-auth/token', null, { email, passcode: PASS, display_name: name }))[1].access_token;
const em = (l) => `${l}@demo.sahakar.test`;
async function signIn(page, email) { await page.goto(`${WEB}/login`); await page.getByLabel('Email').fill(email); await page.getByLabel('Password', { exact: true }).fill(PASS); await page.getByRole('button', { name: 'Sign in' }).click(); await page.waitForURL('**/dashboard', { timeout: 20000 }); }
const iso = (d, h) => { const x = new Date(); x.setUTCDate(x.getUTCDate() + d); x.setUTCHours(h, 0, 0, 0); return x.toISOString(); };
const settle = async (page) => { await page.waitForLoadState('networkidle'); await page.waitForTimeout(400); };
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
const cli = (script, args) => spawnSync(PY, [`${ROOT}/scripts/${script}`, ...args], { encoding: 'utf8', env: { ...process.env, OPENSSL_BIN: OPENSSL } });

(async () => {
  if (!PASS) { console.error('Set DEV_AUTH_PASSCODE'); process.exit(2); }
  const args = process.env.CHROME_ARGS ? [process.env.CHROME_ARGS] : [];
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args });
  const ctx = (vp) => browser.newContext({ viewport: vp, acceptDownloads: true });
  const desk = await (await ctx({ width: 1280, height: 900 })).newPage();
  const mob = await (await ctx({ width: 390, height: 844 })).newPage();
  const asha = await (await ctx({ width: 1280, height: 900 })).newPage(), ravi = await (await ctx({ width: 1280, height: 900 })).newPage();
  try {
    console.log('Preconditions');
    const [, ov0] = await api('GET', '/marketplace/overview'); check('demo dataset is present (run scripts/seed_demo.py --apply first)', ov0.is_demo_dataset);

    console.log('\nScenario A — populated marketplace (signed out, desktop)');
    await desk.goto(`${WEB}/`); await desk.getByTestId('home-counts').waitFor({ timeout: 15000 });
    const [, ov] = await api('GET', '/marketplace/overview');
    check('home counts equal the API sample-dataset counts, with the database total disclosed', num(await desk.getByTestId('count-workers').innerText()) === ov.sample_data_share.workers && num(await desk.getByTestId('count-categories').innerText()) === ov.service_categories && num(await desk.getByTestId('count-jobs').innerText()) === ov.sample_data_share.open_jobs && /older test worker profile/.test(await desk.getByTestId('home-db-total').innerText()), `${ov.sample_data_share.workers}/${ov.service_categories}/${ov.sample_data_share.open_jobs}`);
    check('home labels the dataset "Demo marketplace — sample data" and denies it is traction', /Demo marketplace — sample data/.test(await desk.getByTestId('home-demo-label').innerText()) && /not platform traction/.test(await desk.getByTestId('home-demo-label').innerText()));
    check('site-wide demo banner present', (await desk.getByTestId('demo-banner').innerText()).includes('payments are simulated'));
    await desk.goto(`${WEB}/hire`); await desk.locator('div.rounded-3xl h3').first().waitFor({ timeout: 20000 });
    const defaultCards = await desk.locator('div.rounded-3xl h3').count();
    check('Hire shows seeded workers immediately in the default locality (no clicks)', defaultCards >= 3 && (await desk.getByTestId('sample-only').count()) === 1, `${defaultCards} workers; locality preselected`);
    await settle(desk);
    await desk.locator('#h-cat').selectOption({ label: 'Furniture Assembly' }); await desk.getByRole('button', { name: /Search workers/ }).click();
    await desk.getByRole('heading', { name: /matching worker/ }).waitFor(); await settle(desk);
    await desk.waitForFunction(() => document.body.innerText.includes('Ravi Kumar'), null, { timeout: 15000 });
    const names = await desk.locator('div.rounded-3xl h3').allInnerTexts();
    check('filter by Furniture Assembly returns furniture workers incl. Ravi Kumar, with rates and slots', names.includes('Ravi Kumar') && (await ravi1(desk).innerText()).includes('/hour') && (await ravi1(desk).locator('button[aria-pressed]').count()) >= 1, names.join(', '));
    check('restricted test workers never appear in search', !names.some((n) => /Restricted Test/.test(n)));
    check('every card is honestly labelled (not verified / self-declared)', (await ravi1(desk).innerText()).includes('Not verified') && (await ravi1(desk).innerText()).includes('Self-declared skills'));
    await desk.locator('#h-cat').selectOption({ label: 'Gardening' }); await desk.getByRole('button', { name: /Search workers/ }).click(); await desk.waitForFunction(() => /Manjunath|Shanti|Prakash|Zainab/.test(document.body.innerText), null, { timeout: 15000 }); await settle(desk);
    const gnames = await desk.locator('div.rounded-3xl h3').allInnerTexts(); check('switching to Gardening changes the results (filters work)', !gnames.includes('Ravi Kumar') && gnames.length > 0, gnames.join(', '));
    await desk.goto(`${WEB}/find-work`); await desk.getByTestId('public-job-card').first().waitFor({ timeout: 15000 });
    const jobCount = await desk.getByTestId('public-job-card').count(); const [, apiJobs] = await api('GET', '/jobs/open?sample_only=true');
    check('Find Work (signed out) lists the persisted open jobs, with title/skill/locality/budget/schedule', jobCount === Math.min(apiJobs.length, 60) && jobCount >= 8, `${jobCount} cards`);
    const firstJob = await desk.getByTestId('public-job-card').first().innerText();
    check('job cards show budget, schedule, skill and a sign-in-to-apply action, and no private address', /₹/.test(firstJob) && /total budget/.test(firstJob) && /Sign in to apply/.test(firstJob) && !/Sample Apartments|Flat |House /.test(firstJob));
    await desk.locator('#pj-skill').selectOption({ label: 'Desk Assembly' }); await desk.waitForTimeout(1200);
    const filtered = await desk.getByTestId('public-job-card').allInnerTexts(); check('job-board skill filter works', filtered.length > 0 && filtered.length < jobCount && filtered.every((t) => t.includes('Desk Assembly')), `${filtered.length} of ${jobCount}`);
    await desk.screenshot({ path: `${OUT}/find-work-desktop.png`, fullPage: true });

    console.log('\nScenario B — one agreement, two accounts');
    await signIn(asha, em('asha')); await signIn(ravi, em('ravi'));
    const at = await tok(em('asha'), 'Asha'), rt = await tok(em('ravi'), 'Ravi');
    const [, ab] = await api('GET', '/bookings/mine', at); const headline = ab.find((b) => b.status === 'completed' && b.agreement.service_price_paise === 50000 && b.worker_display_name === 'Ravi Kumar' && b.is_synthetic_demo);
    check('Asha has the seeded completed ₹500-service booking with Ravi', !!headline, headline && headline.id.slice(0, 8));
    await asha.goto(`${WEB}/bookings`); await ravi.goto(`${WEB}/bookings`);
    const ac = asha.locator('div.rounded-3xl', { hasText: 'Synthetic demo record' }).filter({ hasText: 'Ravi Kumar' }).filter({ hasText: 'completed' }).first(); await ac.waitFor({ timeout: 20000 });
    const rc = ravi.locator('div.rounded-3xl', { hasText: 'Synthetic demo record' }).filter({ hasText: 'Asha Menon' }).filter({ hasText: 'completed' }).first(); await rc.waitFor({ timeout: 20000 });
    const read = async (c) => ({ total: await c.getByTestId('amount-customer-total').innerText(), worker: await c.getByTestId('amount-worker-share').innerText(), fee: await c.getByTestId('amount-platform-fee').innerText(), v: await c.getByTestId('quote-version').innerText(), ref: await c.getByTestId('policy-ref').innerText() });
    const A = await read(ac), R = await read(rc);
    check('customer and worker screens show identical total / worker amount / platform charges / quote version / policy ref', JSON.stringify(A) === JSON.stringify(R), `${A.total} / ${A.worker} / ${A.fee} / ${A.v}`);
    const [, rv] = await api('GET', `/bookings/${headline.id}`, rt);
    check('both sides read the same booking id and quote id from the server', rv.id === headline.id && rv.agreement.quote_id === headline.agreement.quote_id);
    check('service price ₹500 → customer ₹500, worker ₹450, platform ₹50 under the labelled example policy', A.total === '₹500' && A.worker === '₹450' && A.fee === '₹50' && /Illustrative example policy/.test(A.ref));
    check('synthetic provenance is stated on the seeded booking', /Synthetic demo record/.test(await ac.innerText()));
    check('dispute access and repeat-booking entry are present on the completed booking', (await ac.getByRole('button', { name: 'Report a problem' }).count()) === 1 && (await ac.getByRole('button', { name: /Book Ravi Kumar again/ }).count()) === 1);

    console.log('\nScenario C — Transaction Transparency (ledger explorer)');
    await ac.getByRole('link', { name: /Transaction transparency/ }).click(); await asha.waitForURL(`**/bookings/${headline.id}/transparency`);
    await asha.getByTestId('transaction-transparency').waitFor({ timeout: 15000 });
    check('Agreement view: quote v1, totals, bearer, acceptances', (await asha.getByTestId('exp-total').innerText()) === '₹500' && (await asha.getByTestId('exp-worker').innerText()) === '₹450' && (await asha.getByTestId('exp-quote-version').innerText()) === 'v1' && (await asha.getByTestId('acceptance').count()) === 2 && /borne by worker/.test(await asha.getByTestId('view-agreement').innerText()));
    await asha.getByRole('tab', { name: 'Ledger' }).click();
    const rows = await asha.getByTestId('ledger-row').allInnerTexts();
    check('Ledger view: readable accounts, debits ₹500 = credits ₹500, Balanced, SIMULATED', rows.length === 3 && (await asha.getByTestId('total-debits').innerText()) === '₹500' && (await asha.getByTestId('total-credits').innerText()) === '₹500' && /^Balanced/.test(await asha.getByTestId('reconciliation').innerText()) && /SIMULATED/.test(await asha.getByTestId('view-ledger').innerText()), rows.map((r) => r.replace(/\s+/g, ' ')).join(' | '));
    await asha.getByRole('tab', { name: 'Cryptographic proof' }).click();
    check('Proof view: the chain of events with previous/current hash and checkpoint', (await asha.getByTestId('proof-event').count()) === 6 && (await asha.getByTestId('proof-checkpoint').count()) >= 1);
    check('Proof view: external timestamp status comes from evidence (verified token contains the checkpoint hash)', /External timestamp verified/.test(await asha.getByTestId('anchor-line').first().innerText()) && /contains this checkpoint hash/.test(await asha.getByTestId('anchor-line').first().innerText()));
    await asha.waitForFunction(() => /recompute correctly/.test(document.body.innerText), null, { timeout: 15000 });
    check('Proof view: local verification actually ran in the browser', /Local verification: hashes, chain links, Merkle proofs and amounts recompute correctly/.test(await asha.getByTestId('local-result').innerText()));
    await asha.getByRole('tab', { name: 'Verification' }).click();
    check('Verification view states what is and is not proven; says local, not external', /Local integrity verified/.test(await asha.getByTestId('verify-statement').innerText()) && !/externally (verified|timestamped)/i.test(await asha.getByTestId('verify-statement').innerText()) && /does not prove/i.test(await asha.getByTestId('view-verification').innerText()));
    await asha.screenshot({ path: `${OUT}/explorer-desktop.png`, fullPage: true });

    console.log('\nScenario D — export the receipt; verify with no database or API');
    const [dl] = await Promise.all([asha.waitForEvent('download'), asha.getByRole('button', { name: 'Download receipt' }).click()]);
    const receiptPath = `${OUT}/receipt-asha.json`; await dl.saveAs(receiptPath);
    const rec = JSON.parse(fs.readFileSync(receiptPath, 'utf8')); check('downloaded receipt matches the booking', rec.summary.booking_id === headline.id && rec.summary.customer_total_paise === 50000);
    const v = cli('verify_receipt.py', [receiptPath, '--tsa-ca', ROOT_PEM, '--json']); const vj = JSON.parse(v.stdout);
    check(`offline CLI: ${vj.result} (exit ${v.status}; ${vj.events_externally_timestamped}/${vj.events_total} events externally timestamped by a verified DigiCert token)`, vj.result === 'EXTERNALLY TIMESTAMPED AND VERIFIED' && v.status === 0);
    const vloc = JSON.parse(cli('verify_receipt.py', [receiptPath, '--json']).stdout); check('same file with no trust anchor supplied is only LOCAL (never claims external)', vloc.result === 'LOCAL INTEGRITY VERIFIED');

    console.log('\nScenario E — tamper detection on COPIES (nothing authoritative changes)');
    const [, before] = await api('GET', `/bookings/${headline.id}/financial-record`, at);
    for (const [mode, extra] of [['display', ['--worker-share', '36000']], ['payload', ['--worker-share', '36000']], ['rehash', ['--worker-share', '36000']]]) {
      const out = `${OUT}/altered-${mode}.json`; cli('tamper_receipt.py', [receiptPath, '--mode', mode, ...extra, '--out', out]);
      const o = JSON.parse(cli('verify_receipt.py', [out, '--tsa-ca', ROOT_PEM, '--json']).stdout);
      check(`CLI tamper (${mode}: worker ₹450 → ₹360) → ${o.result}`, o.result === 'VERIFICATION FAILED', o.failures[0] && o.failures[0].check);
    }
    cli('tamper_receipt.py', [receiptPath, '--mode', 'rehash', '--customer-total', '40000', '--worker-share', '36000', '--platform-fee', '4000', '--out', `${OUT}/forged.json`]);
    const f1 = JSON.parse(cli('verify_receipt.py', [`${OUT}/forged.json`, '--tsa-ca', ROOT_PEM, '--json']).stdout);
    const f2 = JSON.parse(cli('verify_receipt.py', [`${OUT}/forged.json`, '--tsa-ca', ROOT_PEM, '--compare', receiptPath, '--json']).stdout);
    check('consistent forgery with every hash recomputed: LOCAL only, not externally verified…', f1.result === 'LOCAL INTEGRITY VERIFIED' && f1.external_timestamp !== 'VERIFIED', f1.result);
    check('…and exposed by comparing with the retained original', f2.result === 'VERIFICATION FAILED');
    const reorig = JSON.parse(cli('verify_receipt.py', [receiptPath, '--tsa-ca', ROOT_PEM, '--json']).stdout); check('the original receipt is untouched and still verifies externally', reorig.result === 'EXTERNALLY TIMESTAMPED AND VERIFIED');
    // browser tamper page, watching every network request
    const tp = await (await ctx({ width: 1280, height: 900 })).newPage(); const reqs = []; tp.on('request', (r) => { if (r.url().includes('/api/v1')) reqs.push(r.method()); });
    await tp.goto(`${WEB}/demo/tamper`); await tp.getByTestId('td-original').waitFor({ timeout: 15000 });
    await tp.getByTestId('preset-hidden').click(); await tp.getByRole('button', { name: /Run verification on the altered copy/ }).click(); await tp.getByTestId('td-outcome').waitFor();
    check('browser tamper demo (hidden deduction) → real verification FAILED with reasons', /Verification FAILED/.test(await tp.getByTestId('td-outcome').innerText()) && (await tp.getByTestId('td-failures').innerText()).length > 20);
    await tp.getByLabel(/C\. Change the amounts and recompute every hash/).check(); await tp.getByTestId('preset-consistent').click(); await tp.getByRole('button', { name: /Run verification on the altered copy/ }).click();
    await tp.getByTestId('td-limits').waitFor(); check('browser consistent-forgery mode: passes LOCAL check, explains why that is insufficient, shows token mismatch', /internally consistent/.test(await tp.getByTestId('td-outcome').innerText()) && /does not contain it/.test(await tp.getByTestId('td-token').innerText()));
    check('tamper page made only read-only (GET) API calls', reqs.length > 0 && reqs.every((m) => m === 'GET'), [...new Set(reqs)].join(','));
    const [, after] = await api('GET', `/bookings/${headline.id}/financial-record`, at);
    check('authoritative ledger and event chain unchanged after all tampering', JSON.stringify(before.ledger_transactions) === JSON.stringify(after.ledger_transactions) && before.events.length === after.events.length && before.events.every((e, i) => e.event_hash === after.events[i].event_hash));

    console.log('\nScenario F — retention: repeat booking, history, disputes (fresh tagged identities; seeded data untouched)');
    const [, skills] = await api('GET', '/skills'); const deskId = skills.find((s) => s.slug === 'desk-assembly').id;
    const wt = await tok(em(`e2e-w-${TAG}`), `E2E Worker ${TAG}`); await api('POST', '/worker-profiles', wt, { display_name: `E2E Worker ${TAG}` });
    await api('POST', '/worker-profiles/me/skills', wt, { skill_id: deskId }); await api('PUT', '/worker-profiles/me/service-settings', wt, { locality: 'Koramangala', latitude: 12.9352, longitude: 77.6245, radius_km: 10, hourly_rate_paise: 25000 });
    const [, s1] = await api('POST', '/worker-profiles/me/availability', wt, { starts_at: iso(30, 4), ends_at: iso(30, 6) });
    const ct = await tok(em(`e2e-c-${TAG}`), `E2E Customer ${TAG}`); const [, b1] = await api('POST', '/bookings', ct, { worker_profile_id: (await api('GET', '/worker-profiles/me', wt))[1].id, slot_id: s1.id, skill_id: deskId, locality: 'HSR Layout', latitude: 12.9116, longitude: 77.6474, address_details: 'Synthetic E2E address' });
    await api('POST', `/bookings/${b1.id}/accept`, wt, { quote_version: 1 }); await api('POST', `/bookings/${b1.id}/start`, wt); await api('POST', `/bookings/${b1.id}/complete`, ct);
    await api('PUT', '/worker-profiles/me/service-settings', wt, { locality: 'Koramangala', latitude: 12.9352, longitude: 77.6245, radius_km: 10, hourly_rate_paise: 30000 });
    const [, s2] = await api('POST', '/worker-profiles/me/availability', wt, { starts_at: iso(32, 4), ends_at: iso(32, 7) });
    const cust = await (await ctx({ width: 390, height: 844 })).newPage(); const work = await (await ctx({ width: 1280, height: 900 })).newPage();
    await signIn(cust, em(`e2e-c-${TAG}`)); await signIn(work, em(`e2e-w-${TAG}`));
    await cust.goto(`${WEB}/bookings`); const done = cust.locator('div.rounded-3xl', { hasText: 'completed' }).first(); await done.getByRole('button', { name: /again/ }).click(); await done.locator('button[aria-pressed]').first().waitFor({ timeout: 15000 });
    const slotTxt = (await done.locator('button[aria-pressed]').allInnerTexts()).join(' ').replace(/\s+/g, ' ');
    check('repeat flow offers the new slot at the CURRENT rate (3 h × ₹300 = ₹900), not the old ₹250/h price', /₹900/.test(slotTxt), slotTxt);
    if ((await done.locator('button[aria-pressed]').count()) > 1) console.log('  [NOTE] the repeat panel also re-offers the slot of the just-completed booking: free-slot queries only treat confirmed/in_progress bookings as occupying a slot, and completion has no time-window check, so a quickly completed FUTURE-dated booking frees its slot again (existing MVP behaviour; see Known limitations).');
    await done.locator('button[aria-pressed]', { hasText: '₹900' }).first().click(); await done.getByRole('button', { name: 'Request repeat booking' }).click(); await done.getByText(/New booking requested/).waitFor({ timeout: 15000 });
    const [, mineC] = await api('GET', '/bookings/mine', ct); const nb = mineC.find((b) => b.repeat_of_booking_id === b1.id);
    check('a new booking + new quote exist, still "requested" (no automatic booking)', nb && nb.id !== b1.id && nb.status === 'requested' && nb.agreement.quote_id !== mineC.find((b) => b.id === b1.id).agreement.quote_id && nb.agreement.quote_version === 1);
    await work.goto(`${WEB}/bookings`); const req = work.locator('div.rounded-3xl', { hasText: `E2E Customer ${TAG}` }).filter({ has: work.getByRole('button', { name: 'Accept booking' }) }).first(); await req.waitFor({ timeout: 15000 });
    check('worker must consent: sees "Accept booking", address still hidden, same amounts', (await req.getByRole('button', { name: 'Accept booking' }).count()) === 1 && /shared after you accept/.test(await req.innerText()) && (await req.getByTestId('amount-customer-total').innerText()) === '₹900');
    await req.getByRole('button', { name: 'Accept booking' }).click();
    let conf = null; for (let i = 0; i < 20; i++) { conf = (await api('GET', `/bookings/${nb.id}`, wt))[1]; if (conf.status === 'confirmed') break; await new Promise((r) => setTimeout(r, 500)); }
    check('worker acceptance recorded for v1; booking confirmed; address now visible', conf.status === 'confirmed' && !!conf.agreement.worker_accepted_at && !!conf.address_details);
    await cust.goto(`${WEB}/bookings`); await cust.getByRole('button', { name: 'Report a problem' }).first().waitFor({ timeout: 15000 });
    const cards = await cust.locator('div.rounded-3xl', { has: cust.getByTestId('quote-version') }).count();
    check('booking history shows both bookings (completed + the repeat) and a dispute action', cards === 2 && (await cust.getByRole('button', { name: 'Report a problem' }).count()) >= 1, `${cards} booking cards`);
    // seeded asha: the same repeat panel renders with real data (not submitted)
    await asha.goto(`${WEB}/bookings`); const ac2 = asha.locator('div.rounded-3xl', { hasText: 'Synthetic demo record' }).filter({ hasText: 'Ravi Kumar' }).filter({ hasText: 'completed' }).first(); await ac2.getByRole('button', { name: /Book Ravi Kumar again/ }).click(); await ac2.locator('button[aria-pressed]').first().waitFor({ timeout: 15000 });
    check('seeded Asha sees Ravi\'s real free slots in the repeat panel (not submitted)', (await ac2.locator('button[aria-pressed]').count()) >= 2);
    // dashboard
    await asha.goto(`${WEB}/dashboard`); await asha.getByTestId('dashboard-activity').waitFor({ timeout: 15000 }); await settle(asha);
    const [, mineA] = await api('GET', '/bookings/mine', at);
    const wantUp = mineA.filter((b) => ['requested', 'confirmed', 'in_progress'].includes(b.status)).length, wantDone = mineA.filter((b) => b.status === 'completed' || (b.status === 'disputed' && b.settlement)).length;
    await asha.waitForFunction(([u, d]) => document.querySelector('[data-testid=dash-upcoming]')?.textContent === String(u) && document.querySelector('[data-testid=dash-completed]')?.textContent === String(d), [wantUp, wantDone], { timeout: 15000 }).catch(() => {});
    check('dashboard counts equal the API (upcoming/active, completed)', num(await asha.getByTestId('dash-upcoming').innerText()) === wantUp && num(await asha.getByTestId('dash-completed').innerText()) === wantDone, `${wantUp} active, ${wantDone} completed`);
    // worker: nearby jobs + real apply, on a fresh job posted by the fresh customer
    const [, jb] = await api('POST', '/jobs', ct, { skill_id: deskId, title: `E2E sample job ${TAG}`, description: 'Synthetic job posted by the demo E2E for the apply test.', locality: 'HSR Layout', latitude: 12.9116, longitude: 77.6474, address_details: 'Synthetic E2E address', starts_at: iso(33, 4), duration_minutes: 120, budget_paise: 80000 });
    await work.goto(`${WEB}/find-work`); const jc = work.locator('div.rounded-3xl', { hasText: `E2E sample job ${TAG}` }); await jc.waitFor({ timeout: 15000 });
    check('signed-in worker sees nearby jobs with distance and an Apply action', /km from your service centre/.test(await jc.innerText()) && (await jc.getByRole('button', { name: 'Apply' }).count()) === 1);
    await jc.getByRole('button', { name: 'Apply' }).click(); await jc.getByText(/Applied/).first().waitFor({ timeout: 15000 });
    const [, apps] = await api('GET', `/jobs/${jb.id}/applications`, ct); check('Apply used the real API (application persisted)', apps.length === 1);

    console.log('\nScenario G — business model');
    const pr = await (await ctx({ width: 1280, height: 900 })).newPage(); await pr.goto(`${WEB}/pricing`); await pr.getByTestId('policy-ref').waitFor({ timeout: 15000 });
    const [, fp] = await api('GET', '/fee-policy'); const ap = fp.active_policy;
    check('pricing page shows the ACTIVE policy record from the backend', (await pr.getByTestId('policy-ref').innerText()).includes(`${ap.policy_id} · version ${ap.version}`) && (await pr.getByTestId('policy-label').innerText()) === ap.label);
    const ptxt = await pr.locator('main').innerText(); check('example policy labelled "not final pricing"; subscription "Planned"; no Subscribe/Pay button', /Illustrative example policy/.test(ptxt) && /Planned, not currently available/.test(ptxt) && (await pr.getByRole('button', { name: /subscribe|pay now/i }).count()) === 0);
    const vik = await (await ctx({ width: 1280, height: 900 })).newPage(); await signIn(vik, em('vikram')); await vik.goto(`${WEB}/organizations`);
    const org = vik.locator('div.p-4', { hasText: 'BrightDesk Co-working (Demo)' }).first(); await org.waitFor({ timeout: 15000 }); await org.getByRole('button', { name: /Booking and spending records/ }).click(); await vik.getByTestId('org-metrics').waitFor({ timeout: 15000 });
    const vt = await tok(em('vikram'), 'Vikram'); const [, orgs] = await api('GET', '/organizations/mine', vt); const bd = orgs.find((o) => o.name.startsWith('BrightDesk')); const [, sum] = await api('GET', `/organizations/${bd.id}/financial-summary`, vt);
    const metrics = (await vik.getByTestId('org-metrics').innerText()).replace(/\s+/g, ' ');
    const inr = (p) => '₹' + (p / 100).toLocaleString('en-IN');
    check('business dashboard shows the recorded org figures from the API (jobs, bookings, completed, agreed spend incl. the org-borne fee, platform charges)', metrics.includes(`Jobs posted ${sum.jobs_posted}`) && metrics.includes(`Bookings created ${sum.bookings_created}`) && metrics.includes(`Completed ${sum.completed_bookings}`) && metrics.includes(inr(sum.agreed_spend_completed_paise)) && metrics.includes(inr(sum.platform_fees_completed_paise)), metrics);
    check('subscription tools are labelled planned on the business dashboard', /planned, not currently available/i.test(await vik.getByTestId('org-subscription-note').innerText()));
    const [sOut] = await api('GET', `/organizations/${bd.id}/financial-summary`, at); check('a non-member (Asha) is denied that organization\'s records', sOut === 404);
    const [sEco] = await api('GET', '/economics/summary', at); check('platform totals are staff-only (customer gets 403)', sEco === 403);
    await pr.goto(`${WEB}/economics`); const eco = await pr.locator('main').innerText(); check('economics separates recorded figures from assumptions; calculator marked hypothetical', /Scenario calculator \(assumptions, not data\)/.test(eco) && /Every input below is a hypothetical/.test(eco) && /Not a real plan|not a real plan/i.test(eco));

    console.log('\nDemo guide and personas');
    const dg = await (await ctx({ width: 1280, height: 900 })).newPage(); await dg.goto(`${WEB}/`); await dg.getByRole('button', { name: /Demo guide/ }).click();
    check('guide lists the recommended flow and 10 personas; states anchoring honestly', (await dg.getByTestId('demo-guide').locator('ol li').count()) === 8 && /checkpoints verified from DigiCert/.test(await dg.getByTestId('guide-anchoring').innerText()));
    await dg.getByRole('button', { name: 'Asha Menon' }).click(); await dg.waitForURL(/\/login\?as=/); check('persona link opens the real login with the email prefilled and the passcode EMPTY', (await dg.getByLabel('Email').inputValue()) === em('asha') && (await dg.getByLabel('Password', { exact: true }).inputValue()) === '');
    check('the passcode never appears in any page the guide renders', !(await dg.content()).includes(PASS));

    console.log('\nMobile (390px)');
    for (const [name, route] of [['home', '/'], ['hire', '/hire'], ['find-work', '/find-work'], ['pricing', '/pricing'], ['demo hub', '/demo'], ['tamper demo', '/demo/tamper'], ['demo explorer', '/demo/transparency/headline-percentage']]) {
      await mob.goto(WEB + route); await mob.waitForTimeout(1800); const o = await overflow(mob); check(`${name}: no horizontal overflow at 390px`, o <= 1, `overflow ${o}px`);
    }
    await mob.goto(`${WEB}/demo/transparency/headline-percentage`); await mob.getByTestId('transaction-transparency').waitFor(); await mob.getByRole('tab', { name: 'Ledger' }).click(); await mob.screenshot({ path: `${OUT}/ledger-mobile.png`, fullPage: true });
    await mob.goto(`${WEB}/hire`); await mob.waitForTimeout(2500); await mob.screenshot({ path: `${OUT}/hire-mobile.png`, fullPage: true });
  } catch (e) { check('unexpected error', false, String(e).slice(0, 500)); }
  finally { await browser.close(); }
  console.log(`\n${res.filter(Boolean).length}/${res.length} browser demo checks passed. Artifacts: ${OUT}`); process.exit(res.every(Boolean) ? 0 : 1);
})();
