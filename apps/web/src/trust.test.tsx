import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import sample from './fixtures/receipt-sample.json';
import hybrid from './fixtures/receipt-hybrid.json';
import { verifyReceiptInBrowser, canonicalize } from './lib/receiptVerify';
import { TrustPanel, EvidenceStatus } from './components/trust/TrustPanel';
import { ReceiptVerifier } from './components/trust/ReceiptVerifier';
import { Pricing } from './pages/Pricing';
import { scenario } from './pages/Economics';
import type { Booking } from './lib/marketplace';

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><BrowserRouter>{ui}</BrowserRouter></QueryClientProvider>);
}

function booking(role: 'customer' | 'worker', anchor: string | null = 'LOCAL_ONLY'): Booking {
  return {
    id: 'b1', origin: 'direct', status: 'completed', my_role: role, job_id: null,
    skill: { id: 's', category_id: 'c', slug: 'desk-assembly', name: 'Desk Assembly', description: null, is_active: true },
    worker_profile_id: 'w', worker_display_name: 'Ravi', worker_verification_label: 'Not verified — self-declared profile',
    customer_display_name: 'Asha', starts_at: '2026-11-01T10:00:00Z', ends_at: '2026-11-01T12:00:00Z', locality: 'HSR Layout',
    address_details: null, address_hidden_reason: null, customer_notes: null,
    price: { price_paise: 50000, fee_bps: 1000, fee_paise: 5000, payout_paise: 45000, fee_policy: 'Pilot assumption' },
    settlement: null, dispute: null, allowed_actions: [], created_at: '', updated_at: '',
    agreement_actions: ['download_receipt'],
    agreement: {
      service_price_paise: 50000, pricing_model: 'percentage', policy_definition_hash: 'ab'.repeat(32), is_example_policy: true,
      line_items: [{ code: 'platform_service_fee', kind: 'platform_fee', label: 'Platform service fee', bearer: 'worker', percent_bps: 1000,
        fixed_paise: 0, min_paise: null, max_paise: null, computed_paise: 5000, amount_paise: 5000, waived_by: null }],
      evidence_level: 'versioned', note: null, quote_id: 'q1', quote_version: 1, source: 'booking_request', versions: 1,
      customer_total_paise: 50000, worker_share_paise: 45000, platform_fee_paise: 5000, additional_charges_paise: 0, tax_paise: 0,
      taxes_modeled: false, fee_bps: 1000, fee_policy_id: 'illustrative-pilot-example', fee_policy_version: '1', currency: 'INR',
      created_at: '2026-10-28T00:00:00Z', customer_accepted_at: '2026-10-28T00:00:00Z', worker_accepted_at: '2026-10-28T00:01:00Z',
      awaiting_acceptance_from: null, matches_booking_snapshot: true, tax_note: 'No taxes are modeled.', additional_charges_note: 'None.',
    },
    evidence: {
      payment_evidence: 'SIMULATED', payment_evidence_status: 'SIMULATED', ledger_status: 'posted', ledger_transaction_id: 't1',
      ledger_balanced: true, reversal_transaction_id: null, event_count: 6, latest_event_hash: 'ab'.repeat(32),
      anchor: { status: anchor, label: '', checkpoint_index: anchor === 'EXTERNALLY_ANCHORED' ? 1 : null, tsa_gen_time: anchor === 'EXTERNALLY_ANCHORED' ? '2026-10-28T00:02:00Z' : null, events_externally_anchored: 0, events_total: 6 },
    },
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('browser receipt verifier', () => {
  it('canonicalizes like RFC 8785 for the integer profile', () => {
    expect(canonicalize({ b: 1, a: [true, null, 'x"\n'] })).toBe('{"a":[true,null,"x\\"\\n"],"b":1}');
    expect(() => canonicalize({ a: 1.5 })).toThrow();
  });

  it('accepts a genuine receipt captured from the local stack, but never claims external verification', async () => {
    const r = await verifyReceiptInBrowser(clone(sample));
    expect(r.failures).toEqual([]);
    expect(r.result).toBe('LOCAL INTEGRITY VERIFIED');
    expect(r.external).toMatch(/does not check timestamp signatures/);
  });

  it('recomputes a hybrid policy with a waiver and a platform-absorbed charge', async () => {
    const r = await verifyReceiptInBrowser(clone(hybrid));
    expect(r.failures).toEqual([]);
    expect(r.result).toBe('LOCAL INTEGRITY VERIFIED');
  });

  it.each([
    ['hidden waiver', (x: any) => { x.events[0].payload.data.quote.line_items[1].amount_paise = 1500; }],
    ['swapped policy definition', (x: any) => { x.events[0].payload.data.quote.policy_definition.components[0].percent_bps = 100; }],
    ['policy id shown', (x: any) => { x.summary.fee_policy_id = 'cheaper-policy'; }],
    ['service price shown', (x: any) => { x.summary.service_price_paise = 40000; }],
  ])('detects a tampered hybrid receipt: %s', async (_n, mutate) => {
    const t = clone(hybrid);
    mutate(t);
    expect((await verifyReceiptInBrowser(t)).result).toBe('VERIFICATION FAILED');
  });

  it.each([
    ['customer total', (x: any) => { x.summary.customer_total_paise = 40000; }],
    ['worker payout', (x: any) => { x.summary.worker_share_paise = 36000; }],
    ['platform fee', (x: any) => { x.summary.platform_fee_paise = 14000; }],
    ['booking id', (x: any) => { x.summary.booking_id = '00000000-0000-0000-0000-000000000000'; }],
    ['quote version', (x: any) => { x.summary.quote_version = 2; }],
    ['committed payload', (x: any) => { x.events[0].payload.data.quote.worker_share_paise = 36000; }],
    ['event hash', (x: any) => { x.events[1].event_hash = 'cd'.repeat(32); }],
    ['checkpoint', (x: any) => { x.checkpoints[0].body.merkle_root = '00'.repeat(32); }],
    ['removed event', (x: any) => { x.events.splice(1, 1); }],
    ['anchoring claim without token', (x: any) => { x.checkpoints[0].external_timestamp = null; }],
  ])('detects a tampered %s', async (_name, mutate) => {
    const t = clone(sample);
    mutate(t);
    const r = await verifyReceiptInBrowser(t);
    expect(r.result).toBe('VERIFICATION FAILED');
    expect(r.failures.length).toBeGreaterThan(0);
  });
});

describe('transparency components', () => {
  const amounts = () => ['service-price', 'customer-total', 'worker-share', 'platform-fee'].map((id) => screen.getByTestId(`amount-${id}`).textContent);

  it('shows service price, each line item with its bearer, and the policy reference', () => {
    wrap(<TrustPanel booking={booking('worker')} onUpdate={() => {}} />);
    expect(screen.getByTestId('amount-service-price').textContent).toBe('₹500');
    expect(screen.getByTestId('line-platform_service_fee').textContent).toMatch(/from worker payout.*−₹50/);
    expect(screen.getByTestId('policy-ref').textContent).toMatch(/illustrative-pilot-example v1.*Illustrative example policy — not final pricing/);
  });

  it('customer and worker see identical authoritative values', () => {
    const { unmount } = wrap(<TrustPanel booking={booking('customer')} onUpdate={() => {}} />);
    const customerView = amounts();
    unmount();
    wrap(<TrustPanel booking={booking('worker')} onUpdate={() => {}} />);
    expect(amounts()).toEqual(customerView);
    expect(customerView).toEqual(['₹500', '₹500', '₹450', '₹50']);
    expect(screen.getByTestId('quote-version').textContent).toBe('Quote v1');
  });

  it('never shows an external-timestamp claim without verified evidence', () => {
    for (const status of ['LOCAL_ONLY', 'ANCHOR_PENDING', 'ANCHOR_SUBMITTED', 'ANCHOR_FAILED', 'PROOF_INVALID', null]) {
      const { unmount } = wrap(<EvidenceStatus booking={booking('worker', status)} />);
      expect(screen.getByTestId('anchor-status').textContent).not.toMatch(/External timestamp verified/);
      unmount();
    }
    wrap(<EvidenceStatus booking={booking('worker', 'EXTERNALLY_ANCHORED')} />);
    expect(screen.getByTestId('anchor-status').textContent).toMatch(/External timestamp verified/);
  });

  it('describes settlements as simulated, never as transferred money', () => {
    const { container } = wrap(<EvidenceStatus booking={booking('worker')} />);
    expect(container.textContent).toMatch(/Simulated — no real money was collected or paid/);
    expect(container.textContent).not.toMatch(/payment (received|confirmed)|paid out to you/i);
  });

  it('downloads the receipt from the API as a file', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(sample), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const created: string[] = [];
    (URL as any).createObjectURL = (b: Blob) => { created.push(b.type); return 'blob:x'; };
    (URL as any).revokeObjectURL = () => {};
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    wrap(<TrustPanel booking={booking('customer')} onUpdate={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Download receipt/i }));
    await waitFor(() => expect(screen.getByText(/Receipt saved at/)).toBeInTheDocument());
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toMatch(/\/api\/v1\/bookings\/b1\/receipt$/);
    expect(created).toEqual(['application/json']);
  });

  it('shows verification errors clearly', async () => {
    wrap(<ReceiptVerifier />);
    const input = screen.getByLabelText(/Receipt file/i) as HTMLInputElement;
    const bad = clone(sample);
    bad.summary.worker_share_paise = 36000;
    fireEvent.change(input, { target: { files: [new File([JSON.stringify(bad)], 'r.json', { type: 'application/json' })] } });
    await waitFor(() => expect(screen.getByTestId('verify-result').textContent).toBe('Verification failed'));
    expect(screen.getByRole('alert').textContent).toMatch(/Verification failed/);
    fireEvent.change(input, { target: { files: [new File(['not json'], 'r.json')] } });
    await waitFor(() => expect(screen.getByText(/not valid JSON/)).toBeInTheDocument());
  });
});

