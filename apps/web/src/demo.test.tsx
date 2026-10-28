import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import sample from './fixtures/receipt-sample.json';
import hybrid from './fixtures/receipt-hybrid.json';
import { TransactionTransparency, statusStatement } from './components/trust/TransactionTransparency';
import { TamperDemo } from './pages/TamperDemo';
import { DemoGuide } from './components/trust/DemoGuide';
import { AuthProvider } from './lib/auth';
import {
  compareHistories, editCommittedPayloads, editDisplayedSummary, forgeSelfConsistent, merkleRootOf, inclusionPathOf,
  tokenMentionsDigest, verifyReceiptInBrowser,
} from './lib/receiptVerify';

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const S = sample as any;
const wrap = (ui: ReactNode, route = '/') => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[route]}><Routes><Route path="*" element={ui} /></Routes></MemoryRouter></QueryClientProvider>);
};
afterEach(() => vi.unstubAllGlobals());

describe('Transaction Transparency explorer (rendered from a real exported receipt)', () => {
  it('Agreement view shows the committed amounts, quote version, bearers and acceptance evidence', async () => {
    wrap(<TransactionTransparency receipt={S} service="Desk Assembly" />);
    expect(screen.getByTestId('exp-total').textContent).toBe('₹500');
    expect(screen.getByTestId('exp-worker').textContent).toBe('₹450');
    expect(screen.getByTestId('exp-platform').textContent).toBe('₹50');
    expect(screen.getByTestId('exp-quote-version').textContent).toBe('v1');
    expect(screen.getByTestId('view-agreement').textContent).toMatch(/borne by worker/);
    expect(screen.getAllByTestId('acceptance')).toHaveLength(2);
    expect(screen.getByTestId('view-agreement').textContent).toMatch(/illustrative example, not final pricing|Fee policy/);
  });

  it('Ledger view: readable accounts, debits equal credits, SIMULATED label', async () => {
    wrap(<TransactionTransparency receipt={S} initialTab="ledger" />);
    expect(screen.getByTestId('view-ledger').textContent).toMatch(/SIMULATED — no real money moved/);
    const rows = screen.getAllByTestId('ledger-row').map((r) => r.textContent);
    expect(rows.join('|')).toMatch(/Customer payment clearing.*₹500/);
    expect(rows.join('|')).toMatch(/Worker allocation.*₹450/);
    expect(rows.join('|')).toMatch(/Platform service charge.*₹50/);
    expect(screen.getByTestId('total-debits').textContent).toBe('₹500');
    expect(screen.getByTestId('total-credits').textContent).toBe('₹500');
    expect(screen.getByTestId('reconciliation').textContent).toMatch(/^Balanced/);
  });

  it('Ledger view reports an unbalanced posting instead of hiding it', async () => {
    const t = clone(S);
    t.events.find((e: any) => e.event_type === 'simulated_settlement_recorded').payload.data.ledger_transaction.entries[1].amount_paise = 40000;
    wrap(<TransactionTransparency receipt={t} initialTab="ledger" />);
    expect(screen.getByTestId('reconciliation').textContent).toMatch(/^NOT balanced/);
  });

  it('Proof view lists the chain with truncated, copyable hashes and the honest anchor state', async () => {
    const writeText = vi.fn(async () => {});
    Object.assign(navigator, { clipboard: { writeText } });
    wrap(<TransactionTransparency receipt={S} initialTab="proof" />);
    expect(screen.getAllByTestId('proof-event')).toHaveLength(S.events.length);
    const short = screen.getAllByTestId('hash-short')[0].textContent!;
    expect(short).toContain('…');
    expect(short.length).toBeLessThan(30);
    fireEvent.click(screen.getAllByRole('button', { name: /Copy full previous hash/ })[0]);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(S.events[0].previous_event_hash));
    expect(screen.getByTestId('anchor-line').textContent).toMatch(/External timestamp verified/);   // the stored status for this receipt
    expect(screen.getByTestId('anchor-line').textContent).toMatch(/token contains this checkpoint hash/);
    await waitFor(() => expect(screen.getByTestId('local-result').textContent).toMatch(/recompute correctly/));
  });

  it('Verification view: local result is computed, and the browser never claims external verification', async () => {
    wrap(<TransactionTransparency receipt={S} initialTab="verify" />);
    await waitFor(() => expect(screen.getByTestId('verify-statement').textContent).toMatch(/Local integrity verified/));
    expect(screen.getByTestId('verify-statement').textContent).not.toMatch(/externally (timestamped|verified)/i);
    expect(screen.getByTestId('view-verification').textContent).toMatch(/does not prove: |What it does not prove/);
    expect(screen.getByTestId('view-verification').textContent).toMatch(/verify_receipt\.py/);
  });

  it('a receipt without any token says anchoring has not completed', async () => {
    const h = clone(hybrid) as any;
    wrap(<TransactionTransparency receipt={h} initialTab="verify" />);
    await waitFor(() => expect(screen.getByTestId('verify-statement').textContent).toBe('Local integrity verified. External anchoring not yet completed.'));
  });

  it('a tampered receipt shows a failure with reasons', async () => {
    const t = editDisplayedSummary(S, { worker_share_paise: 36000 });
    wrap(<TransactionTransparency receipt={t} initialTab="verify" />);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/Verification failed/));
    expect(screen.getByTestId('view-verification').textContent).toMatch(/worker share|worker_share/i);
  });

  it('statusStatement never produces an "external" success', async () => {
    const v = await verifyReceiptInBrowser(clone(S));
    expect(statusStatement(S, v).text).not.toMatch(/externally (timestamped|verified)/i);
    expect(statusStatement(S, null).tone).toBe('warn');
  });
});

