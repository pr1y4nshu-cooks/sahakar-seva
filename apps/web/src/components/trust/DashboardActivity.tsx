import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CalendarCheck, ClipboardList, Receipt, Wallet } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { StatusPill } from '@/components/marketplace/common';
import { marketplace, rupees, timeRange } from '@/lib/marketplace';

/** Real records for the signed-in account. Nothing here is decorative: every number comes from the API. */
export function DashboardActivity() {
  const bookings = useQuery({ queryKey: ['my-bookings'], queryFn: marketplace.myBookings, retry: false });
  const applications = useQuery({ queryKey: ['my-applications'], queryFn: marketplace.myApplications, retry: false });
  const earnings = useQuery({ queryKey: ['earnings'], queryFn: marketplace.earnings, retry: false });
  const all = bookings.data ?? [];
  const upcoming = all.filter((b) => ['requested', 'confirmed', 'in_progress'].includes(b.status));
  const needsMe = all.filter((b) => b.allowed_actions.includes('accept') || b.agreement_actions?.includes('accept_quote'));
  const completed = all.filter((b) => b.status === 'completed' || (b.status === 'disputed' && b.settlement));
  const apps = applications.data ?? [];
  const appCounts = apps.reduce<Record<string, number>>((m, a) => ({ ...m, [a.status]: (m[a.status] ?? 0) + 1 }), {});
  const e = earnings.data;
  return (
    <div className="mb-8 space-y-4" data-testid="dashboard-activity">
      <h2 className="text-xl font-bold text-ink">My activity</h2>
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="p-4"><CalendarCheck className="h-6 w-6 text-plum" aria-hidden="true" /><p className="mt-2 text-2xl font-bold" data-testid="dash-upcoming">{upcoming.length}</p><p className="text-sm text-ink/60">Upcoming / active bookings</p></Card>
        <Card className="p-4"><ClipboardList className="h-6 w-6 text-plum" aria-hidden="true" /><p className="mt-2 text-2xl font-bold" data-testid="dash-applications">{apps.length}</p><p className="text-sm text-ink/60">Applications{apps.length ? ` (${Object.entries(appCounts).map(([k, v]) => `${v} ${k}`).join(', ')})` : ''}</p></Card>
        <Card className="p-4"><Receipt className="h-6 w-6 text-plum" aria-hidden="true" /><p className="mt-2 text-2xl font-bold" data-testid="dash-completed">{completed.length}</p><p className="text-sm text-ink/60">Completed with receipts</p></Card>
        <Card className="p-4"><Wallet className="h-6 w-6 text-plum" aria-hidden="true" /><p className="mt-2 text-2xl font-bold" data-testid="dash-earnings">{e ? rupees(e.ledger_totals?.net_simulated_payout_paise ?? e.totals.payout_paise) : '₹0'}</p><p className="text-sm text-ink/60">Simulated earnings (not real money)</p></Card>
      </div>
      {needsMe.length > 0 && (
        <Card className="border-amber-300 bg-amber-50 p-4" data-testid="dash-needs-action">
          <p className="font-semibold text-amber-900">Waiting for you</p>
          <ul className="mt-1 text-sm">{needsMe.map((b) => <li key={b.id}>{b.skill.name} · {b.my_role === 'worker' ? `request from ${b.customer_display_name}` : `revised price from ${b.worker_display_name}`} · {timeRange(b.starts_at, b.ends_at)} — <Link to="/bookings" className="font-semibold text-plum underline">review</Link></li>)}</ul>
        </Card>
      )}
      <Card className="p-4">
        <p className="font-semibold text-ink">Recent bookings and their evidence</p>
        {all.length === 0 && <p className="mt-1 text-sm text-ink/60">No bookings yet. <Link to="/hire" className="font-semibold text-plum underline">Hire a worker</Link> or <Link to="/find-work" className="font-semibold text-plum underline">find work</Link>.</p>}
        <ul className="mt-2 divide-y divide-ink/10 text-sm">
          {all.slice(0, 6).map((b) => (
            <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>{b.skill.name} · {b.my_role === 'customer' ? b.worker_display_name : b.customer_display_name} · {timeRange(b.starts_at, b.ends_at)}</span>
              <span className="flex items-center gap-2"><StatusPill status={b.status} />
                {b.agreement && <span className="text-xs">{rupees(b.agreement.customer_total_paise)} total</span>}
                <Link to={`/bookings/${b.id}/transparency`} className="text-xs font-semibold text-plum underline">Ledger &amp; receipt</Link></span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-ink/50">Settlements and ledger entries are simulated.</p>
      </Card>
    </div>
  );
}
