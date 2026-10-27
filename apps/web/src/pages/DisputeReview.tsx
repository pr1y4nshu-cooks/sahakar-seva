import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Scale } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState, ErrorState, Loading } from '@/components/ui/States';
import { errorMessage, marketplace, rupees, when, type DisputeQueueItem } from '@/lib/marketplace';
import { Alert, Field, Select, StatusPill, TextArea } from '@/components/marketplace/common';

export function DisputeReview() {
  const queue = useQuery({ queryKey: ['review-queue'], queryFn: marketplace.reviewQueue, retry: false });
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <h1 className="flex items-center gap-2 text-3xl font-black text-ink"><Scale className="text-plum" /> Dispute review</h1>
        <p className="text-ink/60">Human review only. Record an outcome and the reason. Decisions never automatically restrict a worker.</p>
        {queue.isLoading && <Loading />}
        {queue.isError && ((queue.error as any)?.status === 403
          ? <Card><ErrorState type="forbidden" message="Only authorised dispute reviewers can open this page." /></Card>
          : <Alert kind="error">{errorMessage(queue.error)}</Alert>)}
        {queue.data?.length === 0 && <Card><EmptyState icon={<Scale size={24} />} title="No disputes" /></Card>}
        {queue.data?.map((d) => <DisputeCard key={d.id} item={d} />)}
      </div>
    </div>
  );
}

function DisputeCard({ item: d }: { item: DisputeQueueItem }) {
  const qc = useQueryClient();
  const [outcome, setOutcome] = useState('no_fault');
  const [reason, setReason] = useState('');
  const resolve = useMutation({
    mutationFn: () => marketplace.resolveDispute(d.id, outcome, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['review-queue'] }),
  });
  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-bold text-ink">{d.skill_name} · {d.locality} · {when(d.starts_at)} · {rupees(d.price_paise)}</h2>
          <p className="text-sm text-ink/60">Customer: {d.customer_display_name} · Worker: {d.worker_display_name} · opened by the {d.opened_by_role}</p>
        </div>
        <StatusPill status={d.status} />
      </div>
      <p className="rounded-xl bg-ink/5 p-3 text-sm">“{d.description}”</p>
      {d.status === 'resolved' && (
        <Alert kind="success">Outcome: <strong>{d.outcome?.replace(/_/g, ' ')}</strong> — {d.resolution_reason}</Alert>
      )}
      {d.status === 'open' && !d.can_resolve && <Alert kind="info">You are a party to this booking, so you cannot review it.</Alert>}
      {d.can_resolve && (
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); resolve.mutate(); }}>
          <Field label="Outcome" htmlFor={`out-${d.id}`}>
            <Select id={`out-${d.id}`} value={outcome} onChange={(e) => setOutcome(e.target.value)}>
              <option value="resolved_for_customer">Resolved in the customer's favour</option>
              <option value="resolved_for_worker">Resolved in the worker's favour</option>
              <option value="no_fault">No fault found</option>
            </Select>
          </Field>
          <Field label="Reason (recorded and shown to both parties)" htmlFor={`why-${d.id}`}>
            <TextArea id={`why-${d.id}`} value={reason} onChange={(e) => setReason(e.target.value)} minLength={10} required />
          </Field>
          {resolve.isError && <Alert kind="error">{errorMessage(resolve.error)}</Alert>}
          <Button type="submit" disabled={reason.trim().length < 10 || resolve.isPending}>Record decision</Button>
        </form>
      )}
    </Card>
  );
}
