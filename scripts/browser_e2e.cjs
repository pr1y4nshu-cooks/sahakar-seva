// Browser E2E through the real React UI (http://localhost:5173) -> FastAPI -> PostgreSQL/PostGIS.
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> DEV_AUTH_PASSCODE=... node scripts/browser_e2e.cjs
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const WEB = process.env.WEB || 'http://localhost:5173';
const PASS = process.env.DEV_AUTH_PASSCODE;
const TAG = Math.random().toString(36).slice(2, 8);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const results = [];
const check = (name, ok, detail = '') => { results.push(ok); console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`); };

function localInput(daysAhead, hour) {
  const d = new Date(); d.setDate(d.getDate() + daysAhead); d.setHours(hour, 0, 0, 0);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:00`;
}

async function signIn(page, who) {
  await page.goto(`${WEB}/login`);
  await page.getByLabel('Email').fill(`${who}-${TAG}@demo.sahakar.test`);
  await page.getByLabel('Password', { exact: true }).fill(PASS);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('**/dashboard', { timeout: 15000 });
}

(async () => {
  if (!PASS) { console.error('Set DEV_AUTH_PASSCODE'); process.exit(2); }
  // CHROME_ARGS lets you pin localhost to IPv4 when another dev server owns [::1]:5173.
  const args = process.env.CHROME_ARGS ? [process.env.CHROME_ARGS] : [];
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args });
  const workerCtx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const customerCtx = await browser.newContext({ viewport: { width: 390, height: 844 } }); // mobile viewport
  const w = await workerCtx.newPage();
  const c = await customerCtx.newPage();
  const workerName = `Browser Worker ${TAG}`;
  try {
    console.log(`Run tag ${TAG}\nWorker onboarding (desktop)`);
    await signIn(w, 'bw');
    check('worker signs in (local demo identity) and reaches dashboard', true);
    await w.goto(`${WEB}/earn`);
    await w.getByLabel(/Display Name/).fill(workerName);
    await w.getByRole('button', { name: 'Create Worker Profile' }).click();
    await w.getByRole('button', { name: '+ Desk Assembly' }).click();
    await w.getByRole('button', { name: '✓ Desk Assembly' }).waitFor({ timeout: 10000 });
    check('declares Desk Assembly skill', true);
    await w.locator('#svc-loc').selectOption({ label: 'Koramangala, Bengaluru' });
    await w.locator('#svc-radius').selectOption('5');
    await w.locator('#svc-rate').fill('350');
    await w.getByRole('button', { name: 'Save service area' }).click();
    await w.getByText('Service area saved.').waitFor({ timeout: 10000 });
    check('saves 5 km service area at ₹350/h', true);
    await w.locator('#slot-start').fill(localInput(2, 10));
    await w.getByRole('button', { name: 'Add slot' }).click();
    await w.getByText('Free').first().waitFor({ timeout: 10000 });
    check('adds an availability slot', true);
    await w.reload();
    await w.getByRole('button', { name: '✓ Desk Assembly' }).waitFor({ timeout: 10000 });
    const persisted = (await w.locator('#svc-rate').inputValue()) === '350' && (await w.getByText('Free').count()) >= 1;
    check('skills, service area and slot persist after page refresh', persisted);
    await w.screenshot({ path: '/tmp/sahakar-earn.png', fullPage: true });

    console.log('Customer direct hire (mobile viewport)');
    await signIn(c, 'bc');
    await c.goto(`${WEB}/hire`);
    await c.locator('#h-cat').selectOption({ label: 'Furniture Assembly' });
    await c.locator('#h-loc').selectOption({ label: 'HSR Layout, Bengaluru' });
    await c.getByRole('button', { name: /Search workers/ }).click();
    const card = c.locator('div.rounded-3xl', { hasText: workerName });
    await card.waitFor({ timeout: 15000 });
    const cardText = await card.innerText();
    check('search returns the worker from real DB records', cardText.includes('HSR') === false && cardText.includes('Koramangala'), cardText.match(/[\d.]+ km away/)?.[0] ?? '');
    check('card shows honest verification label and self-declared skills',
      cardText.includes('Not verified') && cardText.includes('Self-declared skills') && !/\bVerified Workers\b/.test(cardText));
    await card.locator('button[aria-pressed]').first().click();
    await card.getByLabel(/Exact address/).fill('Flat 7C, Browser Test Residency, 14th Main');
    await card.getByRole('button', { name: 'Request booking' }).click();
    await card.getByText('Booking requested').waitFor({ timeout: 10000 });
    check('customer requests the booking', true);
    await c.screenshot({ path: '/tmp/sahakar-hire-mobile.png', fullPage: true });

    console.log('Worker accepts');
    await w.goto(`${WEB}/bookings`);
    const wb = w.locator('div.rounded-3xl', { hasText: 'You are working' }).first();
    await wb.waitFor({ timeout: 10000 });
    check('worker sees request without the exact address', (await wb.innerText()).includes('shared after you accept'));
    await wb.getByRole('button', { name: 'Accept booking' }).click();
    await wb.getByText('confirmed').waitFor({ timeout: 10000 });
    await w.reload();
    const after = await w.locator('div.rounded-3xl', { hasText: 'You are working' }).first().innerText();
    check('booking is confirmed and persists after refresh, address now visible', after.includes('confirmed') && after.includes('Flat 7C'));

    console.log('Completion and simulated settlement');
    await w.getByRole('button', { name: 'Start work' }).click();
    await w.getByText('in progress').first().waitFor({ timeout: 10000 });
    await c.goto(`${WEB}/bookings`);
    await c.getByRole('button', { name: 'Confirm work completed' }).click();
    await c.getByText('SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED').waitFor({ timeout: 10000 });
    const cb = await c.locator('div.rounded-3xl', { hasText: 'You are hiring' }).first().innerText();
    check('customer completes; UI shows ₹700 = ₹70 fee + ₹630 payout, labelled simulated', cb.includes('₹700') && cb.includes('₹70') && cb.includes('₹630'));
    await w.goto(`${WEB}/earn`);
    await w.getByText('Earnings (simulated)').waitFor({ timeout: 10000 });
    check('worker earnings show ₹630 payout', (await w.locator('div.rounded-3xl', { hasText: 'Earnings (simulated)' }).innerText()).includes('₹630'));

    console.log('Unauthorised state');
    const anon = await browser.newPage();
    await anon.goto(`${WEB}/bookings`);
    await anon.waitForURL('**/login', { timeout: 10000 });
    check('signed-out visitor is redirected from /bookings to /login', true);
  } catch (err) {
    check('browser flow', false, String(err).split('\n')[0]);
    await w.screenshot({ path: '/tmp/sahakar-fail-worker.png', fullPage: true }).catch(() => {});
    await c.screenshot({ path: '/tmp/sahakar-fail-customer.png', fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
  const ok = results.every(Boolean);
  console.log(`\n${results.filter(Boolean).length}/${results.length} browser checks passed.`);
  process.exit(ok ? 0 : 1);
})();
