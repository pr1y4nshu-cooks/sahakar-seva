import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Calculator, Database, SlidersHorizontal, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/marketplace/common';
import { useAuth } from '@/lib/auth';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Alert, Field } from '@/components/marketplace/common';
import { errorMessage, marketplace, rupees } from '@/lib/marketplace';
import { BEARER_LABELS, trust, type Bearer, type PolicyComponent, type PolicyDefinition } from '@/lib/trust';

type Assumptions = {
  bookingsPerMonth: number; avgBookingRupees: number; avgPlatformChargeRupees: number; paymentCostPercent: number;
  supportCostPerBooking: number; cacPerNewCustomer: number; newCustomersPerMonth: number; disputeRatePercent: number;
  costPerDispute: number; fixedMonthly: number; leakagePercent: number; subscribers: number; subscriptionPrice: number;
};

const DEFAULTS: Assumptions = {
  bookingsPerMonth: 1000, avgBookingRupees: 600, avgPlatformChargeRupees: 0, paymentCostPercent: 2, supportCostPerBooking: 8,
  cacPerNewCustomer: 150, newCustomersPerMonth: 200, disputeRatePercent: 2, costPerDispute: 120, fixedMonthly: 150000,
  leakagePercent: 30, subscribers: 0, subscriptionPrice: 999,
};

export function scenario(a: Assumptions) {
  const onPlatform = a.bookingsPerMonth * (1 - a.leakagePercent / 100);
  const gmv = onPlatform * a.avgBookingRupees;
  const feeRevenue = onPlatform * a.avgPlatformChargeRupees;
  const subscriptionRevenue = a.subscribers * a.subscriptionPrice;
  const paymentCost = gmv * (a.paymentCostPercent / 100);
  const support = onPlatform * a.supportCostPerBooking;
  const disputes = onPlatform * (a.disputeRatePercent / 100) * a.costPerDispute;
  const acquisition = a.newCustomersPerMonth * a.cacPerNewCustomer;
  const variable = paymentCost + support + disputes;
  const contribution = feeRevenue + subscriptionRevenue - variable;
  const net = contribution - acquisition - a.fixedMonthly;
  return { onPlatform, gmv, feeRevenue, subscriptionRevenue, paymentCost, support, disputes, acquisition, variable, contribution, net };
}

const FIELDS: [keyof Assumptions, string, string][] = [
  ['bookingsPerMonth', 'Bookings arranged per month', 'Before leakage'],
  ['avgBookingRupees', 'Average booking value (₹)', ''],
  ['avgPlatformChargeRupees', 'Average platform charge per booking (₹)', 'Use the policy simulator above to derive it'],
  ['paymentCostPercent', 'Payment processing cost (% of value)', 'Future regulated provider'],
  ['supportCostPerBooking', 'Support cost per booking (₹)', ''],
  ['cacPerNewCustomer', 'Acquisition cost per new customer (₹)', ''],
  ['newCustomersPerMonth', 'New customers per month', ''],
  ['disputeRatePercent', 'Disputed bookings (%)', ''],
  ['costPerDispute', 'Cost to review one dispute (₹)', ''],
  ['fixedMonthly', 'Fixed operating cost per month (₹)', ''],
  ['leakagePercent', 'Assumed off-platform leakage (%)', 'Scenario only — never measured'],
  ['subscribers', 'Business subscribers (planned product)', 'Not available today'],
  ['subscriptionPrice', 'Illustrative subscription price (₹/month)', 'Not a real plan'],
];

