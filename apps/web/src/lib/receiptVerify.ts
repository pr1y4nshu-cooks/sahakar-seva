/**
 * In-browser receipt verifier (local integrity only).
 *
 * Runs entirely in the browser with WebCrypto SHA-256; it never calls the SAHAKAR API. It re-implements
 * the formats in docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md. It deliberately does NOT
 * check RFC 3161 timestamp signatures: that needs a trust anchor and certificate-chain validation, which
 * the offline CLI (scripts/verify_receipt.py --tsa-ca ...) performs. So this verifier can report
 * "LOCAL INTEGRITY VERIFIED" or "VERIFICATION FAILED", never "externally verified".
 */

export type BrowserVerification = {
  result: 'LOCAL INTEGRITY VERIFIED' | 'VERIFICATION FAILED' | 'EXTERNAL EVIDENCE UNAVAILABLE';
  external: string;
  failures: { check: string; detail: string }[];
  checksRun: number;
  summary: Record<string, unknown> | null;
};

const enc = new TextEncoder();
const PAYLOAD_DOMAIN = 'SAHAKAR-SEVA:financial-event-payload:v1\u0000';
const EVENT_DOMAIN = 'SAHAKAR-SEVA:financial-event:v1\u0000';
const CHECKPOINT_DOMAIN = 'SAHAKAR-SEVA:checkpoint:v1\u0000';

/** RFC 8785 for this format's profile: JCS string/number rules are ECMAScript JSON.stringify; keys sort by UTF-16 units. */
export function canonicalize(value: unknown): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error('only safe integers are allowed in committed payloads');
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    return `{${Object.keys(obj).sort().map((k) => `${JSON.stringify(k)}:${canonicalize(obj[k])}`).join(',')}}`;
  }
  throw new Error('unsupported value');
}

const hex = (buf: ArrayBuffer) => Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
const fromHex = (h: string) => {
  if (!/^[0-9a-f]{64}$/.test(h)) throw new Error('expected a 32-byte hex digest');
  return Uint8Array.from(h.match(/../g)!.map((b) => parseInt(b, 16)));
};
const concat = (...parts: Uint8Array[]) => {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
};
const sha = async (data: Uint8Array) => new Uint8Array(await crypto.subtle.digest('SHA-256', data as Uint8Array<ArrayBuffer>));
const shaHex = async (data: Uint8Array) => hex(await crypto.subtle.digest('SHA-256', data as Uint8Array<ArrayBuffer>));

export const payloadHash = (payload: unknown) => shaHex(enc.encode(PAYLOAD_DOMAIN + canonicalize(payload)));
export async function eventHash(sequence: number, prev: string, payloadHashHex: string) {
  const seq = new Uint8Array(8);
  new DataView(seq.buffer).setBigUint64(0, BigInt(sequence));
  return shaHex(concat(enc.encode(EVENT_DOMAIN), seq, fromHex(prev), fromHex(payloadHashHex)));
}
export const checkpointDigest = (body: unknown) => shaHex(enc.encode(CHECKPOINT_DOMAIN + canonicalize(body)));
export const policyHash = (definition: unknown) => shaHex(enc.encode('SAHAKAR-SEVA:fee-policy:v1\u0000' + canonicalize(definition)));

const pct = (amount: number, bps: number) => Math.floor((amount * bps + 5000) / 10000);
const applies = (rule: string, org: boolean) => rule === 'any' || (rule === 'only') === org;

