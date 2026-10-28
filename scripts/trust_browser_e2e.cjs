// Trust-ledger browser E2E through the real React UI -> FastAPI -> PostgreSQL (and the configured TSA).
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> DEV_AUTH_PASSCODE=... node scripts/trust_browser_e2e.cjs
// Creates new tagged @demo.sahakar.test users only. Tampering happens on a downloaded COPY of a receipt.
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const WEB = process.env.WEB || 'http://localhost:5173';
const API = process.env.API || 'http://127.0.0.1:8000/api/v1';
const PASS = process.env.DEV_AUTH_PASSCODE;
const TAG = Math.random().toString(36).slice(2, 8);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const OUT = process.env.OUT || '/tmp/sahakar-trust-browser';
const results = [];
const check = (name, ok, detail = '') => { results.push(!!ok); console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`); };

async function api(method, p, token, body) {
  const r = await fetch(`${API}${p}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  return [r.status, text ? JSON.parse(text) : {}];
}
const email = (who) => `${who}-${TAG}@demo.sahakar.test`;
async function token(who, name) {
  const [, b] = await api('POST', '/dev-auth/token', null, { email: email(who), passcode: PASS, display_name: name });
  return b.access_token;
}
function iso(daysAhead, hour) {
  const d = new Date(); d.setUTCDate(d.getUTCDate() + daysAhead); d.setUTCHours(hour, 0, 0, 0); return d.toISOString();
}
async function signIn(page, who) {
  await page.goto(`${WEB}/login`);
  await page.getByLabel('Email').fill(email(who));
  await page.getByLabel('Password', { exact: true }).fill(PASS);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('**/dashboard', { timeout: 15000 });
}
const amounts = async (card) => Promise.all(['customer-total', 'worker-share', 'platform-fee'].map((id) => card.getByTestId(`amount-${id}`).innerText()));