function RecordedFigures() {
  const { user } = useAuth();
  const reviewer = useQuery({ queryKey: ['reviewer-status', user?.id], queryFn: marketplace.reviewerStatus, enabled: !!user });
  const summary = useQuery({ queryKey: ['economics'], queryFn: trust.economics, enabled: !!reviewer.data?.is_dispute_reviewer });
  if (!user) return <p className="text-sm text-ink/60">Recorded platform totals are visible to signed-in platform staff only.</p>;
  if (reviewer.data && !reviewer.data.is_dispute_reviewer) return <p className="text-sm text-ink/60">Recorded platform totals are visible to platform staff (dispute reviewers) only.</p>;
  if (summary.isError) return <Alert kind="error">{errorMessage(summary.error)}</Alert>;
  const s = summary.data;
  if (!s) return <p className="text-sm text-ink/50">Loading recorded figures…</p>;
  const rows: [string, string][] = [
    ['Completed bookings (recorded)', String(s.completed_bookings)],
    ['Total booking value', rupees(s.total_booking_value_paise)],
    ['Simulated platform fee allocations', rupees(s.total_simulated_platform_fees_paise)],
    ['Simulated worker payouts', rupees(s.total_simulated_worker_payouts_paise)],
    ['Average booking value', rupees(s.average_booking_value_paise)],
    ['Average fee per booking', rupees(s.average_fee_per_booking_paise)],
    ['Party-borne charges / customer totals', `${s.effective_fee_bps / 100}%`],
    ['Active policy', s.active_policy ? `${s.active_policy.policy_id} v${s.active_policy.version}${s.active_policy.is_example ? ' (example)' : ''}` : 'none'],
    ['With ledger evidence / legacy', `${s.settlements_with_ledger_evidence} / ${s.legacy_settlements_without_ledger}`],
    ['Reversed by dispute decisions', `${s.reversed_settlements} (${rupees(s.reversed_value_paise)})`],
  ];
  return (
    <div>
      <dl className="grid gap-2 sm:grid-cols-3" data-testid="recorded-figures">
        {rows.map(([k, v]) => <div key={k} className="rounded-2xl bg-ink/5 p-3"><dt className="text-xs text-ink/60">{k}</dt><dd className="font-bold">{v}</dd></div>)}
      </dl>
      <p className="mt-2 text-xs text-amber-800">{s.note}</p>
    </div>
  );
}

const BLANK: PolicyComponent = {
  code: 'platform_service_fee', kind: 'platform_fee', label: 'Platform service fee', bearer: 'worker', percent_bps: 0, fixed_paise: 0,
  min_paise: null, max_paise: null, applies_to_origins: ['direct', 'job'], organization_bookings: 'any',
};