/** Independent re-implementation of the server pricing engine (fee policy format v1). */
export function evaluatePolicy(d: Record<string, any>, service: number, origin: string, forOrg: boolean, at: string) {
  const lines: Record<string, any>[] = [];
  for (const c of d.components) {
    if (!c.applies_to_origins.includes(origin) || !applies(c.organization_bookings, forOrg)) continue;
    let computed = pct(service, c.percent_bps) + c.fixed_paise;
    if (c.min_paise !== null) computed = Math.max(computed, c.min_paise);
    if (c.max_paise !== null) computed = Math.min(computed, c.max_paise);
    const promo = d.promotions.find((p: Record<string, any>) => p.waives.includes(c.code) && applies(p.organization_bookings, forOrg)
      && !(p.starts_at && at < p.starts_at) && !(p.ends_at && at >= p.ends_at)
      && !(p.max_service_price_paise !== null && service > p.max_service_price_paise));
    lines.push({ code: c.code, kind: c.kind, label: c.label, bearer: c.bearer, percent_bps: c.percent_bps, fixed_paise: c.fixed_paise,
      min_paise: c.min_paise, max_paise: c.max_paise, computed_paise: computed, amount_paise: promo ? 0 : computed, waived_by: promo ? promo.code : null });
  }
  const by = (bearers: string[]) => lines.filter((l) => bearers.includes(l.bearer)).reduce((n, l) => n + l.amount_paise, 0);
  const party = by(['customer', 'business', 'worker']);
  const partyLines = lines.filter((l) => l.bearer !== 'platform');
  return {
    lines,
    customer_total_paise: service + by(['customer', 'business']),
    worker_share_paise: service - by(['worker']),
    platform_fee_paise: partyLines.filter((l) => l.kind === 'platform_fee').reduce((n, l) => n + l.amount_paise, 0),
    additional_charges_paise: partyLines.filter((l) => l.kind === 'processing_charge').reduce((n, l) => n + l.amount_paise, 0),
    fee_bps: Math.ceil((party * 10000) / service),
    within_ceiling: party * 10000 <= service * d.max_total_charge_bps,
  };
}

async function verifyInclusion(leafHex: string, index: number, size: number, path: string[], rootHex: string) {
  if (index < 0 || index >= size) return false;
  let fn = index, sn = size - 1;
  let r = await sha(concat(new Uint8Array([0]), fromHex(leafHex)));
  for (const pHex of path) {
    const p = fromHex(pHex);
    if (sn === 0) return false;
    if (fn & 1 || fn === sn) {
      r = await sha(concat(new Uint8Array([1]), p, r));
      if (!(fn & 1)) while (fn && !(fn & 1)) { fn >>= 1; sn >>= 1; }
    } else {
      r = await sha(concat(new Uint8Array([1]), r, p));
    }
    fn >>= 1; sn >>= 1;
  }
  return sn === 0 && hex(r.buffer as ArrayBuffer) === rootHex;
}

type AnyObj = Record<string, any>;

