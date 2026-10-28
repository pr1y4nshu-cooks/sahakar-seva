import { ReceiptVerifier } from '@/components/trust/ReceiptVerifier';

export function Verify() {
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-3xl space-y-4">
        <p className="text-sm font-bold uppercase tracking-[0.2em] text-plum">Receipt verification</p>
        <h1 className="text-3xl font-black text-ink">Check a booking receipt</h1>
        <p className="text-ink/60">
          Customers and workers can each download the same receipt from My Bookings. Checking it here recomputes every hash,
          chain link and amount in your browser.
        </p>
        <ReceiptVerifier />
      </div>
    </div>
  );
}
