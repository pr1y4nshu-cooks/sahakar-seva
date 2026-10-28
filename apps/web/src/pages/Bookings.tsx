import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarCheck } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState, Loading } from '@/components/ui/States';
import { DISPUTE_CATEGORIES, errorMessage, marketplace, rupees, timeRange, type Booking, type BookingAction } from '@/lib/marketplace';
import { Alert, Field, Select, SimulatedPaymentBanner, StatusPill, TextArea } from '@/components/marketplace/common';
import { ProtectedBookingBenefits, TrustPanel } from '@/components/trust/TrustPanel';
import { trust } from '@/lib/trust';

const ACTION_LABELS: Record<Exclude<BookingAction, 'dispute'>, string> = {
  accept: 'Accept booking',
  decline: 'Decline',
  start: 'Start work',
  complete: 'Confirm work completed',
  cancel: 'Cancel booking',
};

export function Bookings() {
  const [role, setRole] = useState<'all' | 'customer' | 'worker'>('all');
  const bookings = useQuery({ queryKey: ['my-bookings'], queryFn: marketplace.myBookings, refetchInterval: 15_000 });
  const visible = (bookings.data ?? []).filter((b) => role === 'all' || b.my_role === role);
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <h1 className="text-3xl font-black text-ink">My Bookings</h1>
        <p className="text-ink/60">Bookings where you are hiring and where you are working. The same account does both.</p>
        <div role="tablist" aria-label="Filter bookings" className="inline-flex rounded-full border border-ink/10 bg-white p-1">
          {(['all', 'customer', 'worker'] as const).map((r) => (
            <button key={r} role="tab" aria-selected={role === r} onClick={() => setRole(r)}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold ${role === r ? 'bg-plum text-white' : 'text-ink/60'}`}>
              {r === 'all' ? 'All' : r === 'customer' ? 'I am hiring' : 'I am working'}
            </button>
          ))}
        </div>
        {bookings.isLoading && <Loading />}
        {bookings.isError && <Alert kind="error">{errorMessage(bookings.error)}</Alert>}
        {bookings.data && visible.length === 0 && (
          <Card><EmptyState icon={<CalendarCheck size={24} />} title="No bookings yet" description="Book a worker from Hire, or apply to jobs from Find Work." /></Card>
        )}
        {visible.map((b) => <BookingCard key={b.id} booking={b} />)}
        <Card><ProtectedBookingBenefits compact /></Card>
      </div>
    </div>
  );
}

function BookingCard({ booking: b }: { booking: Booking }) {
  const qc = useQueryClient();
  const [disputeText, setDisputeText] = useState('');
  const [category, setCategory] = useState('other_booking_issue');
  const [showDispute, setShowDispute] = useState(false);
  const refresh = (data: Booking) => {
    qc.setQueryData<Booking[]>(['my-bookings'], (old) => old?.map((x) => (x.id === data.id ? data : x)));
    qc.invalidateQueries({ queryKey: ['earnings'] });
    qc.invalidateQueries({ queryKey: ['my-slots'] });
  };
  // Accepting always names the exact quote version the worker saw, so a changed price can never be accepted by accident.
  const act = useMutation({
    mutationFn: (a: Exclude<BookingAction, 'dispute'>) =>
      a === 'accept' ? trust.acceptBooking(b.id, b.agreement?.quote_version ?? null) : marketplace.bookingAction(b.id, a),
    onSuccess: refresh,
  });
  const financial = category !== 'other_booking_issue';
  const dispute = useMutation({
    mutationFn: () => marketplace.openDispute(b.id, disputeText, category, financial ? b.evidence?.latest_event_hash ?? undefined : undefined),
    onSuccess: (d) => { setShowDispute(false); refresh(d); },
  });
  const transitions = b.allowed_actions.filter((a): a is Exclude<BookingAction, 'dispute'> => a !== 'dispute');

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-ink/50">
            {b.my_role === 'customer' ? 'You are hiring' : 'You are working'} · {b.origin === 'direct' ? 'Direct hire' : 'From a job post'}
          </p>
          <h2 className="text-lg font-bold text-ink">{b.skill.name} · {b.my_role === 'customer' ? b.worker_display_name : b.customer_display_name}</h2>
          <p className="text-sm text-ink/60">{timeRange(b.starts_at, b.ends_at)} · {b.locality}</p>
          {b.my_role === 'customer' && <p className="text-xs text-amber-800">{b.worker_verification_label}</p>}
        </div>
        <StatusPill status={b.status} />
      </div>
      <p className="text-sm">
        <span className="font-medium">Address: </span>
        {b.address_details ?? <span className="text-ink/50">{b.address_hidden_reason}</span>}
      </p>
      {b.customer_notes && <p className="text-sm text-ink/70">Notes: {b.customer_notes}</p>}

      {b.agreement ? (
        <TrustPanel booking={b} onUpdate={refresh} />
      ) : (
        <dl className="grid grid-cols-3 gap-2 rounded-2xl bg-ink/5 p-3 text-center text-sm">
          <div><dt className="text-xs text-ink/60">Agreed price</dt><dd className="font-bold">{rupees(b.price.price_paise)}</dd></div>
          <div><dt className="text-xs text-ink/60">Platform charges</dt><dd className="font-bold">{rupees(b.price.fee_paise)}</dd></div>
          <div><dt className="text-xs text-ink/60">Worker payout</dt><dd className="font-bold">{rupees(b.price.payout_paise)}</dd></div>
        </dl>
      )}
      <p className="text-xs text-ink/50">{b.price.fee_policy}</p>
      {b.settlement && (
        <div className="space-y-1">
          <SimulatedPaymentBanner label={b.settlement.label} />
          <p className="text-xs text-ink/60">Simulated settlement recorded (no real money moved): {rupees(b.settlement.gross_paise)} = {rupees(b.settlement.fee_paise)} fee + {rupees(b.settlement.payout_paise)} worker share.</p>
        </div>
      )}
      {b.dispute && (
        <Alert kind={b.dispute.status === 'resolved' ? 'success' : 'info'}>
          Dispute {b.dispute.status}{b.dispute.opened_by_me ? ' (opened by you)' : ''}{b.dispute.category ? ` · ${DISPUTE_CATEGORIES.find(([k]) => k === b.dispute!.category)?.[1] ?? b.dispute.category}` : ''}: “{b.dispute.description}”
          {b.dispute.ledger_correction === 'full_reversal' && <><br />The reviewer recorded a full reversal of the simulated settlement. The original ledger entries are kept.</>}
          {b.dispute.outcome && <><br />Human reviewer decision: <strong>{b.dispute.outcome.replace(/_/g, ' ')}</strong> — {b.dispute.resolution_reason}</>}
          {!b.dispute.outcome && <><br />Awaiting review by an independent human reviewer.</>}
        </Alert>
      )}

      {(act.isError || dispute.isError) && <Alert kind="error">{errorMessage(act.error ?? dispute.error)}</Alert>}
      <div className="flex flex-wrap gap-2">
        {transitions.map((a) => (
          <Button key={a} variant={a === 'decline' || a === 'cancel' ? 'outline' : 'primary'} className="px-4 py-2" disabled={act.isPending}
            onClick={() => (a !== 'cancel' || window.confirm('Cancel this booking?')) && act.mutate(a)}>
            {ACTION_LABELS[a]}
          </Button>
        ))}
        {b.allowed_actions.includes('dispute') && !showDispute && (
          <Button variant="ghost" className="px-4 py-2" onClick={() => setShowDispute(true)}>Report a problem</Button>
        )}
      </div>
      {showDispute && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); dispute.mutate(); }}>
          <Field label="What kind of problem?" htmlFor={`dsc-${b.id}`}>
            <Select id={`dsc-${b.id}`} value={category} onChange={(e) => setCategory(e.target.value)}>
              {DISPUTE_CATEGORIES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
          </Field>
          {financial && <p className="text-xs text-ink/60">Quote v{b.agreement?.quote_version ?? '—'}, the ledger record and the latest receipt event will be attached for the reviewer. Only the reviewer and the two parties can see them.</p>}
          <Field label="Describe the problem (reviewed by a human; no automatic penalties)" htmlFor={`dsp-${b.id}`}>
            <TextArea id={`dsp-${b.id}`} value={disputeText} onChange={(e) => setDisputeText(e.target.value)} minLength={10} maxLength={2000} required />
          </Field>
          <Button type="submit" disabled={disputeText.trim().length < 10 || dispute.isPending} className="px-4 py-2">Open dispute</Button>
        </form>
      )}
    </Card>
  );
}
