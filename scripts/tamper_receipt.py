#!/usr/bin/env python3
"""Make an ALTERED COPY of a receipt file, to demonstrate that verification catches it. Never touches a server or
a database: it reads one JSON file and writes another.

    python3 scripts/tamper_receipt.py original.json --mode display --worker-share 36000 --out altered.json
    python3 scripts/tamper_receipt.py original.json --mode payload --worker-share 36000 --out altered.json
    python3 scripts/tamper_receipt.py original.json --mode rehash  --worker-share 36000 --out altered.json
    python3 scripts/verify_receipt.py altered.json --compare original.json

Modes (amounts are integer paise):
  display  change only the summary a person would read                 -> verification FAILS
  payload  change the committed agreement but keep every hash          -> verification FAILS
  (Cutting only the worker amount while the customer total stays the same is caught by plain arithmetic:
   worker + charges must equal the customer total. A consistent forgery changes total, charges and payout together:
   --customer-total 40000 --worker-share 36000 --platform-fee 4000.)
  rehash   change amounts, then recompute every payload/event hash, the per-booking links, the Merkle tree and
           the checkpoint digest, as a database operator could. The result is internally consistent, so a LOCAL
           check passes; the external timestamp token no longer matches (it is dropped), and --compare against the
           original exposes the change. This mode exists to show why local hashes alone are not enough.
"""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_receipt as vr  # reuse the verifier's own hash definitions, so both sides agree by construction

MONEY = {"customer_total_paise", "worker_share_paise", "platform_fee_paise", "gross_paise", "amount_paise", "fee_paise", "payout_paise", "computed_paise", "service_price_paise"}


def forge(node, mapping):
    if isinstance(node, list):
        for n in node:
            forge(n, mapping)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in MONEY and isinstance(v, int) and v in mapping:
                node[k] = mapping[v]
            else:
                forge(v, mapping)


def merkle_root(hashes):
    def leaf(h): return hashlib.sha256(b"\x00" + bytes.fromhex(h)).digest()
    def node(a, b): return hashlib.sha256(b"\x01" + a + b).digest()
    def split(n):
        k = 1
        while k << 1 < n: k <<= 1
        return k
    def mth(xs):
        return xs[0] if len(xs) == 1 else node(mth(xs[:split(len(xs))]), mth(xs[split(len(xs)):]))
    return mth([leaf(h) for h in hashes]).hex()


def inclusion_path(hashes, index):
    def leaf(h): return hashlib.sha256(b"\x00" + bytes.fromhex(h)).digest()
    def node(a, b): return hashlib.sha256(b"\x01" + a + b).digest()
    def split(n):
        k = 1
        while k << 1 < n: k <<= 1
        return k
    def mth(xs):
        return xs[0] if len(xs) == 1 else node(mth(xs[:split(len(xs))]), mth(xs[split(len(xs)):]))
    def path(m, xs):
        if len(xs) == 1: return []
        k = split(len(xs))
        return path(m, xs[:k]) + [mth(xs[k:])] if m < k else path(m - k, xs[k:]) + [mth(xs[:k])]
    return [p.hex() for p in path(index, [leaf(h) for h in hashes])]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("receipt")
    ap.add_argument("--mode", choices=("display", "payload", "rehash"), default="display")
    ap.add_argument("--worker-share", type=int, help="altered worker amount, paise")
    ap.add_argument("--customer-total", type=int, help="altered customer total, paise")
    ap.add_argument("--platform-fee", type=int, help="altered platform charges, paise")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rec = json.load(open(a.receipt, encoding="utf-8"))
    s = rec["summary"]
    edits = {k: v for k, v in (("worker_share_paise", a.worker_share), ("customer_total_paise", a.customer_total), ("platform_fee_paise", a.platform_fee)) if v is not None}
    if not edits:
        print("give at least one of --worker-share/--customer-total/--platform-fee", file=sys.stderr)
        return 2
    mapping = {s[k]: v for k, v in edits.items()}
    if "customer_total_paise" in edits and s.get("service_price_paise") == s["customer_total_paise"]:
        mapping[s["service_price_paise"]] = edits["customer_total_paise"]   # a worker-borne policy: service price follows the total
    out = copy.deepcopy(rec)
    if a.mode != "display":
        for sec in ("events", "agreement", "settlement"):
            if out.get(sec): forge(out[sec], mapping)
    out["summary"].update(edits)
    if a.mode != "display" and mapping.get(s.get("service_price_paise")) is not None:
        out["summary"]["service_price_paise"] = mapping[s["service_price_paise"]]   # keep the summary consistent with the forged payload
    if a.mode == "rehash":
        events = out["events"]
        first, prev_b, renamed = events[0]["sequence"], None, {}
        for i, ev in enumerate(events):
            ev["sequence"] = first + i
            d = ev["payload"].get("data", {})
            if d.get("quote_event_hash"): d["quote_event_hash"] = renamed.get(d["quote_event_hash"], d["quote_event_hash"])
            ev["payload"]["booking_previous_event_hash"] = prev_b
            ev["payload_hash"] = vr.payload_hash(ev["payload"])
            old = ev["event_hash"]
            ev["event_hash"] = vr.event_hash(ev["sequence"], ev["previous_event_hash"], ev["payload_hash"])
            renamed[old] = prev_b = ev["event_hash"]
        hashes = [e["event_hash"] for e in events]
        body = dict(rec["checkpoints"][-1]["body"], first_sequence=first, last_sequence=first + len(events) - 1, event_count=len(events),
                    merkle_root=merkle_root(hashes), last_event_hash=hashes[-1])
        idx = body["checkpoint_index"]
        out["checkpoints"] = [{"checkpoint_index": idx, "body": body, "digest": vr.checkpoint_digest(body), "anchor_status": "LOCAL_ONLY", "external_timestamp": None}]
        for i, ev in enumerate(events):
            ev["inclusion_proof"] = {"checkpoint_index": idx, "leaf_index": i, "tree_size": len(events), "path": inclusion_path(hashes, i)}
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"wrote {a.out} ({a.mode}): {', '.join(f'{k}: {s[k]} -> {v}' for k, v in edits.items())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