describe('pricing and economics', () => {
  it('pricing page renders whatever policy the backend says is active (fixed customer fee here)', async () => {
    const comp = { code: 'booking_fee', kind: 'platform_fee', label: 'Booking fee', bearer: 'customer', percent_bps: 0, fixed_paise: 2500,
      min_paise: null, max_paise: null, applies_to_origins: ['direct', 'job'], organization_bookings: 'any' };
    const policy = {
      active_policy: {
        fee_policy_record_id: 'r', policy_id: 'fixed-fee-trial', version: 3, scope: 'default', label: 'Fixed booking fee trial', description: '',
        is_example: false, status: 'active', pricing_model: 'fixed', max_total_charge_bps: 1200, absolute_ceiling_bps: 2000, definition_hash: 'cd'.repeat(32),
        definition: {}, components: [{ ...comp, description: 'x' }], promotions: [], subscription_plan_code: null, activated_at: '2026-10-28T00:00:00Z', retired_at: null,
      },
      examples: [{ service_price_paise: 50000, customer_total_paise: 52500, worker_payout_paise: 50000, platform_fee_paise: 2500, processing_charge_paise: 0, waived_paise: 0 }],
      examples_note: 'Illustrative service prices.',
      rules: { assessed_when: 'a', cancellations: 'b', disputes: 'c', existing_agreements: 'd', bearers: {}, tax_note: 'No taxes are modeled.',
        processing_note: 'e', payments_mode: 'simulated', payments_note: 'Payments are simulated.', free_for_individuals: ['Registration'], not_final_pricing: 'f' },
    };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(
      String(url).endsWith('/fee-policy') ? policy : String(url).endsWith('/fee-policies') ? [] : { tsa_configured: false, statuses: {} }),
      { status: 200, headers: { 'Content-Type': 'application/json' } })));
    const { container } = wrap(<Pricing />);
    await waitFor(() => expect(screen.getByTestId('policy-label').textContent).toBe('Fixed booking fee trial'));
    expect(screen.getByTestId('policy-ref').textContent).toMatch(/fixed-fee-trial · version 3 · fixed/);
    expect(screen.getByTestId('policy-components').textContent).toMatch(/₹25 fixed.*Paid by customer/);
    expect(screen.getByTestId('policy-examples').textContent).toMatch(/₹525/);
    expect(container.textContent).not.toMatch(/10%/);  // nothing hardcoded
    expect(container.textContent).not.toMatch(/Illustrative example policy/);  // this mock is not an example
    expect(container.textContent).toMatch(/Planned, not currently available/);
    expect(container.textContent).not.toMatch(/Subscribe now|Pay now/i);
    expect(screen.queryByRole('button', { name: /subscribe|pay/i })).toBeNull();
  });

  it('scenario calculator is pure arithmetic on stated assumptions', () => {
    const r = scenario({ bookingsPerMonth: 100, avgBookingRupees: 500, avgPlatformChargeRupees: 50, paymentCostPercent: 2, supportCostPerBooking: 0,
      cacPerNewCustomer: 0, newCustomersPerMonth: 0, disputeRatePercent: 0, costPerDispute: 0, fixedMonthly: 0, leakagePercent: 50,
      subscribers: 0, subscriptionPrice: 999 });
    expect(r.onPlatform).toBe(50);
    expect(r.feeRevenue).toBe(2500);
    expect(r.net).toBe(2500 - 500);
  });
});
