import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Building2, Calculator, History, Receipt } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Loading } from '@/components/ui/States';
import { Alert } from '@/components/marketplace/common';
import { ProtectedBookingBenefits } from '@/components/trust/TrustPanel';
import { errorMessage, rupees, when } from '@/lib/marketplace';
import { BEARER_LABELS, describeComponent, trust } from '@/lib/trust';

/** Public pricing policy. Everything shown comes from the ACTIVE fee_policies record via GET /api/v1/fee-policy. */
export function Pricing() {
  const policy = useQuery({ queryKey: ['fee-policy'], queryFn: trust.feePolicy, staleTime: 60_000 });
  const history = useQuery({ queryKey: ['fee-policy-history'], queryFn: trust.feePolicyHistory, staleTime: 60_000 });
  const anchoring = useQuery({ queryKey: ['anchoring'], queryFn: trust.anchoring, staleTime: 60_000 });
  const data = policy.data;
  const p = data?.active_policy;
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-plum">Pricing policy</p>
          <h1 className="text-3xl font-black text-ink">How SAHAKAR–SEVA charges</h1>
          <p className="mt-2 text-ink/60">Free to join. Charges come from a published, versioned fee policy. Both sides of a booking see the same numbers.</p>
        </div>
        {policy.isLoading && <Loading />}
        {policy.isError && <Alert kind="error">Could not load the fee policy from the server: {errorMessage(policy.error)}</Alert>}
        {data && !p && <Alert kind="info">No fee policy is active, so new bookings cannot be priced right now.</Alert>}
        {data && p && (
          <>
            <Card className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-xl font-bold text-ink" data-testid="policy-label">{p.label}</h2>
                  <p className="text-xs text-ink/60" data-testid="policy-ref">Policy {p.policy_id} · version {p.version} · {p.pricing_model.replace('_', ' ')} · active since {p.activated_at ? when(p.activated_at) : '—'}</p>
                </div>
                <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-bold uppercase text-amber-800">Payments {data.rules.payments_mode}</span>
              </div>
              {p.is_example && (
                <Alert kind="info"><strong>Illustrative example policy.</strong> {data.rules.not_final_pricing}</Alert>
              )}
              {p.description && <p className="text-sm text-ink/70">{p.description}</p>}
              <div>
                <h3 className="text-sm font-semibold text-ink">Charges</h3>
                {p.components.length === 0 ? <p className="text-sm text-ink/60">This policy has no charges.</p> : (
                  <ul className="mt-1 space-y-1 text-sm" data-testid="policy-components">
                    {p.components.map((c) => (
                      <li key={c.code} className="rounded-xl border border-ink/10 p-2">
                        <strong>{c.label}</strong> <span className="text-xs text-ink/50">({c.kind === 'processing_charge' ? 'modeled processing charge' : 'platform charge'})</span>
                        <br /><span className="text-ink/70">{describeComponent(c)}. {BEARER_LABELS[c.bearer]}.</span>
                        {c.organization_bookings !== 'any' && <span className="block text-xs text-ink/50">{c.organization_bookings === 'only' ? 'Organization bookings only.' : 'Not applied to organization bookings.'}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {p.promotions.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-ink">Promotions</h3>
                  <ul className="mt-1 list-disc pl-5 text-sm text-ink/70">
                    {p.promotions.map((pr) => (
                      <li key={pr.code}>{pr.label}{pr.ends_at ? ` (until ${when(pr.ends_at)})` : ''}{pr.max_service_price_paise ? `, services up to ${rupees(pr.max_service_price_paise)}` : ''}. Waived amounts are still shown on the receipt.</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-sm text-ink/70">Safety ceiling: total charges on a booking never exceed <strong>{p.max_total_charge_bps / 100}%</strong> of the service price under this policy (absolute platform limit {p.absolute_ceiling_bps / 100}%). A price that would exceed it is refused, not adjusted.</p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="policy-examples">
                  <caption className="mb-1 text-left text-xs text-ink/60">{data.examples_note}</caption>
                  <thead><tr className="text-left text-xs text-ink/50"><th>Service price</th><th>Customer total</th><th>Worker payout</th><th>Platform charges</th></tr></thead>
                  <tbody>
                    {data.examples.map((e) => (
                      <tr key={e.service_price_paise} className="border-t border-ink/5">
                        <td>{rupees(e.service_price_paise)}</td>
                        {e.error ? <td colSpan={3} className="text-xs text-rose-700">{e.error}</td> : (
                          <><td>{rupees(e.customer_total_paise!)}</td><td>{rupees(e.worker_payout_paise!)}</td><td>{rupees(e.platform_fee_paise!)}{e.waived_paise ? ` (${rupees(e.waived_paise)} waived)` : ''}</td></>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <dl className="space-y-2 text-sm">
                {([
                  ['Free for individuals', data.rules.free_for_individuals.join(' · ')],
                  ['When charges apply', data.rules.assessed_when],
                  ['Cancellations', data.rules.cancellations],
                  ['Disputes', data.rules.disputes],
                  ['Existing bookings', data.rules.existing_agreements],
                  ['Taxes', data.rules.tax_note],
                  ['Processing charges', data.rules.processing_note],
                  ['Payments', data.rules.payments_note],
                  ['Organization terms', 'An organization may have its own fee terms. Owners and admins can see them before posting; they apply only to that organization\'s bookings.'],
                ] as const).map(([k, v]) => (
                  <div key={k} className="grid gap-1 sm:grid-cols-[180px_1fr]"><dt className="font-semibold text-ink">{k}</dt><dd className="text-ink/70">{v}</dd></div>
                ))}
              </dl>
              <p className="break-all text-[11px] text-ink/45">Definition hash {p.definition_hash}. Every booking receipt carries the policy definition and this hash, so charges can be recomputed independently.</p>
            </Card>

            {history.data && history.data.length > 1 && (
              <Card className="space-y-2">
                <h2 className="flex items-center gap-2 text-lg font-bold text-ink"><History size={18} className="text-plum" aria-hidden="true" />Policy history</h2>
                <ul className="text-sm">
                  {history.data.map((h) => (
                    <li key={h.fee_policy_record_id} className="border-t border-ink/5 py-1">{h.policy_id} v{h.version} · {h.status} · {h.pricing_model} · {h.label}</li>
                  ))}
                </ul>
              </Card>
            )}

            <Card><ProtectedBookingBenefits /></Card>

            <Card className="space-y-2">
              <h2 className="flex items-center gap-2 text-xl font-bold text-ink"><Receipt size={20} className="text-plum" aria-hidden="true" />Verifiable receipts</h2>
              <p className="text-sm text-ink/70">
                Each financial step of a booking is written to an append-only, hash-chained record. Checkpoints of that record
                {anchoring.data?.tsa_configured
                  ? ` are submitted to an external RFC 3161 timestamp service (${anchoring.data.tsa_name}). Only a 32-byte digest is sent.`
                  : ' are kept locally. No external timestamp service is configured on this server, so receipts show local integrity only.'}
              </p>
              <Link to="/verify" className="text-sm font-semibold text-plum underline">Check a receipt yourself</Link>
            </Card>

            <Card className="space-y-3">
              <h2 className="flex items-center gap-2 text-xl font-bold text-ink"><Building2 size={20} className="text-plum" aria-hidden="true" />For businesses and cooperatives</h2>
              <p className="text-sm text-ink/70">Available today for organization owners and admins, at no extra charge:</p>
              <ul className="list-disc pl-5 text-sm text-ink/70">
                <li>Booking and spending summary for jobs posted on behalf of the organization (Organizations page)</li>
                <li>Downloadable CSV of those booking records</li>
                <li>“Post a similar job” templates from earlier jobs (reviewed before posting)</li>
              </ul>
              <div className="rounded-2xl border border-dashed border-ink/20 p-3 text-sm">
                <p className="font-semibold text-ink">Business tools subscription — Planned, not currently available</p>
                <p className="mt-1 text-ink/70">Possible future tools: team-level service management, consolidated multi-site reports, scheduled repeat work. No subscription price has been set; any figure used in modelling is illustrative and has not been validated with customers. There is no way to subscribe or pay.</p>
              </div>
            </Card>

            <p className="text-center text-sm"><Link to="/economics" className="inline-flex items-center gap-1 font-semibold text-plum underline"><Calculator size={14} aria-hidden="true" />Model pricing options and sustainability (assumptions clearly marked)</Link></p>
          </>
        )}
      </div>
    </div>
  );
}