describe('tamper functions run the real verification', () => {
  it('Merkle helpers agree with the receipt', async () => {
    const hashes = S.events.map((e: any) => e.event_hash);
    const cp = S.checkpoints[S.checkpoints.length - 1];
    expect(cp.body.event_count).toBeGreaterThanOrEqual(hashes.length);
    const root = await merkleRootOf(hashes);
    expect(root).toMatch(/^[0-9a-f]{64}$/);
    expect((await inclusionPathOf(hashes, 0)).length).toBeGreaterThan(0);
  });

  it('A. edit only the displayed summary -> FAILED', async () => {
    const v = await verifyReceiptInBrowser(editDisplayedSummary(S, { worker_share_paise: 36000 }));
    expect(v.result).toBe('VERIFICATION FAILED');
  });

  it('B. edit the committed payload but keep hashes -> FAILED at the hash check', async () => {
    const v = await verifyReceiptInBrowser(editCommittedPayloads(S, { worker_share_paise: 36000, customer_total_paise: 40000, platform_fee_paise: 4000 }));
    expect(v.result).toBe('VERIFICATION FAILED');
    expect(v.failures.some((f) => /payload hash|event hash/.test(f.check))).toBe(true);
  });

  it('C1. hidden deduction with every hash recomputed still FAILS: worker + charges must equal the total', async () => {
    const forged = await forgeSelfConsistent(S, { worker_share_paise: 36000 });
    const v = await verifyReceiptInBrowser(forged);
    expect(v.result).toBe('VERIFICATION FAILED');
  });

  it('C2. consistent forgery (all amounts -20%, all hashes recomputed): local integrity passes, but it is exposed by the retained original and the timestamp token', async () => {
    const forged = await forgeSelfConsistent(S, { customer_total_paise: 40000, worker_share_paise: 36000, platform_fee_paise: 4000 });
    const v = await verifyReceiptInBrowser(forged);
    expect(v.failures).toEqual([]);
    expect(v.result).toBe('LOCAL INTEGRITY VERIFIED');
    expect(forged.checkpoints[0].external_timestamp).toBeNull();
    expect(compareHistories(S, forged).identical).toBe(false);
    expect(compareHistories(S, forged).diffs.every((d) => d.status === 'changed' || d.status === 'same')).toBe(true);
    const originalCp = S.checkpoints[S.checkpoints.length - 1];
    expect(tokenMentionsDigest(originalCp.external_timestamp.time_stamp_response_der_b64, originalCp.digest)).toBe(true);
    expect(tokenMentionsDigest(originalCp.external_timestamp.time_stamp_response_der_b64, forged.checkpoints[0].digest)).toBe(false);
    expect(compareHistories(S, clone(S)).identical).toBe(true);
  });

  it('the original receipt object is never mutated by the tamper helpers', async () => {
    const before = JSON.stringify(S);
    editDisplayedSummary(S, { worker_share_paise: 1 }); editCommittedPayloads(S, { worker_share_paise: 1 }); await forgeSelfConsistent(S, { worker_share_paise: 1 });
    expect(JSON.stringify(S)).toBe(before);
  });
});

describe('Tamper demonstration page', () => {
  const stub = () => vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url);
    const body = u.includes('/demo/guide') ? { enabled: true, showcase: [{ key: 'headline-percentage', label: 'Headline booking' }], personas: [], steps: [] }
      : u.includes('/demo/showcase/') ? S : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));

  it('runs real verification on the edited copy and shows the failure; never contacts a write endpoint', async () => {
    stub();
    wrap(<TamperDemo />);
    await screen.findByTestId('td-original');
    fireEvent.click(screen.getByTestId('preset-hidden'));
    fireEvent.click(screen.getByRole('button', { name: /Run verification on the altered copy/ }));
    await waitFor(() => expect(screen.getByTestId('td-outcome').textContent).toMatch(/Verification FAILED/));
    expect(screen.getByTestId('td-failures').textContent).toMatch(/worker share|worker_share|customer total/i);
    const methods = (fetch as any).mock.calls.map((c: any[]) => (c[1]?.method ?? 'GET'));
    expect(methods.every((m: string) => m === 'GET')).toBe(true);
  });

  it('consistent-forgery mode explains the limits instead of pretending local hashes are enough', async () => {
    stub();
    wrap(<TamperDemo />);
    await screen.findByTestId('td-original');
    fireEvent.click(screen.getByLabelText(/C\. Change the amounts and recompute every hash/));
    fireEvent.click(screen.getByTestId('preset-consistent'));
    fireEvent.click(screen.getByRole('button', { name: /Run verification on the altered copy/ }));
    await waitFor(() => expect(screen.getByTestId('td-outcome').textContent).toMatch(/internally consistent/));
    const limits = screen.getByTestId('td-limits');
    expect(limits.textContent).toMatch(/Why local hashes alone are not enough/);
    expect(screen.getByTestId('td-token').textContent).toMatch(/does not contain it/);
  });
});

describe('Demo guide is development-only and never handles the passcode', () => {
  it('renders nothing outside dev-identity mode', () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ enabled: true }), { status: 200 })));
    const { container } = wrap(<AuthProvider><DemoGuide /></AuthProvider>);
    // vitest runs with VITE_AUTH_MODE unset => supabase mode => the guide must be absent
    expect(container.querySelector('[data-testid="demo-guide"]')).toBeNull();
  });
});
