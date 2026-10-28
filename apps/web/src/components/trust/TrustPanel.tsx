import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronUp, Download, FileCheck2, Fingerprint, Repeat, Scale } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Alert, Field } from '@/components/marketplace/common';
import { errorMessage, marketplace, rupees, timeRange, when, type Agreement, type Booking } from '@/lib/marketplace';
import { ANCHOR_LABELS, downloadReceipt, trust, type AnchorStatus } from '@/lib/trust';

const BEARER_SHORT = { customer: 'customer pays', worker: 'from worker payout', business: 'organization pays', platform: 'platform absorbs' } as const;

/** The one itemised breakdown both parties see. Values come only from the server's current quote version. */
export function PriceBreakdown({ agreement, title = 'Agreed price breakdown' }: { agreement: Agreement; title?: string }) {
  const lines = agreement.line_items ?? [];
  const partyCharges = agreement.customer_total_paise - agreement.worker_share_paise;
  const allocated = agreement.worker_share_paise + agreement.platform_fee_paise + agreement.additional_charges_paise + agreement.tax_paise;
  return (
    <section aria-label={title} className="rounded-2xl bg-ink/5 p-3 text-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-ink">{title}</h3>
        {agreement.quote_version !== null && (
          <span className="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-ink/70" data-testid="quote-version">
            Quote v{agreement.quote_version}
          </span>
        )}
      </div>
      <dl className="space-y-1">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ink/70">Service price</dt>
          <dd className="font-bold tabular-nums" data-testid="amount-service-price">{rupees(agreement.service_price_paise)}</dd>
        </div>
        {lines.map((l) => (
          <div key={l.code} className="flex items-baseline justify-between gap-3 pl-3 text-xs" data-testid={`line-${l.code}`}>
            <dt className="text-ink/60">
              {l.label} <span className="text-ink/45">({BEARER_SHORT[l.bearer]}{l.kind === 'processing_charge' ? ', modeled' : ''})</span>
              {l.waived_by && <span className="block text-emerald-700">Waived by promotion “{l.waived_by}” (would be {rupees(l.computed_paise)})</span>}
            </dt>
            <dd className="tabular-nums">{l.bearer === 'worker' ? '−' : l.bearer === 'platform' ? '' : '+'}{rupees(l.amount_paise)}</dd>
          </div>
        ))}
        <div className="flex items-baseline justify-between gap-3 border-t border-ink/10 pt-1">
          <dt className="text-ink/70">Customer total<span className="block text-[11px] text-ink/45">What the customer pays.</span></dt>
          <dd className="font-bold tabular-nums" data-testid="amount-customer-total">{rupees(agreement.customer_total_paise)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ink/70">Worker payout</dt>
          <dd className="font-bold tabular-nums" data-testid="amount-worker-share">{rupees(agreement.worker_share_paise)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ink/70">Platform charges</dt>
          <dd className="font-bold tabular-nums" data-testid="amount-platform-fee">{rupees(agreement.platform_fee_paise)}</dd>
        </div>
        <div className="flex justify-between gap-3 text-ink/60"><dt>Processing charges (modeled)</dt><dd>{agreement.additional_charges_paise ? rupees(agreement.additional_charges_paise) : 'None'}</dd></div>
        <div className="flex justify-between gap-3 text-ink/60"><dt>Taxes</dt><dd>{agreement.taxes_modeled ? rupees(agreement.tax_paise) : 'Not modeled'}</dd></div>
        <div className="flex justify-between gap-3 border-t border-ink/10 pt-1 text-xs text-ink/60">
          <dt>Reconciliation</dt>
          <dd className={allocated === agreement.customer_total_paise ? 'text-emerald-700' : 'font-bold text-rose-700'}>
            {rupees(agreement.worker_share_paise)} + {rupees(partyCharges)} {allocated === agreement.customer_total_paise ? '= customer total' : '≠ customer total'}
          </dd>
        </div>
      </dl>
      <p className="mt-2 text-[11px] text-ink/50" data-testid="policy-ref">
        {agreement.fee_policy_id ? `Fee policy ${agreement.fee_policy_id} v${agreement.fee_policy_version}${agreement.pricing_model ? ` (${agreement.pricing_model.replace('_', ' ')})` : ''}. ` : ''}
        {agreement.is_example_policy ? 'Illustrative example policy — not final pricing. ' : ''}
        {agreement.tax_note}
      </p>
    </section>
  );
}

function AgreementStatus({ booking }: { booking: Booking }) {
  const a = booking.agreement!;
  if (a.evidence_level === 'legacy') return <Alert kind="info">{a.note}</Alert>;
  const stamp = (label: string, at: string | null, missingText: string) => (
    <li className={at ? 'text-emerald-700' : 'text-ink/50'}>{at ? `✓ ${label} accepted v${a.quote_version} · ${when(at)}` : missingText}</li>
  );
  return (
    <div className="text-xs">
      <ul className="space-y-0.5">
        {a.evidence_level === 'legacy_snapshot'
          ? <li className="text-ink/60">Legacy snapshot: the customer's acceptance was not recorded for this older booking.</li>
          : stamp('Customer', a.customer_accepted_at, 'Customer has not accepted this version yet')}
        {stamp('Worker', a.worker_accepted_at, a.awaiting_acceptance_from === 'worker' ? 'Waiting for the worker to accept this version' : 'Worker has not accepted this version')}
      </ul>
      {a.versions > 1 && <p className="mt-1 text-ink/50">This price was revised {a.versions - 1} time(s). Earlier versions are kept unchanged.</p>}
    </div>
  );
}

export function anchorText(status: string | null | undefined): string {
  if (!status) return 'No hash-chain evidence (legacy record)';
  return ANCHOR_LABELS[status as AnchorStatus] ?? status;
}

export function EvidenceStatus({ booking }: { booking: Booking }) {
  const e = booking.evidence;
  if (!e) return null;
  const ledger = {
    posted: `Simulated settlement recorded · ledger ${e.ledger_balanced ? 'balanced' : 'NOT balanced'}`,
    reversed: 'Simulated settlement reversed by a reviewer decision (original entries kept)',
    legacy_not_posted: 'Legacy simulated settlement (recorded before the ledger existed)',
    not_applicable_yet: 'No settlement yet (recorded only on completion)',
  }[e.ledger_status];
  const anchored = e.anchor.status === 'EXTERNALLY_ANCHORED';
  return (
    <dl className="grid gap-1 text-xs sm:grid-cols-2" aria-label="Evidence status">
      <div><dt className="font-semibold text-ink/70">Payment evidence</dt><dd className="text-amber-800">Simulated — no real money was collected or paid</dd></div>
      <div><dt className="font-semibold text-ink/70">Financial ledger</dt><dd>{ledger}</dd></div>
      <div><dt className="font-semibold text-ink/70">Receipt integrity</dt><dd>{e.event_count ? `${e.event_count} hash-chained events · latest ${e.latest_event_hash?.slice(0, 12)}…` : 'No hash-chain evidence (legacy record)'}</dd></div>
      <div>
        <dt className="font-semibold text-ink/70">External timestamp</dt>
        <dd className={anchored ? 'text-emerald-700' : 'text-ink/70'} data-testid="anchor-status">
          {anchorText(e.anchor.status)}
          {anchored && e.anchor.tsa_gen_time && ` · ${when(e.anchor.tsa_gen_time)}`}
          {e.anchor.status && !anchored && e.anchor.events_total > 0 && ` (${e.anchor.events_externally_anchored}/${e.anchor.events_total} events)`}
        </dd>
      </div>
    </dl>
  );
}

function LedgerRecord({ bookingId }: { bookingId: string }) {
  const record = useQuery({ queryKey: ['financial-record', bookingId], queryFn: () => trust.financialRecord(bookingId) });
  if (record.isLoading) return <p className="text-xs text-ink/50">Loading the recorded ledger…</p>;
  if (record.isError) return <Alert kind="error">{errorMessage(record.error)}</Alert>;
  const r = record.data!;
  return (
    <div className="space-y-3 text-xs">
      {r.ledger_transactions.length === 0 && <p className="text-ink/60">No ledger transaction yet. One is posted when the booking is completed.</p>}
      {r.ledger_transactions.map((tx) => (
        <div key={tx.id} className="rounded-xl border border-ink/10 p-2">
          <p className="font-semibold">{tx.transaction_type === 'simulated_settlement_reversal' ? 'Reversal (simulated)' : 'Settlement allocation (simulated)'} · {tx.balanced ? 'balanced' : 'NOT balanced'}</p>
          <table className="mt-1 w-full">
            <thead><tr className="text-left text-ink/50"><th>Account</th><th className="text-right">Debit</th><th className="text-right">Credit</th></tr></thead>
            <tbody>
              {tx.entries.map((e) => (
                <tr key={e.index}>
                  <td>{e.account.replace(/^simulated_/, '').replace(/_/g, ' ')}</td>
                  <td className="text-right tabular-nums">{e.direction === 'debit' ? rupees(e.amount_paise) : ''}</td>
                  <td className="text-right tabular-nums">{e.direction === 'credit' ? rupees(e.amount_paise) : ''}</td>
                </tr>
              ))}
              <tr className="border-t border-ink/10 font-semibold"><td>Total</td><td className="text-right">{rupees(tx.total_debits_paise)}</td><td className="text-right">{rupees(tx.total_credits_paise)}</td></tr>
            </tbody>
          </table>
        </div>
      ))}
      <div>
        <p className="font-semibold">Event history ({r.events.length})</p>
        <ol className="mt-1 space-y-0.5 font-mono text-[11px]">
          {r.events.map((e) => (
            <li key={e.sequence}>#{e.sequence} {e.event_type.replace(/_/g, ' ')} · {e.event_hash.slice(0, 16)}… · {e.checkpoint_index ? `checkpoint ${e.checkpoint_index}: ${anchorText(e.anchor_status)}` : 'not yet checkpointed'}</li>
          ))}
        </ol>
      </div>
      <p className="text-ink/50">{r.accounting_note}</p>
    </div>
  );
}

function QuoteRevision({ booking, onUpdate }: { booking: Booking; onUpdate: (b: Booking) => void }) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const revise = useMutation({ mutationFn: () => trust.reviseQuote(booking.id, Math.round(Number(amount) * 100)), onSuccess: (b) => { setOpen(false); onUpdate(b); } });
  // The booking keeps the fee policy it was quoted under; only the service price changes.
  if (!open) return <Button variant="ghost" className="px-3 py-1.5 text-xs" onClick={() => setOpen(true)}>Propose a different price</Button>;
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); revise.mutate(); }}>
      <Field label="New service price (₹)" htmlFor={`rv-${booking.id}`} hint="Creates a new quote version under the same fee policy. The other party must accept it.">
        <Input id={`rv-${booking.id}`} type="number" min={50} max={100000} value={amount} onChange={(e) => setAmount(e.target.value)} required />
      </Field>
      <Button type="submit" className="px-4 py-2" disabled={!amount || revise.isPending}>Send revised quote</Button>
      {revise.isError && <Alert kind="error">{errorMessage(revise.error)}</Alert>}
    </form>
  );
}

