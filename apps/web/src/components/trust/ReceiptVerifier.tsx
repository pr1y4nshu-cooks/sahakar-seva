import { useState } from 'react';
import { FileCheck2, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Alert } from '@/components/marketplace/common';
import { rupees } from '@/lib/marketplace';
import { verifyReceiptInBrowser, type BrowserVerification } from '@/lib/receiptVerify';

const readText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });

/** Verify a downloaded receipt file locally in the browser. Nothing is uploaded. */
export function ReceiptVerifier() {
  const [result, setResult] = useState<BrowserVerification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onFile = async (file: File | undefined) => {
    setResult(null);
    setError(null);
    if (!file) return;
    setBusy(true);
    try {
      const parsed = JSON.parse(await readText(file));
      setResult(await verifyReceiptInBrowser(parsed));
    } catch {
      setError('This file is not valid JSON. Choose a receipt downloaded from My Bookings.');
    } finally {
      setBusy(false);
    }
  };

  const ok = result && result.result !== 'VERIFICATION FAILED';
  const s = (result?.summary ?? {}) as Record<string, number | string>;
  return (
    <Card className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-xl font-bold text-ink"><FileCheck2 size={20} className="text-plum" aria-hidden="true" />Check a receipt</h2>
        <p className="mt-1 text-sm text-ink/60">The file is read and hashed inside your browser. It is not sent to SAHAKAR–SEVA.</p>
      </div>
      <label htmlFor="receipt-file" className="block text-sm font-medium text-ink">Receipt file (.json)</label>
      <input id="receipt-file" type="file" accept="application/json,.json" onChange={(e) => onFile(e.target.files?.[0])}
        className="block w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-plum file:px-4 file:py-2 file:text-white" />
      {busy && <p className="text-sm text-ink/60">Checking…</p>}
      {error && <Alert kind="error">{error}</Alert>}
      {result && (
        <div className="space-y-3" aria-live="polite">
          <div role={ok ? 'status' : 'alert'} className={`flex items-start gap-2 rounded-xl p-3 text-sm ${ok ? 'bg-emerald-50 text-emerald-800' : 'bg-rose-50 text-rose-800'}`}>
            {ok ? <ShieldCheck size={18} aria-hidden="true" /> : <ShieldAlert size={18} aria-hidden="true" />}
            <div>
              <p className="font-bold" data-testid="verify-result">{result.result === 'LOCAL INTEGRITY VERIFIED' ? 'Receipt integrity verified (local)' : result.result === 'VERIFICATION FAILED' ? 'Verification failed' : 'External evidence unavailable'}</p>
              <p className="text-xs">{result.external}</p>
            </div>
          </div>
          {s.booking_id && (
            <p className="text-xs text-ink/70">
              Booking {String(s.booking_id).slice(0, 8)}… · quote v{s.quote_version} · customer total {rupees(Number(s.customer_total_paise))} = worker share {rupees(Number(s.worker_share_paise))} + platform fee {rupees(Number(s.platform_fee_paise))}
            </p>
          )}
          {result.failures.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-xs text-rose-800">
              {result.failures.slice(0, 12).map((f, i) => <li key={i}>{f.check}{f.detail ? ` — ${f.detail}` : ''}</li>)}
            </ul>
          )}
          <p className="text-xs text-ink/50">{result.checksRun} checks. A pass means the agreed amounts and their history are internally consistent. It does not prove that real money moved; payments in this pilot are simulated.</p>
        </div>
      )}
      <div className="rounded-xl bg-ink/5 p-3 text-xs text-ink/70">
        <p className="font-semibold text-ink">Independent check of the external timestamp</p>
        <p className="mt-1">The browser does not check RFC 3161 timestamp signatures. Use the offline verifier with a TSA root certificate you downloaded yourself:</p>
        <pre className="mt-1 overflow-x-auto rounded bg-white p-2 font-mono text-[11px]">python3 scripts/verify_receipt.py receipt.json --tsa-ca DigiCertTrustedRootG4.pem</pre>
      </div>
    </Card>
  );
}
