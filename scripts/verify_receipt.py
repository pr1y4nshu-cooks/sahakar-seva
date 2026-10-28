#!/usr/bin/env python3
"""SAHAKAR–SEVA offline receipt verifier.

Verifies a downloaded receipt file WITHOUT contacting the SAHAKAR API or reading its database. This is an
intentionally separate implementation of the formats in
docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md (it does not import the server code).

    python3 scripts/verify_receipt.py receipt.json
    python3 scripts/verify_receipt.py receipt.json --tsa-ca digicert-trusted-root-g4.pem
    python3 scripts/verify_receipt.py new.json --compare older-copy.json --json

Results:
    EXTERNALLY TIMESTAMPED AND VERIFIED  (exit 0)  every event is covered by a checkpoint whose RFC 3161
                                                   token verified against the trust anchor YOU supplied
    LOCAL INTEGRITY VERIFIED             (exit 3)  hashes, chain links, Merkle proofs and amounts are
                                                   internally consistent; external evidence unavailable
    EXTERNAL EVIDENCE UNAVAILABLE        (exit 3)  nothing to verify (legacy record without hash evidence)
    VERIFICATION FAILED                  (exit 1)  something does not match
Exit 2 is a usage error.

What a pass means: the agreed price breakdown and its allocations were recorded consistently and, if
externally timestamped, that the checkpoint digest existed by the TSA's time. It does NOT prove that real
money changed hands (payments in this pilot are simulated).

Dependencies: Python 3.10+. Optional: ``rfc8785`` (canonical JSON; a restricted-profile fallback is built
in), ``asn1crypto`` and the ``openssl`` command (both needed only to check RFC 3161 timestamp tokens).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

RECEIPT_FORMAT = "sahakar-seva/receipt/v1"
EVENT_FORMAT = "sahakar-seva/financial-event/v1"
CHECKPOINT_FORMAT = "sahakar-seva/checkpoint/v1"
PAYLOAD_DOMAIN = b"SAHAKAR-SEVA:financial-event-payload:v1\x00"
EVENT_DOMAIN = b"SAHAKAR-SEVA:financial-event:v1\x00"
CHECKPOINT_DOMAIN = b"SAHAKAR-SEVA:checkpoint:v1\x00"
GENESIS = "00" * 32
QUOTE_EVENTS = ("quote_created", "quote_revised")

EXTERNAL_OK = "EXTERNALLY TIMESTAMPED AND VERIFIED"
LOCAL_OK = "LOCAL INTEGRITY VERIFIED"
FAILED = "VERIFICATION FAILED"
UNAVAILABLE = "EXTERNAL EVIDENCE UNAVAILABLE"


# --- canonical JSON (RFC 8785) ---------------------------------------------------------------


def _profile_ok(v, path="$"):
    if v is None or isinstance(v, (bool, str)):
        return
    if isinstance(v, int):
        if abs(v) > 2**53 - 1:
            raise ValueError(f"{path}: integer out of range")
        return
    if isinstance(v, float):
        raise ValueError(f"{path}: floats are not part of the committed format")
    if isinstance(v, list):
        for i, x in enumerate(v):
            _profile_ok(x, f"{path}[{i}]")
        return
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str) or not k.isascii():
                raise ValueError(f"{path}: non-ASCII key")
            _profile_ok(x, f"{path}.{k}")
        return
    raise ValueError(f"{path}: unsupported type")


def canonical(value) -> bytes:
    """RFC 8785 bytes. Uses the ``rfc8785`` package when installed. The fallback is exact for this format's
    profile (integers, strings, booleans, null, arrays, objects with ASCII keys), which is enforced."""
    _profile_ok(value)
    try:
        import rfc8785  # type: ignore

        return rfc8785.dumps(value)
    except ImportError:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def payload_hash(payload) -> str:
    return sha256_hex(PAYLOAD_DOMAIN + canonical(payload))


def event_hash(sequence: int, prev_hex: str, payload_hash_hex: str) -> str:
    prev, ph = bytes.fromhex(prev_hex), bytes.fromhex(payload_hash_hex)
    if len(prev) != 32 or len(ph) != 32:
        raise ValueError("hash fields must be 32 bytes")
    return sha256_hex(EVENT_DOMAIN + int(sequence).to_bytes(8, "big") + prev + ph)


def checkpoint_digest(body) -> str:
    return sha256_hex(CHECKPOINT_DOMAIN + canonical(body))


def _leaf(h: str) -> bytes:
    return hashlib.sha256(b"\x00" + bytes.fromhex(h)).digest()


def _node(a: bytes, b: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + a + b).digest()


def verify_inclusion(leaf_hash_hex: str, index: int, size: int, path: list, root_hex: str) -> bool:
    """RFC 9162 §2.1.3.2."""
    if not 0 <= index < size:
        return False
    fn, sn, r = index, size - 1, _leaf(leaf_hash_hex)
    for p_hex in path:
        p = bytes.fromhex(p_hex)
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = _node(p, r)
            if not fn & 1:
                while fn and not fn & 1:
                    fn >>= 1
                    sn >>= 1
        else:
            r = _node(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r.hex() == root_hex


# --- verification --------------------------------------------------------------------------


class Report:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if not c["ok"]]


def _fee(total: int, bps: int) -> int:
    return (total * bps + 5000) // 10000


# --- fee policy engine (independent re-implementation of services/api/app/trust/pricing.py) ---------

POLICY_DOMAIN = b"SAHAKAR-SEVA:fee-policy:v1\x00"


def policy_hash(definition) -> str:
    return sha256_hex(POLICY_DOMAIN + canonical(definition))


def _applies(rule: str, for_org: bool) -> bool:
    return rule == "any" or (rule == "only") == for_org


def evaluate_policy(d: dict, service: int, origin: str, for_org: bool, at: str) -> dict:
    lines = []
    for c in d["components"]:
        if origin not in c["applies_to_origins"] or not _applies(c["organization_bookings"], for_org):
            continue
        computed = _fee(service, c["percent_bps"]) + c["fixed_paise"]
        if c["min_paise"] is not None:
            computed = max(computed, c["min_paise"])
        if c["max_paise"] is not None:
            computed = min(computed, c["max_paise"])
        promo = None
        for p in d["promotions"]:
            if c["code"] not in p["waives"] or not _applies(p["organization_bookings"], for_org):
                continue
            if (p["starts_at"] and at < p["starts_at"]) or (p["ends_at"] and at >= p["ends_at"]):
                continue
            if p["max_service_price_paise"] is not None and service > p["max_service_price_paise"]:
                continue
            promo = p
            break
        lines.append({"code": c["code"], "kind": c["kind"], "label": c["label"], "bearer": c["bearer"],
                      "percent_bps": c["percent_bps"], "fixed_paise": c["fixed_paise"], "min_paise": c["min_paise"],
                      "max_paise": c["max_paise"], "computed_paise": computed, "amount_paise": 0 if promo else computed,
                      "waived_by": promo["code"] if promo else None})
    by = lambda bearers: sum(x["amount_paise"] for x in lines if x["bearer"] in bearers)  # noqa: E731
    party = by(("customer", "business", "worker"))
    party_lines = [x for x in lines if x["bearer"] != "platform"]
    return {
        "lines": lines,
        "customer_total_paise": service + by(("customer", "business")),
        "worker_share_paise": service - by(("worker",)),
        "platform_fee_paise": sum(x["amount_paise"] for x in party_lines if x["kind"] == "platform_fee"),
        "additional_charges_paise": sum(x["amount_paise"] for x in party_lines if x["kind"] == "processing_charge"),
        "business_borne_paise": by(("business",)), "platform_borne_paise": by(("platform",)),
        "fee_bps": -(-party * 10000 // service), "within_ceiling": party * 10000 <= service * d["max_total_charge_bps"],
        "ceiling_bps": d["max_total_charge_bps"],
    }


def verify_events(rec: dict, rep: Report) -> dict | None:
    booking_id = rec.get("summary", {}).get("booking_id")
    rep.add("booking reference consistent", booking_id == rec.get("booking", {}).get("booking_id"),
            "summary and booking sections name the same booking")
    events = rec.get("events") or []
    prev_seq, prev_booking_hash = 0, None
    for i, ev in enumerate(events):
        p = ev.get("payload", {})
        label = f"event {ev.get('sequence')} ({ev.get('event_type')})"
        try:
            ph = payload_hash(p)
            eh = event_hash(ev["sequence"], ev["previous_event_hash"], ph)
        except (ValueError, KeyError, TypeError) as exc:
            rep.add(f"{label}: hashable", False, str(exc))
            continue
        rep.add(f"{label}: payload hash", ph == ev.get("payload_hash"), "recomputed SHA-256 of canonical payload")
        rep.add(f"{label}: event hash", eh == ev.get("event_hash"), "recomputed chained event hash")
        rep.add(f"{label}: format", p.get("format") == EVENT_FORMAT and p.get("event_type") == ev.get("event_type"))
        rep.add(f"{label}: booking id", p.get("booking_id") == booking_id, "event belongs to this receipt's booking")
        rep.add(f"{label}: order", ev["sequence"] > prev_seq and p.get("booking_event_index") == i,
                "global sequence increases and the per-booking index is continuous from 0")
        rep.add(f"{label}: booking chain link", p.get("booking_previous_event_hash") == prev_booking_hash,
                "links to the previous event of the same booking")
        prev_seq, prev_booking_hash = ev["sequence"], ev.get("event_hash")

    quotes = [e for e in events if e.get("event_type") in QUOTE_EVENTS]
    if not rep.add("agreement present", bool(quotes), "a committed quote event exists"):
        return None
    q_event = quotes[-1]
    q = q_event["payload"]["data"]["quote"]
    s = rec.get("summary", {})
    pairs = {
        "quote_version": q["version"], "customer_total_paise": q["customer_total_paise"],
        "worker_share_paise": q["worker_share_paise"], "platform_fee_paise": q["platform_fee_paise"],
        "additional_charges_paise": q["additional_charges_paise"], "tax_paise": q["tax_paise"], "fee_bps": q["fee_bps"],
    }
    if q.get("line_items") is not None:
        pairs.update(service_price_paise=q["service_price_paise"], fee_policy_id=q["fee_policy_id"],
                     fee_policy_version=q["fee_policy_version"], pricing_model=q["pricing_model"],
                     policy_definition_hash=q["policy_definition_hash"])
    for key, committed in pairs.items():
        rep.add(f"summary {key} matches committed quote", s.get(key) == committed, f"receipt shows {s.get(key)}, committed {committed}")
        agreement_key = key
        if agreement_key in rec.get("agreement", {}):
            rep.add(f"agreement {key} matches committed quote", rec["agreement"][agreement_key] == committed)
    amounts = [q["customer_total_paise"], q["worker_share_paise"], q["platform_fee_paise"], q["additional_charges_paise"], q["tax_paise"]]
    rep.add("no negative amounts", all(isinstance(a, int) and a >= 0 for a in amounts) and q["customer_total_paise"] > 0)
    rep.add("allocation reconciles", q["worker_share_paise"] + q["platform_fee_paise"] + q["additional_charges_paise"] + q["tax_paise"] == q["customer_total_paise"],
            "worker share + platform fee + charges + tax = customer total")
    expected_alloc = None
    if q.get("line_items") is not None:
        # Configurable policy (0006+): recompute every charge from the committed policy definition.
        d = q.get("policy_definition") or {}
        rep.add("fee policy definition matches its committed hash", policy_hash(d) == q.get("policy_definition_hash"),
                f"policy {q.get('fee_policy_id')} v{q.get('fee_policy_version')}")
        if rep.add("ceiling never above the 20% safety limit", d.get("max_total_charge_bps", 99999) <= 2000):
            ev = evaluate_policy(d, q["service_price_paise"], rec.get("booking", {}).get("origin") or q_event["payload"]["data"]["service"]["origin"],
                                 bool(q.get("for_organization")), q["evaluated_at"])
            rep.add("charges recomputed from the policy match the committed line items", ev["lines"] == q["line_items"])
            for k in ("customer_total_paise", "worker_share_paise", "platform_fee_paise", "additional_charges_paise", "fee_bps"):
                rep.add(f"recomputed {k} matches the quote", ev[k] == q[k], f"policy gives {ev[k]}, quote has {q[k]}")
            rep.add("charges within the policy ceiling", ev["within_ceiling"] and q["fee_cap_bps"] == ev["ceiling_bps"])
            expected_alloc = ev
        rep.add("service price within totals", q["worker_share_paise"] <= q["service_price_paise"] <= q["customer_total_paise"])
    else:
        rep.add("fee follows recorded rule", q["platform_fee_paise"] == _fee(q["customer_total_paise"], q["fee_bps"]) and q["fee_bps"] <= q["fee_cap_bps"],
                f"{q['fee_bps']} bps of the total, half-up, within the {q['fee_cap_bps']} bps cap")

    # Acceptances of the final quote reference its exact event hash and amounts.
    for e in events:
        d = e["payload"]["data"]
        if e["event_type"] == "quote_accepted" and d.get("quote_version") == q["version"]:
            rep.add(f"{d.get('accepted_by_role')} acceptance binds the final quote",
                    d.get("quote_event_hash") == q_event["event_hash"] and d.get("customer_total_paise") == q["customer_total_paise"]
                    and d.get("worker_share_paise") == q["worker_share_paise"] and d.get("platform_fee_paise") == q["platform_fee_paise"])
        if e["event_type"] == "booking_confirmed":
            rep.add("confirmation used the final quote version", d.get("quote_version") == q["version"])
    # Settlement and ledger.
    for e in events:
        d = e["payload"]["data"]
        if e["event_type"] == "simulated_settlement_recorded":
            rep.add("settlement equals agreed quote",
                    (d["gross_paise"], d["platform_fee_paise"], d["worker_share_paise"], d["quote_version"])
                    == (q["customer_total_paise"], q["platform_fee_paise"], q["worker_share_paise"], q["version"]))
            if "processing_charge_paise" in d:
                rep.add("settlement processing charge equals quote", d["processing_charge_paise"] == q["additional_charges_paise"])
            rep.add("settlement is labelled simulated", d.get("is_simulated") is True)
            _check_ledger(d["ledger_transaction"], rep, "settlement ledger")
            got = {x["account"]: x["amount_paise"] for x in d["ledger_transaction"]["entries"]}
            business = expected_alloc["business_borne_paise"] if expected_alloc else 0
            absorbed = expected_alloc["platform_borne_paise"] if expected_alloc else 0
            rep.add("ledger allocations equal the agreement",
                    got.get("simulated_customer_payment_clearing", 0) == q["customer_total_paise"] - business
                    and got.get("simulated_business_payment_clearing", 0) == business
                    and got.get("simulated_platform_promotion_expense", 0) == absorbed
                    and got.get("simulated_worker_entitlement", 0) == q["worker_share_paise"]
                    and got.get("simulated_platform_fee_allocation", 0) == q["platform_fee_paise"]
                    and got.get("simulated_processing_charge_allocation", 0) == q["additional_charges_paise"] + absorbed)
            st = rec.get("settlement")
            if st is not None:
                rep.add("settlement section matches committed settlement",
                        (st.get("gross_paise"), st.get("fee_paise"), st.get("payout_paise"))
                        == (d["gross_paise"], d["gross_paise"] - d["worker_share_paise"], d["worker_share_paise"]))
        if e["event_type"] == "ledger_reversal_posted":
            _check_ledger(d["ledger_transaction"], rep, "reversal ledger")
    return q


def _check_ledger(tx: dict, rep: Report, name: str) -> None:
    debit = sum(x["amount_paise"] for x in tx["entries"] if x["direction"] == "debit")
    credit = sum(x["amount_paise"] for x in tx["entries"] if x["direction"] == "credit")
    rep.add(f"{name} balanced", debit == credit == tx["amount_paise"] and all(x["amount_paise"] > 0 for x in tx["entries"]),
            f"debits {debit} = credits {credit} = {tx['amount_paise']}")


def verify_checkpoints(rec: dict, rep: Report) -> dict[int, dict]:
    cps = {}
    for cp in rec.get("checkpoints") or []:
        body = cp.get("body", {})
        idx = cp.get("checkpoint_index")
        ok = rep.add(f"checkpoint {idx}: digest", checkpoint_digest(body) == cp.get("digest") and body.get("format") == CHECKPOINT_FORMAT
                     and body.get("checkpoint_index") == idx, "recomputed checkpoint digest")
        cps[idx] = {**cp, "_digest_ok": ok}
    for ev in rec.get("events") or []:
        proof = ev.get("inclusion_proof")
        if not proof:
            continue
        cp = cps.get(proof.get("checkpoint_index"))
        if not rep.add(f"event {ev['sequence']}: checkpoint present", cp is not None):
            continue
        b = cp["body"]
        in_range = b["first_sequence"] <= ev["sequence"] <= b["last_sequence"] and proof["leaf_index"] == ev["sequence"] - b["first_sequence"] \
            and proof["tree_size"] == b["event_count"]
        rep.add(f"event {ev['sequence']}: position in checkpoint", in_range)
        rep.add(f"event {ev['sequence']}: Merkle inclusion", verify_inclusion(ev["event_hash"], proof["leaf_index"], proof["tree_size"], proof["path"], b["merkle_root"]),
                f"included in checkpoint {cp['checkpoint_index']} root")
        if ev["sequence"] == b["last_sequence"]:
            rep.add(f"event {ev['sequence']}: checkpoint head", ev["event_hash"] == b["last_event_hash"])
    return cps


def _openssl_can_verify_timestamps(openssl: str) -> tuple[bool, str]:
    """`openssl ts -verify -digest … -attime …` needs OpenSSL 1.1.1+/3.x. macOS /usr/bin/openssl is LibreSSL,
    which lacks -attime; using it would make a GENUINE receipt look forged. Detect that instead of misreporting."""
    try:
        r = subprocess.run([openssl, "ts", "-help"], capture_output=True, text=True, timeout=15)
        version = subprocess.run([openssl, "version"], capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False, f"could not run {openssl}"
    if "-attime" in (r.stdout + r.stderr):
        return True, version
    return False, (f"{version or openssl} cannot verify RFC 3161 timestamp tokens (no `ts -verify -attime`). "
                   "This is a tool limitation, not evidence of tampering. Install OpenSSL 3 (macOS: `brew install openssl`) and set "
                   "OPENSSL_BIN=/opt/homebrew/bin/openssl, then re-run.")


def _verify_tsa(cp: dict, ca_file: str | None) -> tuple[str, str]:
    """Return (state, detail) where state is 'verified', 'unavailable' or 'failed'."""
    ext = cp.get("external_timestamp")
    if cp.get("anchor_status") == "EXTERNALLY_ANCHORED" and not (ext and ext.get("time_stamp_response_der_b64")):
        return "failed", "claims external anchoring but carries no timestamp token"
    if not ext:
        return "unavailable", f"no external timestamp (status {cp.get('anchor_status')})"
    if not ca_file:
        return "unavailable", "timestamp token present; supply --tsa-ca with an independently obtained TSA root to check it"
    if not os.path.isfile(ca_file):
        return "unavailable", f"trust anchor file not found: {ca_file}"
    try:
        from asn1crypto import tsp  # type: ignore
    except ImportError:
        return "unavailable", "install asn1crypto to check RFC 3161 tokens (pip install asn1crypto)"
    openssl = os.environ.get("OPENSSL_BIN") or shutil.which("openssl")
    if not openssl:
        return "unavailable", "openssl command not found"
    ok_openssl, why = _openssl_can_verify_timestamps(openssl)
    if not ok_openssl:
        return "unavailable", why
    try:
        der = base64.b64decode(ext["time_stamp_response_der_b64"], validate=True)
        resp = tsp.TimeStampResp.load(der)
        if resp["status"]["status"].native not in ("granted", "granted_with_mods"):
            return "failed", "token status is not granted"
        signed = resp["time_stamp_token"]["content"]
        tst = signed["encap_content_info"]["content"].parsed
        imprint = tst["message_imprint"]
        if imprint["hash_algorithm"]["algorithm"].native != "sha256":
            return "failed", "unsupported imprint algorithm"
        if imprint["hashed_message"].native.hex() != cp["digest"]:
            return "failed", "token imprint does not equal the checkpoint digest"
        if ext.get("request_nonce") is not None and str(tst["nonce"].native) != str(ext["request_nonce"]):
            return "failed", "token nonce does not match the recorded request nonce"
        gen_time: datetime = tst["gen_time"].native
        if gen_time.tzinfo is None:
            gen_time = gen_time.replace(tzinfo=timezone.utc)
    except Exception as exc:  # noqa: BLE001 - malformed token = failed evidence
        return "failed", f"token could not be parsed: {type(exc).__name__}"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.tsr")
        with open(path, "wb") as fh:
            fh.write(der)
        r = subprocess.run([openssl, "ts", "-verify", "-digest", cp["digest"], "-in", path, "-CAfile", ca_file,
                            "-attime", str(int(gen_time.timestamp()))], capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        if r.returncode != 0 or "Verification: OK" not in out:
            return "failed", "signature or certificate chain did not verify against your trust anchor: " + (out.splitlines()[-1] if out else "")
    return "verified", f"RFC 3161 token verified; digest existed by {gen_time.astimezone(timezone.utc).isoformat()}"


def compare_with(older: dict, newer: dict, rep: Report) -> None:
    new_by_seq = {e["sequence"]: e for e in newer.get("events") or []}
    for e in older.get("events") or []:
        n = new_by_seq.get(e["sequence"])
        rep.add(f"history: event {e['sequence']} unchanged since your earlier copy",
                n is not None and n.get("event_hash") == e.get("event_hash"),
                "an event you held earlier is missing or different" if not n or n.get("event_hash") != e.get("event_hash") else "")
    rep.add("history: same booking", older.get("summary", {}).get("booking_id") == newer.get("summary", {}).get("booking_id"))


def verify(rec: dict, ca_file: str | None = None, older: dict | None = None) -> dict:
    rep = Report()
    if not rep.add("receipt format", rec.get("receipt_format") == RECEIPT_FORMAT, f"expected {RECEIPT_FORMAT}"):
        return _result(rep, FAILED, [], rec)
    events = rec.get("events") or []
    if not events:
        rep.add("hash-chain evidence", True, "legacy record: no committed events were collected for this booking")
        return _result(rep, UNAVAILABLE, [], rec)
    verify_events(rec, rep)
    cps = verify_checkpoints(rec, rep)
    if older is not None:
        compare_with(older, rec, rep)
    external = []
    verified_cps = set()
    for idx, cp in sorted(cps.items()):
        state, detail = _verify_tsa(cp, ca_file)
        external.append({"checkpoint_index": idx, "state": state, "detail": detail})
        if state == "failed":
            rep.add(f"checkpoint {idx}: external timestamp", False, detail)
        elif state == "verified" and cp["_digest_ok"]:
            verified_cps.add(idx)
    if rep.failed:
        return _result(rep, FAILED, external, rec)
    covered = [e for e in events if e.get("inclusion_proof") and e["inclusion_proof"]["checkpoint_index"] in verified_cps]
    if len(covered) == len(events):
        return _result(rep, EXTERNAL_OK, external, rec)
    return _result(rep, LOCAL_OK, external, rec, covered=len(covered))


def _result(rep: Report, result: str, external: list, rec: dict, covered: int | None = None) -> dict:
    events = rec.get("events") or []
    out = {
        "result": result,
        "local_integrity": "FAILED" if rep.failed else ("NOT AVAILABLE" if not events else "VERIFIED"),
        "external_timestamp": "VERIFIED" if result == EXTERNAL_OK else ("FAILED" if any(x["state"] == "failed" for x in external) else UNAVAILABLE),
        "events_total": len(events),
        "events_externally_timestamped": len(events) if result == EXTERNAL_OK else (covered or 0),
        "booking_id": rec.get("summary", {}).get("booking_id"),
        "summary": rec.get("summary"),
        "external": external,
        "failures": rep.failed,
        "checks": rep.checks,
        "disclaimer": "Verifies agreement-record integrity (and timestamped existence where shown). It does not prove real money moved.",
    }
    if result == LOCAL_OK:
        out["message"] = "Local integrity verified — independent timestamp not yet available."
    return out


def _rupees(p) -> str:
    return "—" if p is None else f"₹{p / 100:,.2f}"


def human(out: dict) -> str:
    s = out.get("summary") or {}
    lines = [
        f"RESULT: {out['result']}",
        out.get("message", ""),
        f"Booking: {out.get('booking_id')}   quote version: {s.get('quote_version')}",
        f"Service price {_rupees(s.get('service_price_paise'))} · customer total {_rupees(s.get('customer_total_paise'))} = worker payout "
        f"{_rupees(s.get('worker_share_paise'))} + platform fee {_rupees(s.get('platform_fee_paise'))} + modeled processing "
        f"{_rupees(s.get('additional_charges_paise'))} (tax {_rupees(s.get('tax_paise'))})",
        f"Fee policy: {s.get('fee_policy_id')} v{s.get('fee_policy_version')} ({s.get('pricing_model')})",
        f"Local integrity: {out['local_integrity']}   External timestamp: {out['external_timestamp']} "
        f"({out['events_externally_timestamped']}/{out['events_total']} events)",
    ]
    for x in out["external"]:
        lines.append(f"  checkpoint {x['checkpoint_index']}: {x['state']} — {x['detail']}")
    if out["failures"]:
        lines.append("Failures:")
        lines += [f"  ✗ {f['check']}: {f['detail']}" for f in out["failures"]]
    lines.append(f"({len(out['checks'])} checks) {out['disclaimer']}")
    return "\n".join(line for line in lines if line)


EXIT = {EXTERNAL_OK: 0, LOCAL_OK: 3, UNAVAILABLE: 3, FAILED: 1}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify a SAHAKAR–SEVA receipt offline.")
    ap.add_argument("receipt")
    ap.add_argument("--tsa-ca", help="PEM trust anchor for the TSA, obtained independently of the receipt")
    ap.add_argument("--compare", help="an earlier copy of the receipt you kept; its events must be unchanged")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    try:
        with open(args.receipt, encoding="utf-8") as fh:
            rec = json.load(fh)
        older = None
        if args.compare:
            with open(args.compare, encoding="utf-8") as fh:
                older = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"cannot read input: {exc}", file=sys.stderr)
        return 2
    try:
        out = verify(rec, args.tsa_ca, older)
    except Exception as exc:  # noqa: BLE001 - malformed receipt structure is a failure, not a crash
        out = {"result": FAILED, "local_integrity": "FAILED", "external_timestamp": UNAVAILABLE, "events_total": 0,
               "events_externally_timestamped": 0, "booking_id": None, "summary": None, "external": [],
               "failures": [{"check": "receipt structure", "ok": False, "detail": f"{type(exc).__name__}: {exc}"}],
               "checks": [], "disclaimer": ""}
    print(json.dumps(out, indent=2, ensure_ascii=False) if args.json else human(out))
    return EXIT[out["result"]]


if __name__ == "__main__":
    raise SystemExit(main())