/** Candidate-policy simulator. The server's pricing engine evaluates it; nothing is saved or activated. */
function PolicySimulator({ onAverage }: { onAverage: (rupeesPerBooking: number) => void }) {
  const { user } = useAuth();
  const policy = useQuery({ queryKey: ['fee-policy'], queryFn: trust.feePolicy, staleTime: 60_000 });
  const [draft, setDraft] = useState<PolicyDefinition | null>(null);
  const [prices, setPrices] = useState('200, 500, 1000, 2000');
  const [recorded, setRecorded] = useState(false);
  useEffect(() => {
    if (!draft && policy.data) {
      const d = policy.data.active_policy?.definition;
      setDraft(d ? { ...d, label: `Candidate based on ${policy.data.active_policy!.policy_id} (scenario)`, is_example: true }
        : { label: 'Candidate policy (scenario)', description: '', is_example: true, components: [BLANK], promotions: [], max_total_charge_bps: 1500, subscription_plan_code: null });
    }
  }, [policy.data, draft]);
  const sim = useMutation({
    mutationFn: () => trust.simulate(draft!, prices.split(',').map((x) => Math.round(Number(x.trim()) * 100)).filter((x) => x > 0), recorded),
  });
  if (!draft) return <p className="text-sm text-ink/50">Loading the active policy…</p>;
  const setComp = (i: number, patch: Partial<PolicyComponent>) =>
    setDraft({ ...draft, components: draft.components.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  const num = (v: string) => (v === '' ? null : Math.round(Number(v) * 100));
  const run = sim.data?.recorded_bookings ?? sim.data?.samples;
  const avg = run && run.totals.bookings ? run.totals.platform_fee_paise / run.totals.bookings / 100 : null;
  return (
    <div className="space-y-3 text-sm">
      {draft.components.map((c, i) => (
        <div key={i} className="grid gap-2 rounded-xl border border-ink/10 p-2 sm:grid-cols-7">
          <Input aria-label={`Component ${i + 1} label`} value={c.label} onChange={(e) => setComp(i, { label: e.target.value })} className="sm:col-span-2" />
          <Select aria-label={`Component ${i + 1} bearer`} value={c.bearer} onChange={(e) => setComp(i, { bearer: e.target.value as Bearer, organization_bookings: e.target.value === 'business' ? 'only' : c.organization_bookings === 'only' ? 'any' : c.organization_bookings, kind: e.target.value === 'platform' ? 'processing_charge' : c.kind })}>
            {(Object.keys(BEARER_LABELS) as Bearer[]).map((b) => <option key={b} value={b}>{BEARER_LABELS[b]}</option>)}
          </Select>
          <Input aria-label={`Component ${i + 1} percent`} type="number" min={0} step="0.1" placeholder="%" value={c.percent_bps / 100} onChange={(e) => setComp(i, { percent_bps: Math.round(Number(e.target.value) * 100) })} />
          <Input aria-label={`Component ${i + 1} fixed rupees`} type="number" min={0} placeholder="₹ fixed" value={c.fixed_paise / 100} onChange={(e) => setComp(i, { fixed_paise: Math.round(Number(e.target.value) * 100) })} />
          <Input aria-label={`Component ${i + 1} minimum rupees`} type="number" min={0} placeholder="₹ min" value={c.min_paise === null ? '' : c.min_paise / 100} onChange={(e) => setComp(i, { min_paise: num(e.target.value) })} />
          <div className="flex gap-1">
            <Input aria-label={`Component ${i + 1} maximum rupees`} type="number" min={0} placeholder="₹ max" value={c.max_paise === null ? '' : c.max_paise / 100} onChange={(e) => setComp(i, { max_paise: num(e.target.value) })} />
            <button type="button" aria-label={`Remove component ${i + 1}`} onClick={() => setDraft({ ...draft, components: draft.components.filter((_, j) => j !== i), promotions: [] })} className="px-1 text-rose-600"><Trash2 size={14} /></button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap items-end gap-3">
        <button type="button" className="flex items-center gap-1 text-sm font-semibold text-plum" disabled={draft.components.length >= 5}
          onClick={() => setDraft({ ...draft, components: [...draft.components, { ...BLANK, code: `charge_${draft.components.length + 1}`, label: `Charge ${draft.components.length + 1}` }] })}>
          <Plus size={14} /> Add charge
        </button>
        <Field label="Ceiling (% of service price, max 20)" htmlFor="sim-ceiling">
          <Input id="sim-ceiling" type="number" min={0} max={20} step="0.5" value={draft.max_total_charge_bps / 100} onChange={(e) => setDraft({ ...draft, max_total_charge_bps: Math.round(Number(e.target.value) * 100) })} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.promotions.length > 0} onChange={(e) => setDraft({ ...draft, promotions: e.target.checked ? [{ code: 'scenario_waiver', label: 'Scenario: all charges waived', waives: draft.components.map((c) => c.code), starts_at: null, ends_at: null, max_service_price_paise: null, organization_bookings: 'any' }] : [] })} />
          Waive all charges (promotion scenario)
        </label>
      </div>
      <Field label="Sample service prices (₹, comma-separated)" htmlFor="sim-prices"><Input id="sim-prices" value={prices} onChange={(e) => setPrices(e.target.value)} /></Field>
      {user && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={recorded} onChange={(e) => setRecorded(e.target.checked)} /> Also re-price recorded completed bookings (platform staff only; hypothetical)</label>}
      <Button className="px-4 py-2" disabled={sim.isPending} onClick={() => sim.mutate()}>Evaluate candidate policy</Button>
      {sim.isError && <Alert kind="error">{errorMessage(sim.error)}</Alert>}
      {sim.data && (
        <div className="space-y-2" data-testid="simulation-results">
          <p className="text-xs text-ink/60">Pricing model: {sim.data.pricing_model}. {sim.data.recorded_note ?? 'Sample prices only.'}</p>
          <table className="w-full text-xs">
            <thead><tr className="text-left text-ink/50"><th>Service</th><th>Customer total</th><th>Worker payout</th><th>Platform</th><th>Note</th></tr></thead>
            <tbody>
              {sim.data.samples.items.map((it, i) => (
                <tr key={i} className="border-t border-ink/5">
                  <td>{rupees(it.service_price_paise)}</td>
                  {it.refused ? <td colSpan={4} className="text-rose-700">Refused: {it.refused.replace(/_/g, ' ').toLowerCase()}</td> : (
                    <><td>{rupees(it.customer_total_paise!)}</td><td>{rupees(it.worker_payout_paise!)}</td><td>{rupees(it.platform_fee_paise!)}</td><td>{it.waived_paise ? `${rupees(it.waived_paise)} waived` : ''}</td></>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {sim.data.recorded_bookings && (
            <p className="text-xs">Recorded bookings re-priced: {sim.data.recorded_bookings.totals.bookings} priced, {sim.data.recorded_bookings.totals.refused} refused · platform charges {rupees(sim.data.recorded_bookings.totals.platform_fee_paise)} · worker payouts {rupees(sim.data.recorded_bookings.totals.worker_payout_paise)}</p>
          )}
          {avg !== null && <Button variant="outline" className="px-3 py-1.5 text-xs" onClick={() => onAverage(Math.round(avg * 100) / 100)}>Use average platform charge ({rupees(Math.round(avg * 100))}) in the calculator</Button>}
        </div>
      )}
    </div>
  );
}

export function Economics() {
  const [overrides, setOverrides] = useState<Partial<Assumptions>>({});
  const a: Assumptions = { ...DEFAULTS, ...overrides };
  const r = useMemo(() => scenario(a), [a]);
  const money = (rupeesValue: number) => rupees(Math.round(rupeesValue * 100));
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-plum">Internal demonstration</p>
          <h1 className="text-3xl font-black text-ink">Unit economics</h1>
          <p className="mt-2 text-ink/60">Two separate parts: figures recorded in this demo's database, and a calculator driven only by assumptions you type in.</p>
        </div>
        <Card>
          <h2 className="mb-3 flex items-center gap-2 text-xl font-bold text-ink"><Database size={20} className="text-plum" aria-hidden="true" />Recorded in the demo database</h2>
          <RecordedFigures />
        </Card>
        <Card className="space-y-3">
          <h2 className="flex items-center gap-2 text-xl font-bold text-ink"><SlidersHorizontal size={20} className="text-plum" aria-hidden="true" />Fee policy simulator (candidate, not saved)</h2>
          <p className="text-sm text-ink/60">Try percentage, fixed, hybrid, minimum/maximum, split bearers or a waiver. The server's pricing engine evaluates it with the same rules bookings use. Nothing is activated; final pricing is decided separately.</p>
          <PolicySimulator onAverage={(v) => setOverrides((o) => ({ ...o, avgPlatformChargeRupees: v }))} />
        </Card>
        <Card className="space-y-4">
          <h2 className="flex items-center gap-2 text-xl font-bold text-ink"><Calculator size={20} className="text-plum" aria-hidden="true" />Scenario calculator (assumptions, not data)</h2>
          <p className="text-sm text-amber-800">Every input below is a hypothetical. Leakage, costs and subscribers have not been measured. Results are not forecasts.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            {FIELDS.map(([key, label, hint]) => (
              <Field key={key} label={label} htmlFor={`eco-${key}`} hint={hint || undefined}>
                <Input id={`eco-${key}`} type="number" min={0} value={a[key]} onChange={(e) => setOverrides((o) => ({ ...o, [key]: Number(e.target.value) }))} />
              </Field>
            ))}
          </div>
          <dl className="grid gap-2 sm:grid-cols-4" data-testid="scenario-results">
            {([
              ['On-platform bookings', Math.round(r.onPlatform).toLocaleString('en-IN')],
              ['Booking value', money(r.gmv)],
              ['Fee revenue (scenario)', money(r.feeRevenue)],
              ['Subscription revenue (scenario)', money(r.subscriptionRevenue)],
              ['Variable costs', money(r.variable)],
              ['Contribution', money(r.contribution)],
              ['Acquisition', money(r.acquisition)],
              ['Monthly result', money(r.net)],
            ] as const).map(([k, v]) => (
              <div key={k} className={`rounded-2xl p-3 ${k === 'Monthly result' ? (r.net >= 0 ? 'bg-emerald-50' : 'bg-rose-50') : 'bg-ink/5'}`}><dt className="text-xs text-ink/60">{k}</dt><dd className="font-bold">{v}</dd></div>
            ))}
          </dl>
          <p className="text-xs text-ink/50">Formula: on-platform = bookings × (1 − leakage); fee revenue = on-platform × average platform charge; contribution = fees + subscriptions − (payment + support + dispute costs); result = contribution − acquisition − fixed costs.</p>
        </Card>
      </div>
    </div>
  );
}