function RepeatHire({ booking }: { booking: Booking }) {
  const options = useQuery({ queryKey: ['repeat', booking.id], queryFn: () => trust.repeatOptions(booking.id) });
  const localities = useQuery({ queryKey: ['localities'], queryFn: marketplace.localities, staleTime: Infinity });
  const [slotId, setSlotId] = useState<string | null>(null);
  const [address, setAddress] = useState<string | null>(null);
  const request = useMutation({
    mutationFn: () => {
      const o = options.data!;
      const loc = localities.data?.find((l) => l.name === o.locality);
      if (!loc) throw new Error('Choose the location again from Hire; this locality is not in the list.');
      return marketplace.requestBooking({
        worker_profile_id: o.worker_profile_id, slot_id: slotId!, skill_id: o.skill.id, locality: loc.name,
        latitude: loc.latitude, longitude: loc.longitude, address_details: address ?? o.address_details, repeat_of_booking_id: booking.id,
      });
    },
  });
  if (options.isLoading) return <p className="text-xs text-ink/50">Loading {booking.worker_display_name}'s free slots…</p>;
  if (options.isError) return <Alert kind="error">{errorMessage(options.error)}</Alert>;
  const o = options.data!;
  if (!o.eligible) return <Alert kind="info">{o.reason}</Alert>;
  if (request.isSuccess) return <Alert kind="success">New booking requested with {o.worker_display_name} (quote v1 at today's rate). They must accept it. Your earlier booking is unchanged.</Alert>;
  const chosen = o.available_slots.find((s) => s.id === slotId);
  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-ink/60">{o.terms} Current rate: {o.current_hourly_rate_paise ? `${rupees(o.current_hourly_rate_paise)}/hour` : '—'} · {o.worker_verification_label}</p>
      {o.available_slots.length === 0 ? <p className="text-xs text-ink/50">No free slots right now. Try again later.</p> : (
        <div className="flex flex-wrap gap-2">
          {o.available_slots.map((s) => (
            <button key={s.id} type="button" aria-pressed={slotId === s.id} onClick={() => setSlotId(s.id)}
              className={`rounded-xl border px-3 py-2 text-left text-xs ${slotId === s.id ? 'border-plum bg-plum/10' : 'border-ink/15 hover:bg-ink/5'}`}>
              {timeRange(s.starts_at, s.ends_at)}<br /><span className="font-semibold">{rupees(s.customer_total_paise ?? s.service_price_paise)}</span>
            </button>
          ))}
        </div>
      )}
      {chosen && (
        <>
          <p className="text-xs">
            Service price {rupees(chosen.service_price_paise)} · customer total {chosen.customer_total_paise !== null ? rupees(chosen.customer_total_paise) : '—'} ·
            worker payout {chosen.worker_payout_paise !== null ? rupees(chosen.worker_payout_paise) : '—'} under {o.fee_policy ? `${o.fee_policy.policy_id} v${o.fee_policy.version}` : 'no active policy'}.
            The server records the binding quote when you send the request.
          </p>
          <Field label="Address" htmlFor={`rep-addr-${booking.id}`}>
            <Input id={`rep-addr-${booking.id}`} value={address ?? o.address_details} onChange={(e) => setAddress(e.target.value)} />
          </Field>
          <Button className="px-4 py-2" disabled={request.isPending} onClick={() => request.mutate()}>Request repeat booking</Button>
        </>
      )}
      {request.isError && <Alert kind="error">{errorMessage(request.error)}</Alert>}
    </div>
  );
}

