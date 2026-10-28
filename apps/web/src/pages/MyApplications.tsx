import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ClipboardList } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState, Loading } from '@/components/ui/States';
import { errorMessage, marketplace, rupees, when } from '@/lib/marketplace';
import { Alert, StatusPill } from '@/components/marketplace/common';

export function MyApplications() {
  const qc = useQueryClient();
  const apps = useQuery({ queryKey: ['my-applications'], queryFn: marketplace.myApplications });
  const withdraw = useMutation({
    mutationFn: marketplace.withdraw,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-applications'] }),
  });
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-3xl space-y-4">
        <h1 className="text-3xl font-black text-ink">My Applications</h1>
        <p className="text-ink/60">If a customer selects you, a booking request appears in <Link to="/bookings" className="font-semibold text-plum underline">My Bookings</Link> for you to confirm or decline.</p>
        {apps.isLoading && <Loading />}
        {apps.isError && <Alert kind="error">{errorMessage(apps.error)}</Alert>}
        {withdraw.isError && <Alert kind="error">{errorMessage(withdraw.error)}</Alert>}
        {apps.data?.length === 0 && (
          <Card><EmptyState icon={<ClipboardList size={24} />} title="No applications yet" action={{ label: 'Find work', href: '/find-work' }} /></Card>
        )}
        {apps.data?.map((a) => (
          <Card key={a.id} className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-bold text-ink">{a.job_title}</h2>
              <p className="text-sm text-ink/60">{a.job_locality} · {when(a.job_starts_at)} · {rupees(a.job_budget_paise)}</p>
              {a.status === 'selected' && <p className="mt-1 text-sm font-medium text-emerald-700">You were selected — confirm the booking in My Bookings.</p>}
            </div>
            <div className="flex items-center gap-2">
              <StatusPill status={a.status} />
              {a.status === 'applied' && (
                <Button variant="outline" className="px-4 py-2" disabled={withdraw.isPending} onClick={() => withdraw.mutate(a.id)}>Withdraw</Button>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