export async function verifyReceiptInBrowser(rec: AnyObj): Promise<BrowserVerification> {
  const failures: { check: string; detail: string }[] = [];
  let checks = 0;
  const check = (name: string, ok: boolean, detail = '') => { checks += 1; if (!ok) failures.push({ check: name, detail }); return ok; };
  const done = (result: BrowserVerification['result'], external: string): BrowserVerification =>
    ({ result: failures.length ? 'VERIFICATION FAILED' : result, external, failures, checksRun: checks, summary: rec?.summary ?? null });

  try {
    if (!check('receipt format', rec?.receipt_format === 'sahakar-seva/receipt/v1', 'not a SAHAKAR–SEVA v1 receipt')) {
      return done('VERIFICATION FAILED', 'not checked');
    }
    const events: AnyObj[] = rec.events ?? [];
    if (events.length === 0) return done('EXTERNAL EVIDENCE UNAVAILABLE', 'Legacy record: no hash-chain evidence was collected.');
    const s = rec.summary ?? {};
    check('booking reference', s.booking_id === rec.booking?.booking_id);
    let prevSeq = 0;
    let prevBooking: string | null = null;
    for (let i = 0; i < events.length; i++) {
      const ev = events[i];
      const p = ev.payload ?? {};
      const label = `event ${ev.sequence} (${ev.event_type})`;
      const ph = await payloadHash(p);
      check(`${label}: payload hash`, ph === ev.payload_hash, 'payload does not match its hash');
      check(`${label}: event hash`, (await eventHash(ev.sequence, ev.previous_event_hash, ph)) === ev.event_hash, 'chained hash does not recompute');
      check(`${label}: belongs to booking`, p.booking_id === s.booking_id);
      check(`${label}: order`, ev.sequence > prevSeq && p.booking_event_index === i, 'an event is missing or out of order');
      check(`${label}: booking link`, p.booking_previous_event_hash === prevBooking, 'does not link to the previous event');
      prevSeq = ev.sequence;
      prevBooking = ev.event_hash;
    }
    const quotes = events.filter((e) => e.event_type === 'quote_created' || e.event_type === 'quote_revised');
    if (check('agreement present', quotes.length > 0)) {
      const qe = quotes[quotes.length - 1];
      const q = qe.payload.data.quote;
      const pairs: [string, number][] = [
        ['quote_version', q.version], ['customer_total_paise', q.customer_total_paise], ['worker_share_paise', q.worker_share_paise],
        ['platform_fee_paise', q.platform_fee_paise], ['additional_charges_paise', q.additional_charges_paise], ['tax_paise', q.tax_paise],
      ];
      for (const [k, v] of pairs) check(`shown ${k.replace(/_/g, ' ')} matches the committed agreement`, s[k] === v, `shown ${s[k]}, committed ${v}`);
      check('allocation reconciles', q.worker_share_paise + q.platform_fee_paise + q.additional_charges_paise + q.tax_paise === q.customer_total_paise);
      if (q.line_items) {
        for (const k of ['service_price_paise', 'fee_policy_id', 'fee_policy_version', 'pricing_model', 'policy_definition_hash']) {
          check(`shown ${k.replace(/_/g, ' ')} matches the committed agreement`, s[k] === q[k], `shown ${s[k]}, committed ${q[k]}`);
        }
        check('fee policy definition matches its committed hash', (await policyHash(q.policy_definition)) === q.policy_definition_hash);
        check('ceiling within the 20% safety limit', q.policy_definition.max_total_charge_bps <= 2000);
        const ev = evaluatePolicy(q.policy_definition, q.service_price_paise, qe.payload.data.service.origin, !!q.for_organization, q.evaluated_at);
        check('charges recomputed from the policy match the line items', canonicalize(ev.lines) === canonicalize(q.line_items));
        for (const k of ['customer_total_paise', 'worker_share_paise', 'platform_fee_paise', 'additional_charges_paise', 'fee_bps'] as const) {
          check(`recomputed ${k.replace(/_/g, ' ')} matches the quote`, ev[k] === q[k], `policy gives ${ev[k]}, quote has ${q[k]}`);
        }
        check('charges within the policy ceiling', ev.within_ceiling);
      } else {
        check('fee follows the recorded rule', q.platform_fee_paise === Math.floor((q.customer_total_paise * q.fee_bps + 5000) / 10000) && q.fee_bps <= q.fee_cap_bps);
      }
      for (const e of events) {
        const d = e.payload.data;
        if (e.event_type === 'quote_accepted' && d.quote_version === q.version) {
          check(`${d.accepted_by_role} acceptance binds the final quote`, d.quote_event_hash === qe.event_hash && d.customer_total_paise === q.customer_total_paise);
        }
        if (e.event_type === 'simulated_settlement_recorded') {
          check('settlement equals the agreement', d.gross_paise === q.customer_total_paise && d.worker_share_paise === q.worker_share_paise && d.platform_fee_paise === q.platform_fee_paise);
          const tx = d.ledger_transaction;
          const sum = (dir: string) => tx.entries.filter((x: AnyObj) => x.direction === dir).reduce((n: number, x: AnyObj) => n + x.amount_paise, 0);
          check('ledger balanced', sum('debit') === sum('credit') && sum('debit') === tx.amount_paise);
        }
      }
    }
    const cps: Record<number, AnyObj> = {};
    for (const cp of rec.checkpoints ?? []) {
      check(`checkpoint ${cp.checkpoint_index}: digest`, (await checkpointDigest(cp.body)) === cp.digest);
      cps[cp.checkpoint_index] = cp;
    }
    let covered = 0;
    for (const ev of events) {
      const proof = ev.inclusion_proof;
      if (!proof) continue;
      const cp = cps[proof.checkpoint_index];
      if (!check(`event ${ev.sequence}: checkpoint present`, !!cp)) continue;
      check(`event ${ev.sequence}: Merkle inclusion`,
        proof.tree_size === cp.body.event_count && proof.leaf_index === ev.sequence - cp.body.first_sequence &&
        (await verifyInclusion(ev.event_hash, proof.leaf_index, proof.tree_size, proof.path, cp.body.merkle_root)));
      covered += 1;
    }
    const tokens = (rec.checkpoints ?? []).filter((c: AnyObj) => c.external_timestamp?.time_stamp_response_der_b64).length;
    for (const cp of rec.checkpoints ?? []) {
      check(`checkpoint ${cp.checkpoint_index}: anchoring claim has evidence`,
        cp.anchor_status !== 'EXTERNALLY_ANCHORED' || !!cp.external_timestamp?.time_stamp_response_der_b64, 'claims a timestamp but has no token');
    }
    const external = tokens
      ? `${tokens} RFC 3161 token(s) present. The browser does not check timestamp signatures; run the offline verifier with an independently obtained TSA certificate.`
      : `Independent timestamp not yet available (${covered}/${events.length} events are in a local checkpoint).`;
    return done('LOCAL INTEGRITY VERIFIED', external);
  } catch (err) {
    failures.push({ check: 'receipt structure', detail: (err as Error).message });
    return done('VERIFICATION FAILED', 'not checked');
  }
}