/** Agreement, ledger and proof for one booking, shown identically to both parties. */
export function TrustPanel({ booking, onUpdate }: { booking: Booking; onUpdate: (b: Booking) => void }) {
  const qc = useQueryClient();
  const [showLedger, setShowLedger] = useState(false);
  const [showRepeat, setShowRepeat] = useState(false);
  const [downloaded, setDownloaded] = useState<string | null>(null);
  const actions = booking.agreement_actions ?? [];
  const a = booking.agreement;
  const acceptQuote = useMutation({ mutationFn: () => trust.acceptQuote(booking.id, a!.quote_version!), onSuccess: onUpdate });
  const download = useMutation({
    mutationFn: () => downloadReceipt(booking.id),
    onSuccess: () => { setDownloaded(new Date().toLocaleTimeString()); qc.invalidateQueries({ queryKey: ['financial-record', booking.id] }); },
  });
  if (!a) return null;
  return (
    <div className="space-y-3">
      <PriceBreakdown agreement={a} />
      <AgreementStatus booking={booking} />
      {booking.is_synthetic_demo && <p className="rounded-lg bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-900">Synthetic demo record: acceptances were recorded by a seed script for demo personas.</p>}
      {a.awaiting_acceptance_from === 'customer' && booking.my_role === 'customer' && (
        <Alert kind="info">
          The worker proposed a revised price (quote v{a.quote_version}). Review the breakdown above.
          <div className="mt-2"><Button className="px-4 py-2" disabled={acceptQuote.isPending} onClick={() => acceptQuote.mutate()}>Accept quote v{a.quote_version}</Button></div>
        </Alert>
      )}
      {acceptQuote.isError && <Alert kind="error">{errorMessage(acceptQuote.error)}</Alert>}
      <EvidenceStatus booking={booking} />
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" className="flex items-center gap-1.5 px-3 py-1.5 text-xs" disabled={download.isPending} onClick={() => download.mutate()}>
          <Download size={13} aria-hidden="true" /> Download receipt
        </Button>
        <Link to="/verify" className="flex items-center gap-1.5 rounded-full border border-ink/20 bg-white px-3 py-1.5 text-xs font-semibold text-ink hover:bg-ink/5">
          <FileCheck2 size={13} aria-hidden="true" /> Verify a receipt
        </Link>
        <Link to={`/bookings/${booking.id}/transparency`} className="flex items-center gap-1.5 rounded-full border border-plum/40 bg-plum/5 px-3 py-1.5 text-xs font-semibold text-plum hover:bg-plum/10">
          <Fingerprint size={13} aria-hidden="true" /> Transaction transparency
        </Link>
        <Button variant="ghost" className="flex items-center gap-1.5 px-3 py-1.5 text-xs" onClick={() => setShowLedger((v) => !v)} aria-expanded={showLedger}>
          Quick ledger view {showLedger ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </Button>
        {actions.includes('repeat') && (
          <Button variant="ghost" className="flex items-center gap-1.5 px-3 py-1.5 text-xs" onClick={() => setShowRepeat((v) => !v)} aria-expanded={showRepeat}>
            <Repeat size={13} aria-hidden="true" /> Book {booking.worker_display_name} again
          </Button>
        )}
        {actions.includes('revise_quote') && <QuoteRevision booking={booking} onUpdate={onUpdate} />}
      </div>
      {downloaded && <p className="text-xs text-emerald-700">Receipt saved at {downloaded}. Keep this file: it lets you check this record later without SAHAKAR.</p>}
      {download.isError && <Alert kind="error">{errorMessage(download.error)}</Alert>}
      {showLedger && <LedgerRecord bookingId={booking.id} />}
      {showRepeat && <RepeatHire booking={booking} />}
    </div>
  );
}

export function ProtectedBookingBenefits({ compact = false }: { compact?: boolean }) {
  const items: [string, string][] = [
    ['Agreed price record', 'Both of you see the same itemised total, worker share and fee, with a version number and acceptance time.'],
    ['Scheduling and history', 'Booked slots, changes and every past booking stay in your account.'],
    ['Transparent allocation', 'Completion posts a balanced ledger record: total = worker share + platform fee.'],
    ['Evidence-backed receipts', 'Download a receipt that you can check yourself, offline, at any time.'],
    ['Disputes reviewed by people', 'Report a problem; an independent human reviewer records a reasoned decision.'],
  ];
  return (
    <section aria-label="SAHAKAR Protected Booking" className={compact ? 'text-xs' : 'text-sm'}>
      <h3 className="flex items-center gap-1.5 font-bold text-ink"><Scale size={compact ? 14 : 18} className="text-plum" aria-hidden="true" />SAHAKAR Protected Booking</h3>
      <ul className="mt-2 space-y-1">
        {items.map(([t, d]) => <li key={t}><strong>{t}.</strong> <span className="text-ink/70">{d}</span></li>)}
      </ul>
      <p className="mt-2 text-ink/50">
        Not included: insurance, guaranteed refunds, guaranteed payouts, replacement workers, identity verification, or bank-confirmed payments. Payments are simulated in this pilot.
      </p>
    </section>
  );
}
