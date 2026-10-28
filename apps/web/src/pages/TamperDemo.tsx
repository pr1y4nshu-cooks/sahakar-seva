import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Alert, Field, Select } from '@/components/marketplace/common';
import { errorMessage, rupees } from '@/lib/marketplace';
import { publicApi } from '@/lib/trust';
import { compareHistories, editCommittedPayloads, editDisplayedSummary, forgeSelfConsistent, shortHash, tokenMentionsDigest, verifyReceiptInBrowser, type BrowserVerification, type Edits } from '@/lib/receiptVerify';

type R = Record<string, any>;
type Mode = 'display' | 'payload' | 'rehash';
const MODES: [Mode, string, string][] = [
  ['display', 'A. Change only the numbers shown on the receipt', 'A lazy lie: edit the summary a user would read.'],
  ['payload', 'B. Change the committed agreement but keep the hashes', 'Edit the signed-over agreement data without recomputing anything.'],
  ['rehash', 'C. Change the amounts and recompute every hash (privileged operator)', 'Someone with database access rewrites history consistently, including checkpoint hashes.'],
];

/** Everything runs on an in-memory COPY. Nothing is sent to the server and no ledger is touched. */
export function TamperDemo() {
  const guide = useQuery({ queryKey: ['demo-guide'], queryFn: publicApi.demoGuide, retry: false });
  const [key, setKey] = useState('headline-percentage');
  const [original, setOriginal] = useState<R | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('display');
  const [worker, setWorker] = useState('');
  const [total, setTotal] = useState('');
  const [fee, setFee] = useState('');
  const [result, setResult] = useState<{ v: BrowserVerification; tampered: R; baseline: BrowserVerification } | null>(null);

  useEffect(() => {
    setOriginal(null); setResult(null); setLoadError(null);
    publicApi.showcaseReceipt(key).then((r) => { setOriginal(r); setWorker(String(r.summary.worker_share_paise / 100)); setTotal(String(r.summary.customer_total_paise / 100)); setFee(String(r.summary.platform_fee_paise / 100)); })
      .catch((e) => setLoadError(errorMessage(e)));
  }, [key]);

  const run = async () => {
    if (!original) return;
    const edits: Edits = { worker_share_paise: Math.round(Number(worker) * 100), customer_total_paise: Math.round(Number(total) * 100), platform_fee_paise: Math.round(Number(fee) * 100) };
    const tampered = mode === 'display' ? editDisplayedSummary(original, edits) : mode === 'payload' ? editCommittedPayloads(original, edits) : await forgeSelfConsistent(original, edits);
    setResult({ v: await verifyReceiptInBrowser(tampered), tampered, baseline: await verifyReceiptInBrowser(original) });
  };

  const s = original?.summary;
  const diff = result && original ? compareHistories(original, result.tampered) : null;
  const lastCp = original?.checkpoints?.[original.checkpoints.length - 1];
  const tokenOnTampered = result && lastCp ? tokenMentionsDigest(lastCp.external_timestamp?.time_stamp_response_der_b64, result.tampered.checkpoints?.[result.tampered.checkpoints.length - 1]?.digest ?? '') : false;
  const noChange = !!s && Math.round(Number(worker) * 100) === s.worker_share_paise && Math.round(Number(total) * 100) === s.customer_total_paise && Math.round(Number(fee) * 100) === s.platform_fee_paise;
  const preset = (w: number, t: number, f: number) => { setWorker(String(w / 100)); setTotal(String(t / 100)); setFee(String(f / 100)); setResult(null); };

  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <p className="text-sm font-bold uppercase tracking-[0.2em] text-plum">Demo marketplace — sample data</p>
        <h1 className="text-3xl font-black text-ink">Tamper-detection demonstration</h1>
        <Alert kind="info">You edit a <strong>copy</strong> of a synthetic receipt in your browser. The real verification code then runs on the edited copy. The server, database and ledger are never changed, and there is no endpoint that could change them.</Alert>
        {guide.isError && <Alert kind="info">No demo dataset is available in this environment.</Alert>}
        <Card className="space-y-4">
          <Field label="Receipt to copy" htmlFor="td-key">
            <Select id="td-key" value={key} onChange={(e) => setKey(e.target.value)}>
              {(guide.data?.showcase ?? [{ key: 'headline-percentage', label: 'Headline booking' } as any]).map((x: any) => <option key={x.key} value={x.key}>{x.label}</option>)}
            </Select>
          </Field>
          {loadError && <Alert kind="error">{loadError}</Alert>}
          {s && (
            <>
              <dl className="grid gap-2 rounded-2xl bg-ink/5 p-3 text-sm sm:grid-cols-3" data-testid="td-original">
                <div><dt className="text-xs text-ink/60">Original customer total (committed)</dt><dd className="font-bold">{rupees(s.customer_total_paise)}</dd></div>
                <div><dt className="text-xs text-ink/60">Original worker share (committed)</dt><dd className="font-bold">{rupees(s.worker_share_paise)}</dd></div>
                <div><dt className="text-xs text-ink/60">Original platform charges</dt><dd className="font-bold">{rupees(s.platform_fee_paise)}</dd></div>
              </dl>
              <fieldset className="space-y-2"><legend className="text-sm font-semibold text-ink">What does the attacker do?</legend>
                {MODES.map(([m, label, hint]) => (
                  <label key={m} className="flex cursor-pointer items-start gap-2 text-sm"><input type="radio" name="td-mode" checked={mode === m} onChange={() => { setMode(m); setResult(null); }} className="mt-1" /><span><strong>{label}</strong><br /><span className="text-xs text-ink/60">{hint}</span></span></label>
                ))}
              </fieldset>
              <div className="flex flex-wrap gap-2 text-xs">
                <button type="button" className="rounded-full border border-ink/20 bg-white px-3 py-1 font-semibold" onClick={() => preset(Math.round(s.worker_share_paise * 0.8), s.customer_total_paise, s.customer_total_paise - Math.round(s.worker_share_paise * 0.8))} data-testid="preset-hidden">Preset: hidden deduction (total unchanged, worker share −20%)</button>
                <button type="button" className="rounded-full border border-ink/20 bg-white px-3 py-1 font-semibold" onClick={() => preset(Math.round(s.worker_share_paise * 0.8), Math.round(s.customer_total_paise * 0.8), Math.round(s.platform_fee_paise * 0.8))} data-testid="preset-consistent">Preset: consistent forgery (every amount −20%)</button>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Altered worker share (₹)" htmlFor="td-worker"><Input id="td-worker" type="number" min={0} value={worker} onChange={(e) => { setWorker(e.target.value); setResult(null); }} /></Field>
                <Field label="Altered customer total (₹)" htmlFor="td-total"><Input id="td-total" type="number" min={0} value={total} onChange={(e) => { setTotal(e.target.value); setResult(null); }} /></Field>
                <Field label="Altered platform charges (₹)" htmlFor="td-fee"><Input id="td-fee" type="number" min={0} value={fee} onChange={(e) => { setFee(e.target.value); setResult(null); }} /></Field>
              </div>
              <Button onClick={run} disabled={noChange}>Run verification on the altered copy</Button>
              {noChange && <p className="text-xs text-ink/50">Change at least one amount first.</p>}
            </>
          )}
        </Card>

        {result && original && diff && (
          <Card className="space-y-3" data-testid="td-result">
            <div role={result.v.result === 'VERIFICATION FAILED' ? 'alert' : 'status'} className={`flex items-start gap-2 rounded-xl p-3 text-sm ${result.v.result === 'VERIFICATION FAILED' ? 'bg-rose-50 text-rose-800' : 'bg-amber-50 text-amber-900'}`}>
              {result.v.result === 'VERIFICATION FAILED' ? <ShieldAlert size={18} /> : <ShieldCheck size={18} />}
              <div>
                <p className="font-bold" data-testid="td-outcome">{result.v.result === 'VERIFICATION FAILED' ? `Verification FAILED — ${result.v.failures.length} check(s) did not match.` : 'Local integrity verified — the forged copy is internally consistent.'}</p>
                <p className="text-xs">Unaltered original, same code: {result.baseline.result === 'VERIFICATION FAILED' ? 'FAILED' : 'passes'} ({result.baseline.checksRun} checks).</p>
              </div>
            </div>
            {result.v.failures.length > 0 && <ul className="list-disc pl-5 text-xs text-rose-800" data-testid="td-failures">{result.v.failures.slice(0, 8).map((f, i) => <li key={i}>{f.check}{f.detail ? ` — ${f.detail}` : ''}</li>)}</ul>}
            {mode === 'rehash' && result.v.result !== 'VERIFICATION FAILED' && (
              <div className="space-y-2 text-sm" data-testid="td-limits">
                <Alert kind="info"><strong>Why local hashes alone are not enough.</strong> An attacker who controls the database can recompute every hash, so a purely local check passes. What still gives them away:</Alert>
                <ul className="list-disc space-y-1 pl-5 text-xs">
                  <li>Compared with the receipt a participant kept earlier, {diff.diffs.filter((d) => d.status !== 'same').length} of {diff.diffs.length} events differ (first: <code>{shortHash(original.events[0].event_hash)}</code> vs <code>{shortHash(result.tampered.events[0].event_hash)}</code>).</li>
                  {lastCp?.external_timestamp ? (
                    <li data-testid="td-token">The original checkpoint carries an external timestamp token over hash <code>{shortHash(lastCp.digest)}</code>. The forged checkpoint hash is <code>{shortHash(result.tampered.checkpoints[0].digest)}</code>; the token {tokenOnTampered ? 'contains it' : 'does not contain it'}, so the timestamp cannot be reused for the forged history.</li>
                  ) : (
                    <li data-testid="td-token">This receipt has <strong>no external timestamp</strong> yet, so there is nothing outside SAHAKAR–SEVA&apos;s control to compare against except copies participants kept. Limitation: until a checkpoint is externally timestamped, a rewrite is only detectable by a retained copy.</li>
                  )}
                  <li>An operator could ask the timestamp service to stamp the <em>new</em> hash too. That would carry a <em>later</em> time than the original, which is why keeping your own copy matters.</li>
                </ul>
              </div>
            )}
            <div className="rounded-xl bg-ink/5 p-2 text-[11px]">
              <p className="font-semibold">Run the same check on the command line</p>
              <p>Save the original from the booking page, then: <code>python3 scripts/tamper_receipt.py original.json --mode {mode} --customer-total {Math.round(Number(total) * 100)} --worker-share {Math.round(Number(worker) * 100)} --platform-fee {Math.round(Number(fee) * 100)} --out altered.json</code> and <code>python3 scripts/verify_receipt.py altered.json --compare original.json</code></p>
            </div>
          </Card>
        )}
        <p className="text-sm"><Link to="/demo" className="font-semibold text-plum underline">Back to the showcase</Link></p>
      </div>
    </div>
  );
}