// ===== helpers for the explorer and the tamper demonstration =====

export const shortHash = (h: string, head = 10, tail = 6) => (h.length > head + tail + 1 ? `${h.slice(0, head)}…${h.slice(-tail)}` : h);

const leafHash = async (h: string) => sha(concat(new Uint8Array([0]), fromHex(h)));
const nodeHash = async (a: Uint8Array, b: Uint8Array) => sha(concat(new Uint8Array([1]), a, b));
const split = (n: number) => { let k = 1; while (k << 1 < n) k <<= 1; return k; };
async function mth(leaves: Uint8Array[]): Promise<Uint8Array> {
  if (leaves.length === 1) return leaves[0];
  const k = split(leaves.length);
  return nodeHash(await mth(leaves.slice(0, k)), await mth(leaves.slice(k)));
}
async function pathFor(m: number, leaves: Uint8Array[]): Promise<Uint8Array[]> {
  if (leaves.length === 1) return [];
  const k = split(leaves.length);
  return m < k ? [...(await pathFor(m, leaves.slice(0, k))), await mth(leaves.slice(k))] : [...(await pathFor(m - k, leaves.slice(k))), await mth(leaves.slice(0, k))];
}
export async function merkleRootOf(eventHashes: string[]): Promise<string> {
  return hex((await mth(await Promise.all(eventHashes.map(leafHash)))).buffer as ArrayBuffer);
}
export async function inclusionPathOf(eventHashes: string[], index: number): Promise<string[]> {
  const leaves = await Promise.all(eventHashes.map(leafHash));
  return (await pathFor(index, leaves)).map((x) => hex(x.buffer as ArrayBuffer));
}

/** Does an RFC 3161 token (base64 DER) contain this exact 32-byte checkpoint digest as its signed imprint?
 *  This is NOT a signature check: it only tells whether the token could possibly apply to this digest. */
export function tokenMentionsDigest(tokenB64: string | null | undefined, digestHex: string): boolean {
  if (!tokenB64) return false;
  try {
    const bin = atob(tokenB64);
    const needle = Array.from(fromHex(digestHex), (b) => String.fromCharCode(b)).join('');
    return bin.includes(needle);
  } catch { return false; }
}

export type EventDiff = { sequence: number; event_type: string; status: 'same' | 'changed' | 'missing_in_copy' | 'extra_in_copy' };
/** Compare a receipt against an independently retained original. */
export function compareHistories(original: AnyObj, copy: AnyObj): { diffs: EventDiff[]; identical: boolean } {
  const a: AnyObj[] = original.events ?? [], b: AnyObj[] = copy.events ?? [];
  const diffs: EventDiff[] = a.map((e, i) => ({ sequence: e.sequence, event_type: e.event_type,
    status: !b[i] ? 'missing_in_copy' : b[i].event_hash === e.event_hash ? 'same' : 'changed' }));
  b.slice(a.length).forEach((e) => diffs.push({ sequence: e.sequence, event_type: e.event_type, status: 'extra_in_copy' }));
  return { diffs, identical: diffs.every((d) => d.status === 'same') };
}

