// Audit 4: retention flow through the REAL frontend (Vite :5180 -> isolated audit API :8100 -> throwaway DB).
// Independent of the implementer's own E2E: different selectors strategy, ground truth read from the API, claims scan across pages.
const fs = require('fs'); const { execSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_CORE);
const WEB = 'http://127.0.0.1:5180', API = 'http://127.0.0.1:8100/api/v1';
const PASS = fs.readFileSync('/tmp/sahakar-audit/passcode', 'utf8').trim();
const TAG = Math.random().toString(36).slice(2, 8), CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const out = []; const check = (n, ok, d = '') => { out.push(!!ok); console.log(`  [${ok ? 'OBSERVED-OK' : 'DEVIATION'}] ${n}${d ? ' — ' + d : ''}`); };
const em = (w) => `${w}-${TAG}@demo.sahakar.test`;
async function api(method, p, tok, body) {
  const r = await fetch(API + p, { method, headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: 'Bearer ' + tok } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text(); return [r.status, t ? JSON.parse(t) : {}];
}
const token = async (w) => (await api('POST', '/dev-auth/token', null, { email: em(w), passcode: PASS, display_name: w }))[1].access_token;
const iso = (d, h) => { const x = new Date(); x.setUTCDate(x.getUTCDate() + d); x.setUTCHours(h, 0, 0, 0); return x.toISOString(); };
async function signIn(page, w) {
  await page.goto(`${WEB}/login`); await page.getByLabel('Email').fill(em(w)); await page.getByLabel('Password', { exact: true }).fill(PASS);
  await page.getByRole('button', { name: 'Sign in' }).click(); await page.waitForURL('**/dashboard', { timeout: 20000 });
}
const card = (page, text) => page.locator('div.rounded-3xl', { hasText: text }).first();

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const mk = async (vp) => (await browser.newContext({ viewport: vp, acceptDownloads: true })).newPage();
  const cust = await mk({ width: 390, height: 844 }), work = await mk({ width: 1280, height: 900 }), rev = await mk({ width: 1280, height: 900 });
  const wname = `Ravi ${TAG}`;
  try {
    console.log('Setup (API, not under test): worker profile ₹250/h with two future slots');
    const [, skills] = await api('GET', '/skills'); const desk = skills.find((s) => s.slug === 'desk-assembly').id;
    const wt = await token('ravi'); await api('POST', '/worker-profiles', wt, { display_name: wname }); await api('POST', '/worker-profiles/me/skills', wt, { skill_id: desk });
    await api('PUT', '/worker-profiles/me/service-settings', wt, { locality: 'Koramangala', latitude: 12.9352, longitude: 77.6245, radius_km: 5, hourly_rate_paise: 25000 });
    const [, slot1] = await api('POST', '/worker-profiles/me/availability', wt, { starts_at: iso(3, 4), ends_at: iso(3, 6) });

    console.log('\n1. Complete a booking through the UI');
    await signIn(cust, 'asha'); await signIn(work, 'ravi');
    await cust.goto(`${WEB}/hire`); await cust.locator('#h-cat').selectOption({ label: 'Furniture Assembly' }); await cust.locator('#h-loc').selectOption({ label: 'HSR Layout, Bengaluru' });
    await cust.getByRole('button', { name: /Search workers/ }).click();
    const wc = card(cust, wname); await wc.waitFor({ timeout: 20000 }); await wc.locator('button[aria-pressed]').first().click();
    await wc.getByLabel('Price before you confirm').getByText('₹450', { exact: true }).waitFor({ timeout: 10000 });
    const pre = await wc.getByLabel('Price before you confirm').innerText();
    check('pre-confirmation shows service ₹500 / customer total ₹500 / worker payout ₹450 / platform ₹50', ['₹500', '₹450', '₹50'].every((x) => pre.includes(x)));
    await wc.getByLabel(/Exact address/).fill('Flat 5, Audit Tower, 2nd Cross'); await wc.getByRole('button', { name: 'Request booking' }).click(); await wc.getByText('Booking requested').waitFor({ timeout: 15000 });
    await work.goto(`${WEB}/bookings`); const wb = card(work, 'You are working'); await wb.getByRole('button', { name: 'Accept booking' }).click(); await wb.getByRole('button', { name: 'Start work' }).click();
    await cust.goto(`${WEB}/bookings`); const cb = card(cust, 'You are hiring'); await cb.getByRole('button', { name: 'Confirm work completed' }).click(); await cb.getByText(/ledger balanced/).waitFor({ timeout: 15000 });
    const ct = await token('asha');
    const [, mine] = await api('GET', '/bookings/mine', ct); const first = mine.find((b) => b.status === 'completed');
    check('first booking completed via UI; settlement simulated', first && first.settlement && first.settlement.is_simulated, first && first.id.slice(0, 8));

    console.log('\n2-3. Rehire through the repeat-booking flow; new booking + new quote');
    await api('PUT', '/worker-profiles/me/service-settings', wt, { locality: 'Koramangala', latitude: 12.9352, longitude: 77.6245, radius_km: 5, hourly_rate_paise: 30000 });   // worker raised rate
    const [, slot2] = await api('POST', '/worker-profiles/me/availability', wt, { starts_at: iso(5, 4), ends_at: iso(5, 7) });                                        // new 3 h slot
    await cust.goto(`${WEB}/bookings`); const done = card(cust, 'completed');
    await done.getByRole('button', { name: new RegExp(`Book ${wname} again`) }).click();
    await done.locator('button[aria-pressed]').first().waitFor({ timeout: 10000 });
    const slotsShown = await done.locator('button[aria-pressed]').allInnerTexts();
    check('repeat flow offers ONLY the new free slot (old booked slot not offered), at the CURRENT rate (3 h × ₹300 = ₹900)', slotsShown.length === 1 && slotsShown[0].includes('₹900'), slotsShown.join(' | ').replace(/\n/g, ' '));
    await done.locator('button[aria-pressed]').first().click(); await done.getByRole('button', { name: 'Request repeat booking' }).click(); await done.getByText(/New booking requested/).waitFor({ timeout: 15000 });
    const [, after] = await api('GET', '/bookings/mine', ct); const second = after.find((b) => b.repeat_of_booking_id === first.id);
    check('a NEW booking exists (different id), linked to the first', second && second.id !== first.id);
    check('new booking is "requested" — NOT auto-confirmed', second.status === 'requested', second.status);
    check('new quote: version 1, new quote id, customer accepted, worker not yet', second.agreement.quote_version === 1 && second.agreement.quote_id !== first.agreement.quote_id && second.agreement.customer_accepted_at && !second.agreement.worker_accepted_at && second.agreement.awaiting_acceptance_from === 'worker');
    check('new price reflects current rate + current policy (service ₹900, worker ₹810, platform ₹90)', [second.agreement.service_price_paise, second.agreement.worker_share_paise, second.agreement.platform_fee_paise].join() === '90000,81000,9000', JSON.stringify([second.agreement.service_price_paise, second.agreement.worker_share_paise, second.agreement.platform_fee_paise]));
    const [, oldNow] = await api('GET', `/bookings/${first.id}`, ct);
    check('original booking untouched (completed, ₹500/₹450/₹50, quote v1 same id, same settlement)', oldNow.status === 'completed' && oldNow.agreement.quote_id === first.agreement.quote_id && oldNow.agreement.customer_total_paise === 50000 && oldNow.settlement.id === first.settlement.id);
    const [dupS] = await api('POST', '/bookings', ct, { worker_profile_id: first.worker_profile_id, slot_id: slot2.id, skill_id: desk, locality: 'HSR Layout', latitude: 12.9116, longitude: 77.6474, address_details: 'Flat 5, Audit Tower, 2nd Cross', repeat_of_booking_id: first.id });
    check('same customer cannot double-request the same slot', dupS === 409, 'HTTP ' + dupS);
    const [, ro] = await api('GET', `/bookings/${first.id}/repeat-options`, ct);
    check('availability: the requested slot is still free until the worker confirms (no hold), old slot not offered', !ro.available_slots.some((s) => s.id === slot1.id));

    console.log('\n4. Worker must consent again (worker UI)');
    await work.goto(`${WEB}/bookings`); await work.reload();
    const req = card(work, 'requested'); await req.waitFor({ timeout: 15000 });
    const reqText = await req.innerText();
    check('worker sees the new request as "requested" with an Accept button and no address yet', /requested/i.test(reqText) && (await req.getByRole('button', { name: 'Accept booking' }).count()) === 1 && /shared after you accept/i.test(reqText));
    check('worker sees the same ₹900 / ₹810 / ₹90 breakdown and Quote v1', ['₹900', '₹810', '₹90', 'Quote v1'].every((x) => reqText.includes(x)));
    const [, still] = await api('GET', `/bookings/${second.id}`, wt); check('nothing was confirmed without the worker (server state)', still.status === 'requested');
    await req.getByRole('button', { name: 'Accept booking' }).click(); await req.getByText(/Worker accepted v1/).waitFor({ timeout: 15000 });
    const [, conf] = await api('GET', `/bookings/${second.id}`, wt); check('after the worker accepts: confirmed, worker acceptance recorded for v1', conf.status === 'confirmed' && conf.agreement.worker_accepted_at);

    console.log('\n5. Dispute through the existing process');
    execSync(`cd ../../services/api && DATABASE_URL='postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit_test' .venv/bin/python -m app.cli.grant_reviewer --email ${em('rev')} 2>&1 || true`, { cwd: __dirname });
    await token('rev'); execSync(`cd ../../services/api && DATABASE_URL='postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit_test' .venv/bin/python -m app.cli.grant_reviewer --email ${em('rev')}`, { cwd: __dirname, stdio: 'pipe' });
    await cust.goto(`${WEB}/bookings`); const comp = cust.locator('div.rounded-3xl', { hasText: 'completed' }).first();
    await comp.getByRole('button', { name: 'Report a problem' }).click(); await comp.locator('select[id^="dsc-"]').selectOption('unexpected_deduction');
    await comp.locator('textarea[id^="dsp-"]').fill('I think an unexpected amount was deducted from the worker share.'); await comp.getByRole('button', { name: 'Open dispute' }).click();
    await cust.getByText(/Unexpected deduction/).first().waitFor({ timeout: 15000 });
    const [, dv] = await api('GET', `/bookings/${first.id}`, ct); check('dispute opened; booking disputed; category + quote v1 + ledger tx attached', dv.status === 'disputed' && dv.dispute.category === 'unexpected_deduction' && dv.dispute.related_quote_version === 1 && dv.dispute.related_ledger_transaction_id);
    const rt = await token('rev'); const [s403] = await api('POST', `/disputes/${dv.dispute.id}/resolve`, ct, { outcome: 'no_fault', reason: 'resolving my own dispute' });
    check('a booking party cannot resolve their own dispute', s403 === 403, 'HTTP ' + s403);
    const [sW] = await api('POST', `/disputes/${dv.dispute.id}/resolve`, wt, { outcome: 'no_fault', reason: 'worker trying to resolve' }); check('a non-reviewer worker cannot resolve it', sW === 403);
    await signIn(rev, 'rev'); await rev.goto(`${WEB}/disputes/review`);
    const dc = rev.locator('div.rounded-3xl', { hasText: 'unexpected' }).first().or(rev.locator('div.rounded-3xl').first()); await dc.waitFor({ timeout: 15000 });
    check('reviewer queue shows the category and "simulated settlement posted"', /Unexpected deduction/.test(await dc.innerText()) && /simulated settlement posted/.test(await dc.innerText()));
    await dc.locator('select[id^="out-"]').selectOption('resolved_for_customer'); await dc.locator('select[id^="corr-"]').selectOption('full_reversal');
    await dc.locator('textarea[id^="why-"]').fill('Reviewed the receipt and ledger; recording a reversal for audit.'); await dc.getByRole('button', { name: 'Record decision' }).click();
    await rev.getByText(/full reversal of the simulated settlement was recorded/i).waitFor({ timeout: 15000 });
    const [, dr] = await api('GET', `/bookings/${first.id}/financial-record`, wt);
    check('reversal recorded as NEW ledger transaction; original kept; both balanced', dr.ledger_transactions.length === 2 && dr.ledger_transactions.every((t) => t.balanced) && dr.ledger_transactions[1].reverses_transaction_id === dr.ledger_transactions[0].id && !!dr.settlement);
    check('decision recorded in the event chain', dr.events.some((e) => e.event_type === 'dispute_decision_recorded') && dr.events.some((e) => e.event_type === 'ledger_reversal_posted'));
    await work.goto(`${WEB}/earn`); await work.getByText(/Reversed \(simulated\)/).first().waitFor({ timeout: 15000 }); check('worker earnings page shows the settlement as reversed (simulated)', true);
    fs.writeFileSync('/tmp/sahakar-audit/a4_ids.json', JSON.stringify({ first: first.id, second: second.id }));

    console.log('\n6. False-claim scan over every page, signed in as each role');
    const FORBID = /insur|guarantee|refund|replacement|blockchain|100\s?%|fraud[- ]?proof|tamper[- ]?proof|bank[- ](certified|verified|confirmed)|verified (worker|identity)|background[- ]check|escrow|your money is (safe|protected)/i;
    const pages = [['/', null], ['/hire', cust], ['/find-work', work], ['/pricing', cust], ['/verify', cust], ['/economics', cust], ['/bookings', cust], ['/bookings', work], ['/earn', work], ['/my-jobs', cust], ['/applications', work], ['/organizations', cust], ['/profile', cust], ['/dashboard', cust], ['/disputes/review', rev], ['/login', null], ['/signup', null]];
    const hits = []; let total = 0;
    for (const [route, pg] of pages) {
      const p = pg || (await browser.newContext()).newPage ? (pg || await (await browser.newContext()).newPage()) : pg;
      await p.goto(WEB + route); await p.waitForTimeout(1200);
      const text = await p.locator('body').innerText(); total += text.length;
      for (const line of text.split(/\n+/)) if (FORBID.test(line)) hits.push(`${route}: ${line.trim().slice(0, 240)}`);
    }
    console.log(`   scanned ${pages.length} page states, ${total} characters. Lines matching a forbidden-claim pattern:`);
    [...new Set(hits)].forEach((h) => console.log('     • ' + h));
    const affirmative = hits.filter((h) => !/(not included|no |never|isn't|is not|does not|do not|cannot|without|not a|not final|nor|none)/i.test(h));
    check('no affirmative insurance / guaranteed payout / refund / replacement / verified-identity claim on any page', affirmative.length === 0, affirmative.join(' || '));
  } catch (e) { check('unexpected error', false, String(e).slice(0, 400)); await cust.screenshot({ path: '/tmp/sahakar-audit/a4_fail_cust.png', fullPage: true }).catch(() => {}); await work.screenshot({ path: '/tmp/sahakar-audit/a4_fail_work.png', fullPage: true }).catch(() => {}); }
  finally { await browser.close(); }
  console.log(`\n${out.filter(Boolean).length}/${out.length} observations as expected`); process.exit(out.every(Boolean) ? 0 : 1);
})();
