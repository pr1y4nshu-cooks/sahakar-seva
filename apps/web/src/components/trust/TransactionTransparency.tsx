import { useEffect, useMemo, useState } from 'react';
import { Check, Copy, Download, FileCheck2, Fingerprint, Landmark, Link2, Scale, ScrollText, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { rupees } from '@/lib/marketplace';
import { shortHash, tokenMentionsDigest, verifyReceiptInBrowser, type BrowserVerification } from '@/lib/receiptVerify';
import { ANCHOR_LABELS, type AnchorStatus } from '@/lib/trust';

type R = Record<string, any>;
const ACCOUNT_LABELS: Record<string, string> = {
  simulated_customer_payment_clearing: 'Customer payment clearing',
  simulated_business_payment_clearing: 'Organization payment clearing',
  simulated_platform_promotion_expense: 'Platform-absorbed charge',
  simulated_worker_entitlement: 'Worker allocation',
  simulated_platform_fee_allocation: 'Platform service charge',
  simulated_processing_charge_allocation: 'Modeled processing charge',
};
const EVENT_LABELS: Record<string, string> = {
  quote_created: 'Price agreement proposed', quote_revised: 'Price revised', quote_accepted: 'Price accepted', booking_confirmed: 'Booking confirmed',
  booking_declined: 'Booking declined', booking_cancelled: 'Booking cancelled', booking_completed: 'Work completed',
  simulated_settlement_recorded: 'Simulated settlement recorded', dispute_opened: 'Dispute opened', dispute_decision_recorded: 'Dispute decision recorded',
  ledger_reversal_posted: 'Reversing ledger entry posted',
};
const BEARER: Record<string, string> = { customer: 'customer', worker: 'worker', business: 'organization', platform: 'platform' };
const when = (iso?: string) => (iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', second: '2-digit' }) : '—');

export function Hash({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[11px]" title={value}>
      <span data-testid="hash-short">{shortHash(value)}</span>
      <button type="button" aria-label={`Copy full ${label ?? 'hash'}`} className="rounded p-0.5 text-ink/50 hover:bg-ink/10"
        onClick={async () => { try { await navigator.clipboard.writeText(value); } catch { /* clipboard unavailable */ } setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
        {copied ? <Check size={11} className="text-emerald-600" /> : <Copy size={11} />}
      </button>
    </span>
  );
}

function saveJson(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function questions(rec: R) {
  const events: R[] = rec.events ?? [];
  const quoteEv = [...events].reverse().find((e) => e.event_type === 'quote_created' || e.event_type === 'quote_revised');
  const quote: R | undefined = quoteEv?.payload?.data?.quote;
  const settlement = events.find((e) => e.event_type === 'simulated_settlement_recorded');
  const reversal = events.find((e) => e.event_type === 'ledger_reversal_posted');
  const acceptances = events.filter((e) => e.event_type === 'quote_accepted' && e.payload.data.quote_version === quote?.version);
  return { events, quote, quoteEv, settlement, reversal, acceptances };
}

function AgreementView({ rec, service }: { rec: R; service?: string | null }) {
  const { quote, acceptances, quoteEv } = questions(rec);
  const s = rec.summary;
  if (!quote) return <p className="text-sm text-ink/60">This is a legacy record: no versioned agreement was collected for it, so none is shown.</p>;
  const lines: R[] = quote.line_items ?? [];
  return (
    <div className="space-y-3 text-sm" data-testid="view-agreement">
      <dl className="grid gap-2 sm:grid-cols-2">
        <div><dt className="text-xs text-ink/60">Booking reference</dt><dd><Hash value={s.booking_id} label="booking id" /></dd></div>
        <div><dt className="text-xs text-ink/60">Service</dt><dd>{service ?? 'Service skill id ' + shortHash(String(rec.booking?.skill_id ?? ''), 6, 4)}</dd></div>
        <div><dt className="text-xs text-ink/60">Quote version</dt><dd className="font-semibold" data-testid="exp-quote-version">v{quote.version}</dd></div>
        <div><dt className="text-xs text-ink/60">Fee policy</dt><dd>{quote.fee_policy_id} v{quote.fee_policy_version} ({quote.pricing_model})</dd></div>
      </dl>
      <div className="rounded-2xl bg-ink/5 p-3">
        <div className="flex justify-between"><span>Service price</span><strong data-testid="exp-service">{rupees(quote.service_price_paise ?? quote.customer_total_paise)}</strong></div>
        {lines.map((l) => (
          <div key={l.code} className="flex justify-between pl-3 text-xs text-ink/70">
            <span>{l.label} — borne by <strong>{BEARER[l.bearer]}</strong>{l.waived_by ? ` · waived by promotion "${l.waived_by}" (would be ${rupees(l.computed_paise)})` : ''}</span>
            <span>{l.bearer === 'worker' ? '−' : l.bearer === 'platform' ? '' : '+'}{rupees(l.amount_paise)}</span>
          </div>
        ))}
        <div className="mt-1 flex justify-between border-t border-ink/10 pt-1"><span>Customer agreed total</span><strong data-testid="exp-total">{rupees(quote.customer_total_paise)}</strong></div>
        <div className="flex justify-between"><span>Worker agreed amount</span><strong data-testid="exp-worker">{rupees(quote.worker_share_paise)}</strong></div>
        <div className="flex justify-between"><span>Platform charges</span><strong data-testid="exp-platform">{rupees(quote.platform_fee_paise)}</strong></div>
        <div className="flex justify-between text-ink/60"><span>Modeled processing charges</span><span>{quote.additional_charges_paise ? rupees(quote.additional_charges_paise) : 'None'}</span></div>
        <div className="flex justify-between text-ink/60"><span>Taxes</span><span>Not modeled</span></div>
      </div>
      <div>
        <p className="text-xs font-semibold text-ink/70">Evidence of acceptance of quote v{quote.version}</p>
        <ul className="mt-1 space-y-0.5 text-xs">
          {acceptances.length === 0 && <li className="text-ink/60">No acceptance event is recorded for this version.</li>}
          {acceptances.map((a) => <li key={a.sequence} data-testid="acceptance">✓ {a.payload.data.accepted_by_role} accepted · {when(a.payload.occurred_at)} · event #{a.sequence} <Hash value={a.event_hash} label="acceptance event hash" /></li>)}
        </ul>
        <p className="mt-1 text-[11px] text-ink/50">Agreement created {when(quoteEv?.payload?.occurred_at)}. {quote.is_example_policy ? 'Pricing policy is an illustrative example, not final pricing. ' : ''}Amounts here are read from the committed agreement, the same source both parties see.</p>
      </div>
    </div>
  );
}

function LedgerView({ rec }: { rec: R }) {
  const { settlement, reversal } = questions(rec);
  const txs = [settlement, reversal].filter(Boolean).map((e) => ({ ev: e as R, tx: (e as R).payload.data.ledger_transaction as R }));
  if (!txs.length) return <p className="text-sm text-ink/60" data-testid="view-ledger">No ledger transaction yet. A balanced simulated posting is written when the booking is completed.</p>;
  return (
    <div className="space-y-4" data-testid="view-ledger">
      <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-bold uppercase tracking-wide text-amber-800">SIMULATED — no real money moved. Demonstration accounting, not bank receivables or revenue.</p>
      {txs.map(({ ev, tx }) => {
        const debit = tx.entries.filter((e: R) => e.direction === 'debit').reduce((n: number, e: R) => n + e.amount_paise, 0);
        const credit = tx.entries.filter((e: R) => e.direction === 'credit').reduce((n: number, e: R) => n + e.amount_paise, 0);
        const balanced = debit === credit && debit === tx.amount_paise;
        return (
          <div key={tx.id} className="rounded-2xl border border-ink/10 p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span><strong>{tx.transaction_type === 'simulated_settlement_reversal' ? 'Reversal' : 'Settlement allocation'}</strong> · transaction <Hash value={tx.id} label="ledger transaction id" /></span>
              <span>Posted {when(ev.payload.occurred_at)} · INR</span>
            </div>
            <table className="mt-2 w-full text-sm">
              <thead><tr className="text-left text-xs text-ink/50"><th>Account</th><th className="text-right">Debit</th><th className="text-right">Credit</th></tr></thead>
              <tbody>
                {tx.entries.map((e: R, i: number) => (
                  <tr key={i} className="border-t border-ink/5" data-testid="ledger-row">
                    <td>{ACCOUNT_LABELS[e.account] ?? e.account}</td>
                    <td className="text-right tabular-nums">{e.direction === 'debit' ? rupees(e.amount_paise) : ''}</td>
                    <td className="text-right tabular-nums">{e.direction === 'credit' ? rupees(e.amount_paise) : ''}</td>
                  </tr>
                ))}
                <tr className="border-t border-ink/20 font-semibold"><td>Total</td><td className="text-right tabular-nums" data-testid="total-debits">{rupees(debit)}</td><td className="text-right tabular-nums" data-testid="total-credits">{rupees(credit)}</td></tr>
              </tbody>
            </table>
            <p className={`mt-2 text-xs font-semibold ${balanced ? 'text-emerald-700' : 'text-rose-700'}`} data-testid="reconciliation">
              {balanced ? `Balanced: total debits ${rupees(debit)} = total credits ${rupees(credit)}.` : `NOT balanced: debits ${rupees(debit)} ≠ credits ${rupees(credit)}.`}
            </p>
          </div>
        );
      })}
      {reversal && <p className="text-xs text-ink/60">The reversal is a new transaction that mirrors the original. The original entries remain in the record; nothing was edited.</p>}
    </div>
  );
}

function ProofView({ rec, verification }: { rec: R; verification: BrowserVerification | null }) {
  const events: R[] = rec.events ?? [];
  const cps: R[] = rec.checkpoints ?? [];
  const cpOf = (e: R) => cps.find((c) => c.checkpoint_index === e.inclusion_proof?.checkpoint_index);
  if (!events.length) return <p className="text-sm text-ink/60" data-testid="view-proof">No hash-chain evidence exists for this record (legacy booking).</p>;
  return (
    <div className="space-y-3" data-testid="view-proof">
      <p className="text-xs text-ink/70">
        Each step is hashed together with the previous step&apos;s hash, so changing any earlier record changes every later hash. Hash function: SHA-256 over canonical JSON (RFC 8785), with domain separation. Hover or copy to see full values.
      </p>
      <ol className="space-y-2">
        {events.map((e, i) => {
          const cp = cpOf(e);
          return (
            <li key={e.sequence} className="relative rounded-xl border border-ink/10 p-2 pl-8 text-xs" data-testid="proof-event">
              <span className="absolute left-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-plum/10 text-[10px] font-bold text-plum">{i + 1}</span>
              <div className="flex flex-wrap items-center justify-between gap-1"><strong>#{e.sequence} {EVENT_LABELS[e.event_type] ?? e.event_type}</strong><span className="text-ink/50">{when(e.payload.occurred_at)}</span></div>
              <div className="mt-1 grid gap-0.5 sm:grid-cols-2">
                <span>previous hash: <Hash value={e.previous_event_hash} label="previous hash" /></span>
                <span>this hash: <Hash value={e.event_hash} label="event hash" /></span>
                <span>payload hash: <Hash value={e.payload_hash} label="payload hash" /></span>
                <span>{cp ? <>in checkpoint {cp.checkpoint_index} (Merkle path of {e.inclusion_proof.path.length})</> : 'not yet in a checkpoint'}</span>
              </div>
              {i < events.length - 1 && <Link2 size={12} className="absolute -bottom-2.5 left-3 rotate-90 text-plum/60" aria-hidden="true" />}
            </li>
          );
        })}
      </ol>
      {cps.map((c) => (
        <div key={c.checkpoint_index} className="rounded-xl bg-ink/5 p-2 text-xs" data-testid="proof-checkpoint">
          <p className="font-semibold">Checkpoint {c.checkpoint_index}: events {c.body.first_sequence}–{c.body.last_sequence}</p>
          <p>Merkle root <Hash value={c.body.merkle_root} label="Merkle root" /> · checkpoint hash <Hash value={c.digest} label="checkpoint hash" /></p>
          <p data-testid="anchor-line">
            External timestamp: <strong>{ANCHOR_LABELS[c.anchor_status as AnchorStatus] ?? c.anchor_status}</strong>
            {c.external_timestamp?.gen_time && ` · stamped ${when(c.external_timestamp.gen_time)} by ${c.external_timestamp.tsa_name ?? 'TSA'}`}
            {c.external_timestamp && ` · token ${tokenMentionsDigest(c.external_timestamp.time_stamp_response_der_b64, c.digest) ? 'contains this checkpoint hash' : 'does NOT contain this checkpoint hash'}`}
          </p>
        </div>
      ))}
      <p className="text-xs" data-testid="local-result">
        {verification ? (verification.result === 'VERIFICATION FAILED' ? <span className="font-semibold text-rose-700">Local verification: FAILED ({verification.failures.length} problem(s))</span>
          : <span className="font-semibold text-emerald-700">Local verification: hashes, chain links, Merkle proofs and amounts recompute correctly ({verification.checksRun} checks, run in your browser).</span>) : 'Running local verification…'}
      </p>
    </div>
  );
}

export function statusStatement(rec: R, v: BrowserVerification | null): { tone: 'ok' | 'warn' | 'bad'; text: string } {
  if (!v) return { tone: 'warn', text: 'Checking…' };
  if (v.result === 'VERIFICATION FAILED') return { tone: 'bad', text: 'Verification failed: this receipt does not match its own commitments.' };
  const anchored = (rec.checkpoints ?? []).some((c: R) => c.external_timestamp?.time_stamp_response_der_b64);
  return anchored
    ? { tone: 'warn', text: 'Local integrity verified. An external timestamp token is attached; check its signature with the offline verifier (the browser cannot).' }
    : { tone: 'warn', text: 'Local integrity verified. External anchoring not yet completed.' };
}

function VerificationView({ rec, verification, fileName, onDownload }: { rec: R; verification: BrowserVerification | null; fileName: string; onDownload?: () => void }) {
  const st = statusStatement(rec, verification);
  const tone = { ok: 'bg-emerald-50 text-emerald-800', warn: 'bg-amber-50 text-amber-900', bad: 'bg-rose-50 text-rose-800' }[st.tone];
  const hasToken = (rec.checkpoints ?? []).some((c: R) => c.external_timestamp?.time_stamp_response_der_b64);
  return (
    <div className="space-y-3 text-sm" data-testid="view-verification">
      <div role={st.tone === 'bad' ? 'alert' : 'status'} className={`flex items-start gap-2 rounded-xl p-3 ${tone}`}>
        {st.tone === 'bad' ? <ShieldAlert size={18} aria-hidden="true" /> : <ShieldCheck size={18} aria-hidden="true" />}
        <div><p className="font-bold" data-testid="verify-statement">{st.text}</p>
          {verification && verification.failures.length > 0 && <ul className="mt-1 list-disc pl-4 text-xs">{verification.failures.slice(0, 6).map((f, i) => <li key={i}>{f.check}{f.detail ? ` — ${f.detail}` : ''}</li>)}</ul>}
        </div>
      </div>
      <ul className="space-y-1 text-xs text-ink/70">
        <li><strong>What this proves:</strong> the agreed amounts, the ledger posting and the order of events are consistent with each other and with committed hashes.</li>
        <li><strong>What it does not prove:</strong> that real money moved (payments are simulated); that nobody rewrote the whole history, unless an external timestamp or a copy you kept earlier agrees with it.</li>
        <li><strong>External timestamp:</strong> {hasToken ? 'a token is attached. Verify its signature against a root certificate you downloaded yourself (command below).' : 'none attached yet, so local integrity is the strongest claim available.'}</li>
      </ul>
      <div className="flex flex-wrap gap-2">
        {onDownload && <button type="button" onClick={onDownload} className="flex items-center gap-1.5 rounded-full border border-ink/20 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-ink/5"><Download size={13} aria-hidden="true" />Download receipt</button>}
        <Link to="/verify" className="flex items-center gap-1.5 rounded-full border border-ink/20 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-ink/5"><FileCheck2 size={13} aria-hidden="true" />Verify a receipt file</Link>
        <Link to="/demo/tamper" className="flex items-center gap-1.5 rounded-full border border-plum/40 bg-plum/5 px-3 py-1.5 text-xs font-semibold text-plum hover:bg-plum/10"><ScrollText size={13} aria-hidden="true" />See tamper detection</Link>
      </div>
      <div className="rounded-xl bg-ink/5 p-2 text-[11px]">
        <p className="font-semibold text-ink">Independent verification (no SAHAKAR server or database)</p>
        <pre className="mt-1 overflow-x-auto font-mono">{`curl -sO https://cacerts.digicert.com/DigiCertTrustedRootG4.crt
openssl x509 -inform DER -in DigiCertTrustedRootG4.crt -out root.pem
python3 scripts/verify_receipt.py ${fileName} --tsa-ca root.pem`}</pre>
        <p className="mt-1 text-ink/60">Needs Python 3 with <code>asn1crypto</code> and OpenSSL 3 (not macOS&apos;s built-in LibreSSL). Compare the root&apos;s SHA-256 fingerprint with DigiCert&apos;s published value.</p>
      </div>
    </div>
  );
}

const TABS = [
  { id: 'agreement', label: 'Agreement', Icon: Scale },
  { id: 'ledger', label: 'Ledger', Icon: Landmark },
  { id: 'proof', label: 'Cryptographic proof', Icon: Fingerprint },
  { id: 'verify', label: 'Verification', Icon: ShieldCheck },
] as const;

export function TransactionTransparency({ receipt, service, fileName, onDownload, initialTab = 'agreement' }: {
  receipt: R; service?: string | null; fileName?: string; onDownload?: () => void; initialTab?: (typeof TABS)[number]['id'];
}) {
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>(initialTab);
  const [verification, setVerification] = useState<BrowserVerification | null>(null);
  useEffect(() => { let live = true; setVerification(null); verifyReceiptInBrowser(receipt).then((v) => live && setVerification(v)); return () => { live = false; }; }, [receipt]);
  const name = fileName ?? `sahakar-receipt-${String(receipt.summary?.booking_id ?? '').slice(0, 8)}.json`;
  const body = useMemo(() => ({
    agreement: <AgreementView rec={receipt} service={service} />, ledger: <LedgerView rec={receipt} />,
    proof: <ProofView rec={receipt} verification={verification} />,
    verify: <VerificationView rec={receipt} verification={verification} fileName={name} onDownload={onDownload ?? (() => saveJson(name, receipt))} />,
  }), [receipt, service, verification, name, onDownload]);
  return (
    <section aria-label="Transaction Transparency" className="rounded-2xl border border-plum/20 bg-white p-3" data-testid="transaction-transparency">
      <h3 className="text-sm font-bold text-ink">Transaction Transparency</h3>
      <div role="tablist" aria-label="Evidence views" className="mt-2 flex flex-wrap gap-1">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${tab === id ? 'bg-plum text-white' : 'bg-ink/5 text-ink/70 hover:bg-ink/10'}`}>
            <Icon size={12} aria-hidden="true" />{label}
          </button>
        ))}
      </div>
      <div className="mt-3" role="tabpanel">{body[tab === 'verify' ? 'verify' : tab]}</div>
    </section>
  );
}
