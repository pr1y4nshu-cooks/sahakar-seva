import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { BarChart3, ChevronDown, ChevronUp, Download } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Alert, StatusPill } from '@/components/marketplace/common';
import { errorMessage, rupees, when } from '@/lib/marketplace';
import { downloadOrgCsv, trust } from '@/lib/trust';

/** Owner/admin view of the organization's own job-post bookings. Data comes from recorded rows only. */
export function OrgDashboard({ orgId }: { orgId: string }) {
  const [open, setOpen] = useState(false);
  const summary = useQuery({ queryKey: ['org-summary', orgId], queryFn: () => trust.orgSummary(orgId), enabled: open });
  const csv = useMutation({ mutationFn: () => downloadOrgCsv(orgId) });
  return (
    <div className="mt-3 border-t border-[#eee8f2] pt-3">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-1.5 text-sm font-semibold text-plum">
        <BarChart3 size={15} aria-hidden="true" /> Booking and spending records {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>
      {open && summary.isLoading && <p className="mt-2 text-xs text-ink/50">Loading records…</p>}
      {open && summary.isError && <div className="mt-2"><Alert kind="error">{errorMessage(summary.error)}</Alert></div>}
      {open && summary.data && (
        <div className="mt-3 space-y-3 text-sm">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5" data-testid="org-metrics">
            {([
              ['Jobs posted', String(summary.data.jobs_posted)],
              ['Bookings created', String(summary.data.bookings_created)],
              ['Completed', String(summary.data.completed_bookings)],
              ['Agreed spend (completed)', rupees(summary.data.agreed_spend_completed_paise)],
              ['Platform fees (completed)', rupees(summary.data.platform_fees_completed_paise)],
            ] as const).map(([k, v]) => <div key={k} className="rounded-xl bg-ink/5 p-2"><dt className="text-[11px] text-ink/60">{k}</dt><dd className="font-bold">{v}</dd></div>)}
          </dl>
          {summary.data.bookings.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-ink/50"><th>Job</th><th>When</th><th>Worker</th><th>Status</th><th className="text-right">Total</th><th className="text-right">Fee</th></tr></thead>
                <tbody>
                  {summary.data.bookings.map((b) => (
                    <tr key={b.booking_id} className="border-t border-ink/5">
                      <td>{b.job_title}</td><td>{when(b.starts_at)}</td><td>{b.worker_display_name}</td><td><StatusPill status={b.status} /></td>
                      <td className="text-right tabular-nums">{rupees(b.customer_total_paise)}</td><td className="text-right tabular-nums">{rupees(b.platform_fee_paise)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" className="flex items-center gap-1.5 px-3 py-1.5 text-xs" disabled={csv.isPending} onClick={() => csv.mutate()}>
              <Download size={13} aria-hidden="true" /> Download CSV
            </Button>
            <Link to="/my-jobs" className="text-xs font-semibold text-plum underline">Reuse a past job as a template</Link>
          </div>
          {csv.isError && <Alert kind="error">{errorMessage(csv.error)}</Alert>}
          <p className="text-[11px] text-ink/50">{summary.data.scope_note} {summary.data.note}</p>
          <p className="text-[11px] text-ink/50" data-testid="org-subscription-note">Business subscription tools: <strong>planned, not currently available</strong>. Charges above follow this organization&apos;s active fee terms (<Link to="/pricing" className="underline">pricing</Link>); there is nothing to subscribe to or pay.</p>
        </div>
      )}
    </div>
  );
}