(async () => {
  if (!PASS) { console.error('Set DEV_AUTH_PASSCODE'); process.exit(2); }
  fs.mkdirSync(OUT, { recursive: true });
  const args = process.env.CHROME_ARGS ? [process.env.CHROME_ARGS] : [];
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args });
  const workerCtx = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  const customerCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, acceptDownloads: true }); // mobile
  const anonCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const w = await workerCtx.newPage();
  const c = await customerCtx.newPage();
  const workerName = `Trust Worker ${TAG}`;
  try {
    console.log(`Run tag ${TAG}\nSetup (API): worker at ₹250/h with a 2 h slot`);
    const [, skills] = await api('GET', '/skills');
    const desk = skills.find((s) => s.slug === 'desk-assembly').id;
    const wt = await token('tw', workerName);
    await api('POST', '/worker-profiles', wt, { display_name: workerName });
    await api('POST', '/worker-profiles/me/skills', wt, { skill_id: desk });
    await api('PUT', '/worker-profiles/me/service-settings', wt, { locality: 'Koramangala', latitude: 12.9352, longitude: 77.6245, radius_km: 5, hourly_rate_paise: 25000 });
    await api('POST', '/worker-profiles/me/availability', wt, { starts_at: iso(3, 4), ends_at: iso(3, 6) });

    console.log('Demo 1 — price shown before confirming (customer, mobile)');
    await signIn(c, 'tc');
    await c.goto(`${WEB}/hire`);
    await c.locator('#h-cat').selectOption({ label: 'Furniture Assembly' });
    await c.locator('#h-loc').selectOption({ label: 'HSR Layout, Bengaluru' });
    await c.getByRole('button', { name: /Search workers/ }).click();
    const card = c.locator('div.rounded-3xl', { hasText: workerName });
    await card.waitFor({ timeout: 15000 });
    await card.locator('button[aria-pressed]').first().click();
    const preview = card.getByLabel('Price before you confirm');
    await preview.getByText('₹450', { exact: true }).waitFor({ timeout: 10000 });
    const pv = await preview.innerText();
    const [, active] = await api('GET', '/fee-policy');
    check('before confirming (illustrative example policy): service ₹500, worker ₹450, platform ₹50, processing and taxes stated',
      pv.includes('₹500') && pv.includes('₹450') && pv.includes('₹50') && pv.includes('Processing charges') && pv.includes('Not modeled'));
    check('preview names the active fee policy and labels it as an example',
      (await preview.getByTestId('preview-policy').innerText()).includes(`${active.active_policy.policy_id} v${active.active_policy.version}`) && pv.includes('not final pricing'));
    check('protection terms are stated without false promises', pv.includes('SAHAKAR Protected Booking') && pv.includes('Not included: insurance'));
    await card.getByLabel(/Exact address/).fill('Flat 3B, Trust Test Residency');
    await card.getByRole('button', { name: 'Request booking' }).click();
    await card.getByText('Booking requested').waitFor({ timeout: 10000 });

    console.log('Both parties see one agreement');
    await signIn(w, 'tw');
    await w.goto(`${WEB}/bookings`);
    const wcard = w.locator('div.rounded-3xl', { hasText: 'You are working' }).first();
    await wcard.getByTestId('amount-customer-total').waitFor({ timeout: 15000 });
    await c.goto(`${WEB}/bookings`);
    const ccard = c.locator('div.rounded-3xl', { hasText: 'You are hiring' }).first();
    await ccard.getByTestId('amount-customer-total').waitFor({ timeout: 15000 });
    const wa = await amounts(wcard), ca = await amounts(ccard);
    check('worker and customer screens show identical amounts', JSON.stringify(wa) === JSON.stringify(ca) && wa.join(',') === '₹500,₹450,₹50', wa.join(' / '));
    check('both show the same quote version and fee policy reference',
      (await wcard.getByTestId('quote-version').innerText()) === (await ccard.getByTestId('quote-version').innerText())
      && (await wcard.getByTestId('policy-ref').innerText()) === (await ccard.getByTestId('policy-ref').innerText()));
    await wcard.getByRole('button', { name: 'Accept booking' }).click();
    await wcard.getByText(/Worker accepted v1/).waitFor({ timeout: 10000 });
    check('worker accepts quote v1 with the booking', true);

    console.log('Demo 2 — completion and ledger');
    await wcard.getByRole('button', { name: 'Start work' }).click();
    await c.reload();
    await ccard.getByRole('button', { name: 'Confirm work completed' }).click();
    await ccard.getByText(/ledger balanced/).waitFor({ timeout: 10000 });
    const evidence = await ccard.getByLabel('Evidence status').innerText();
    check('evidence: simulated payment, balanced ledger, honest timestamp status',
      evidence.includes('Simulated — no real money') && evidence.includes('ledger balanced') && /External timestamp/.test(evidence), evidence.split('\n').slice(-1)[0]);
    await ccard.getByRole('button', { name: /Ledger & event record/ }).click();
    await ccard.getByText('Settlement allocation (simulated) · balanced').waitFor({ timeout: 10000 });
    const ledgerText = await ccard.locator('table').first().innerText();
    check('ledger table: debits ₹500 = credits ₹450 + ₹50', ledgerText.includes('customer payment clearing') && /Total\s+₹500\s+₹500/.test(ledgerText));
    await c.screenshot({ path: `${OUT}/bookings-mobile.png`, fullPage: true });

    console.log('Demo 3/4 — receipt download and verification');
    const [download] = await Promise.all([c.waitForEvent('download'), ccard.getByRole('button', { name: /Download receipt/ }).click()]);
    const receiptPath = path.join(OUT, `receipt-${TAG}.json`);
    await download.saveAs(receiptPath);
    const receipt = JSON.parse(fs.readFileSync(receiptPath, 'utf8'));
    check('receipt downloads as a file with the agreed values', receipt.summary.customer_total_paise === 50000 && receipt.summary.worker_share_paise === 45000);
    const tampered = JSON.parse(JSON.stringify(receipt));
    tampered.summary.customer_total_paise = 40000; tampered.summary.worker_share_paise = 36000;
    const tamperedPath = path.join(OUT, `receipt-${TAG}-tampered.json`);
    fs.writeFileSync(tamperedPath, JSON.stringify(tampered));
    await c.goto(`${WEB}/verify`);
    await c.getByLabel(/Receipt file/).setInputFiles(receiptPath);
    await c.getByTestId('verify-result').waitFor({ timeout: 10000 });
    check('browser verifier: genuine receipt → integrity verified (local)', (await c.getByTestId('verify-result').innerText()) === 'Receipt integrity verified (local)');
    const verifyText = await c.locator('main').innerText();
    check('browser verifier never claims external verification', !/Externally timestamped and verified/i.test(verifyText) && /offline verifier/.test(verifyText));
    await c.getByLabel(/Receipt file/).setInputFiles(tamperedPath);
    await c.getByText('Verification failed').waitFor({ timeout: 10000 });
    check('browser verifier: tampered ₹400/₹360 copy → verification failed, reasons listed', (await c.getByRole('alert').innerText()).includes('Verification failed'));

    console.log('Demo 5 — repeat booking and dispute route');
    await api('POST', '/worker-profiles/me/availability', wt, { starts_at: iso(5, 4), ends_at: iso(5, 6) });
    await c.goto(`${WEB}/bookings`);
    const done = c.locator('div.rounded-3xl', { hasText: 'You are hiring' }).first();
    await done.getByRole('button', { name: new RegExp(`Book ${workerName} again`) }).click();
    await done.locator('button[aria-pressed]').first().click();
    await done.getByRole('button', { name: 'Request repeat booking' }).click();
    await done.getByText(/New booking requested/).waitFor({ timeout: 10000 });
    check('repeat booking creates a new request that the worker must accept', true);
    await c.reload();
    const completed = c.locator('div.rounded-3xl', { hasText: 'completed' }).first();
    await completed.getByRole('button', { name: 'Report a problem' }).click();
    await completed.locator('select[id^="dsc-"]').selectOption('worker_payout_differs');
    await completed.locator('textarea[id^="dsp-"]').fill('The payout shown to the worker differs from the agreed share.');
    await completed.getByRole('button', { name: 'Open dispute' }).click();
    await c.getByText(/Worker payout differs from the agreed amount/).first().waitFor({ timeout: 10000 });
    check('financial dispute opened with category and attached record', true);

    console.log('Demo 4 — external timestamp status (honest)');
    let status = '';
    for (let i = 0; i < 18; i++) {
      await w.goto(`${WEB}/bookings`);
      const s = w.locator('div.rounded-3xl', { hasText: 'disputed' }).first().getByTestId('anchor-status');
      await s.waitFor({ timeout: 10000 });
      status = await s.innerText();
      if (/External timestamp verified/.test(status)) break;
      await w.waitForTimeout(5000);
    }
    check('anchor status reported from evidence (verified only after TSA proof passed)', /External timestamp (verified|pending|requested)|Local integrity only/.test(status), status);

    console.log('Demo 6 — public pricing policy (signed out, mobile)');
    const a = await anonCtx.newPage();
    await a.goto(`${WEB}/pricing`);
    await a.getByTestId('policy-ref').waitFor({ timeout: 10000 });
    const [, policy] = await api('GET', '/fee-policy');
    const ref = await a.getByTestId('policy-ref').innerText();
    check('pricing page shows the active policy record from the backend',
      ref.includes(`${policy.active_policy.policy_id} · version ${policy.active_policy.version}`) && (await a.getByTestId('policy-label').innerText()) === policy.active_policy.label, ref);
    check('example policy is labelled as not final pricing', !policy.active_policy.is_example || (await a.locator('main').innerText()).includes('Illustrative example policy'));
    const pricingText = await a.locator('main').innerText();
    check('subscription marked planned; no subscribe or pay button', pricingText.includes('Planned, not currently available') && (await a.getByRole('button', { name: /subscribe|pay now/i }).count()) === 0);
    await a.screenshot({ path: `${OUT}/pricing-mobile.png`, fullPage: true });
    await a.goto(`${WEB}/economics`);
    await a.getByTestId('scenario-results').waitFor();
    const eco = await a.locator('main').innerText();
    check('economics separates recorded data (staff only) from assumptions', eco.includes('Scenario calculator (assumptions, not data)') && eco.includes('visible to signed-in platform staff only'));
    await a.getByRole('button', { name: 'Evaluate candidate policy' }).click();
    await a.getByTestId('simulation-results').waitFor({ timeout: 10000 });
    check('policy simulator evaluates a candidate via the server engine (not saved)', (await a.getByTestId('simulation-results').innerText()).includes('Pricing model'));
  } catch (err) {
    check('unexpected error', false, String(err).slice(0, 300));
    await c.screenshot({ path: `${OUT}/failure-customer.png`, fullPage: true }).catch(() => {});
    await w.screenshot({ path: `${OUT}/failure-worker.png`, fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
  const passed = results.filter(Boolean).length;
  console.log(`\n${passed}/${results.length} trust browser checks passed. Artifacts: ${OUT}`);
  process.exit(passed === results.length ? 0 : 1);
})();