export type Edits = { customer_total_paise?: number; worker_share_paise?: number; platform_fee_paise?: number };
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

/** Edit only the receipt's displayed summary (a lazy lie). */
export function editDisplayedSummary(rec: AnyObj, e: Edits): AnyObj {
  const r = clone(rec); Object.assign(r.summary, e); return r;
}

function forgeAmounts(node: any, from: AnyObj, to: AnyObj): void {
  const keys = ['customer_total_paise', 'worker_share_paise', 'platform_fee_paise', 'gross_paise', 'amount_paise', 'fee_paise', 'payout_paise', 'computed_paise', 'service_price_paise'];
  if (Array.isArray(node)) { node.forEach((n) => forgeAmounts(n, from, to)); return; }
  if (node && typeof node === 'object') for (const [k, v] of Object.entries(node)) {
    if (keys.includes(k) && typeof v === 'number' && v in to) node[k] = to[v as number]; else forgeAmounts(v, from, to);
  }
}

/** Edit the committed quote/settlement payloads but leave every hash alone (the hash chain must notice). */
export function editCommittedPayloads(rec: AnyObj, e: Edits): AnyObj {
  const r = clone(rec); const map = amountMap(rec, e);
  for (const sec of ['events', 'agreement', 'settlement']) if (r[sec]) forgeAmounts(r[sec], {}, map);
  Object.assign(r.summary, e);
  if (map[rec.summary.service_price_paise] !== undefined) r.summary.service_price_paise = map[rec.summary.service_price_paise];
  return r;
}
function amountMap(rec: AnyObj, e: Edits): Record<number, number> {
  const s = rec.summary, m: Record<number, number> = {};
  if (e.customer_total_paise !== undefined) {
    m[s.customer_total_paise] = e.customer_total_paise;
    if (s.service_price_paise === s.customer_total_paise) m[s.service_price_paise] = e.customer_total_paise;   // worker-borne policy: service price follows the total
  }
  if (e.worker_share_paise !== undefined) m[s.worker_share_paise] = e.worker_share_paise;
  if (e.platform_fee_paise !== undefined) m[s.platform_fee_paise] = e.platform_fee_paise;
  return m;
}

/** What a privileged operator can do: edit the committed amounts, then recompute every payload hash, event hash,
 *  per-booking link, Merkle tree and checkpoint digest. The result is internally consistent. It does NOT carry
 *  a valid external timestamp, because no TSA ever signed the new digest. */
export async function forgeSelfConsistent(rec: AnyObj, e: Edits): Promise<AnyObj> {
  const r = editCommittedPayloads(rec, e);
  const events: AnyObj[] = r.events;
  const first = events[0].sequence; let prevBooking: string | null = null;
  const renamed: Record<string, string> = {};
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    ev.sequence = first + i;
    const d = ev.payload.data;
    if (d && d.quote_event_hash) d.quote_event_hash = renamed[d.quote_event_hash] ?? d.quote_event_hash;
    ev.payload.booking_previous_event_hash = prevBooking;
    ev.payload_hash = await payloadHash(ev.payload);
    const old = ev.event_hash;
    ev.event_hash = await eventHash(ev.sequence, ev.previous_event_hash, ev.payload_hash);
    renamed[old] = ev.event_hash; prevBooking = ev.event_hash;
  }
  const hashes = events.map((x) => x.event_hash);
  const body = { ...rec.checkpoints[rec.checkpoints.length - 1].body, first_sequence: first, last_sequence: first + events.length - 1,
    event_count: events.length, merkle_root: await merkleRootOf(hashes), last_event_hash: hashes[hashes.length - 1] };
  const index = body.checkpoint_index;
  r.checkpoints = [{ checkpoint_index: index, body, digest: await checkpointDigest(body), anchor_status: 'LOCAL_ONLY', external_timestamp: null }];
  for (let i = 0; i < events.length; i++) {
    events[i].inclusion_proof = { checkpoint_index: index, leaf_index: i, tree_size: events.length, path: await inclusionPathOf(hashes, i) };
  }
  Object.assign(r.summary, e);
  return r;
}
