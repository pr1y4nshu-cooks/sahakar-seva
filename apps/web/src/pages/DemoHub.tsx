import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, FlaskConical } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Loading } from '@/components/ui/States';
import { Alert } from '@/components/marketplace/common';
import { TransactionTransparency } from '@/components/trust/TransactionTransparency';
import { errorMessage, rupees } from '@/lib/marketplace';
import { ANCHOR_LABELS, publicApi, type AnchorStatus } from '@/lib/trust';

export function DemoHub() {
  const guide = useQuery({ queryKey: ['demo-guide'], queryFn: publicApi.demoGuide, retry: false });
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-[0.2em] text-plum"><FlaskConical size={16} aria-hidden="true" />Demo marketplace — sample data</p>
        <h1 className="text-3xl font-black text-ink">Synthetic showcase bookings</h1>
        <p className="text-ink/60">Public, synthetic records generated for this demonstration. They contain no real people or money. Open one to see the agreement, ledger, hash chain and verification.</p>
        {guide.isLoading && <Loading />}
        {guide.isError && <Alert kind="info">No demo dataset is available in this environment. {errorMessage(guide.error)}</Alert>}
        <div className="grid gap-3 md:grid-cols-2">
          {guide.data?.showcase.map((s) => (
            <Card key={s.key} className="space-y-2" data-testid="showcase-card">
              <h2 className="font-bold text-ink">{s.label}</h2>
              <p className="text-xs text-ink/60">{s.description}</p>
              <p className="text-sm">Service {rupees(s.service_price_paise)} → customer total <strong>{rupees(s.customer_total_paise)}</strong>, worker <strong>{rupees(s.worker_payout_paise)}</strong>, platform <strong>{rupees(s.platform_charges_paise)}</strong></p>
              <p className="text-xs text-ink/60">{s.pricing_model} · policy {s.fee_policy_id} · {s.status} · {ANCHOR_LABELS[s.anchor_status as AnchorStatus] ?? s.anchor_label}</p>
              <Link to={`/demo/transparency/${s.key}`} className="text-sm font-semibold text-plum underline">Open transaction transparency</Link>
            </Card>
          ))}
        </div>
        <p className="text-sm"><Link to="/demo/tamper" className="font-semibold text-plum underline">Try the tamper-detection demonstration</Link></p>
      </div>
    </div>
  );
}

export function DemoTransparency() {
  const { key = '' } = useParams();
  const rec = useQuery({ queryKey: ['showcase-receipt', key], queryFn: () => publicApi.showcaseReceipt(key), retry: false });
  const guide = useQuery({ queryKey: ['demo-guide'], queryFn: publicApi.demoGuide, retry: false });
  const item = guide.data?.showcase.find((s) => s.key === key);
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <Link to="/demo" className="inline-flex items-center gap-1 text-sm font-semibold text-plum"><ArrowLeft size={14} aria-hidden="true" />Demo showcase</Link>
        <h1 className="text-3xl font-black text-ink">{item?.label ?? 'Showcase booking'}</h1>
        <Alert kind="info"><strong>Demo marketplace — sample data.</strong> This booking is synthetic. Its acceptances were recorded by the seed script on behalf of demo personas. All ledger entries are simulated.</Alert>
        {rec.isLoading && <Loading />}
        {rec.isError && <Alert kind="error">{errorMessage(rec.error)}</Alert>}
        {rec.data && <Card><TransactionTransparency receipt={rec.data} service={item?.service} fileName={`${key}.json`} /></Card>}
      </div>
    </div>
  );
}
