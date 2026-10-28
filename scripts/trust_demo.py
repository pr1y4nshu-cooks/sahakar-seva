"""Trust-ledger live demonstration against the running local stack (Demos 1–6 of the upgrade brief).

Uses the local development identity provider, the real API, PostgreSQL and (if configured) the real
external RFC 3161 TSA. Every run creates new, uniquely tagged @demo.sahakar.test identities and never
modifies existing rows. Tampering is done only on COPIES of downloaded receipt files.

    DEV_AUTH_PASSCODE=... python3 scripts/trust_demo.py [--out /tmp/sahakar-trust-demo] [--anchor-wait 90]

Exit code 0 means every check passed. The receipts and tampered copies are left in --out for the
presenter to re-run the offline verifier by hand.
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_demo import HSR, KORAMANGALA, RESULTS, at, call, check, login  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts" / "verify_receipt.py"
TSA_CA = ROOT / "services" / "api" / "trust" / "tsa" / "digicert-trusted-root-g4.pem"


def section(title: str) -> None:
    print(f"\n{title}")


def verify(path: Path, *extra: str) -> dict:
    proc = subprocess.run([sys.executable, str(VERIFIER), str(path), "--json", *extra], capture_output=True, text=True)
    out = json.loads(proc.stdout)
    out["_exit"] = proc.returncode
    return out


def worker_with_slot(name: str, rate_paise: int, day: int, start_h: int, end_h: int, skill_id: str) -> tuple[str, dict, dict]:
    tok = login(name)
    call("POST", "/worker-profiles", tok, {"display_name": f"{name.title()} (demo)"})
    call("POST", "/worker-profiles/me/skills", tok, {"skill_id": skill_id})
    call("PUT", "/worker-profiles/me/service-settings", tok, {**KORAMANGALA, "radius_km": 5, "hourly_rate_paise": rate_paise})
    _, slot = call("POST", "/worker-profiles/me/availability", tok, {"starts_at": at(day, start_h), "ends_at": at(day, end_h)})
    _, profile = call("GET", "/worker-profiles/me", tok)
    return tok, profile, slot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/sahakar-trust-demo")
    ap.add_argument("--anchor-wait", type=int, default=90)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("DEV_AUTH_PASSCODE"):
        print("Set DEV_AUTH_PASSCODE (local demo identity).", file=sys.stderr)
        return 2

    _, skills = call("GET", "/skills")
    desk = next(s for s in skills if s["slug"] == "desk-assembly")["id"]

    _, active = call("GET", "/fee-policy")
    ap_ = active["active_policy"]
    print(f"\nActive fee policy: {ap_['policy_id']} v{ap_['version']} — {ap_['label']}")
    if not ap_["is_example"]:
        print("This demo's ₹500/₹450/₹50 figures assume the illustrative example policy; skipping amount checks.", file=sys.stderr)
        return 2
    section("Demo 1 — Transparent price (₹500 service, ILLUSTRATIVE example policy)")
    ravi, ravi_profile, slot = worker_with_slot("ravi", 25000, 3, 10, 12, desk)
    asha = login("asha")
    s, b = call("POST", "/bookings", asha, {"worker_profile_id": ravi_profile["id"], "slot_id": slot["id"], "skill_id": desk, **HSR,
                                            "address_details": "Flat 2A, Demo Residency", "customer_notes": "Two desks"})
    check("customer requests a booking (server computes the price)", s == 201, f"booking {b.get('id', '')[:8]}")
    _, as_customer = call("GET", f"/bookings/{b['id']}", asha)
    _, as_worker = call("GET", f"/bookings/{b['id']}", ravi)
    ca, wa = as_customer["agreement"], as_worker["agreement"]
    check("customer sees ₹500 = ₹450 worker + ₹50 fee",
          (ca["customer_total_paise"], ca["worker_share_paise"], ca["platform_fee_paise"]) == (50000, 45000, 5000))
    check("worker sees the identical gross, fee and payout",
          (wa["customer_total_paise"], wa["worker_share_paise"], wa["platform_fee_paise"]) == (50000, 45000, 5000))
    check("both see the same booking ID, quote ID and quote version",
          as_customer["id"] == as_worker["id"] and ca["quote_id"] == wa["quote_id"] and ca["quote_version"] == wa["quote_version"] == 1)
    check("both see the same fee policy ID, version, hash and line items",
          (ca["fee_policy_id"], ca["fee_policy_version"], ca["policy_definition_hash"], ca["line_items"])
          == (wa["fee_policy_id"], wa["fee_policy_version"], wa["policy_definition_hash"], wa["line_items"])
          and ca["fee_policy_id"] == ap_["policy_id"] and ca["is_example_policy"] is True)
    check("customer acceptance of quote v1 is recorded", bool(ca["customer_accepted_at"]))
    s, conf = call("POST", f"/bookings/{b['id']}/accept", ravi, {"quote_version": 1})
    check("worker accepts the same quote version", s == 200 and conf["agreement"]["worker_accepted_at"] is not None)

    section("Demo 2 — Completed booking and balanced ledger")
    call("POST", f"/bookings/{b['id']}/start", ravi)
    s, done = call("POST", f"/bookings/{b['id']}/complete", asha)
    check("customer confirms completion", s == 200 and done["status"] == "completed")
    _, record = call("GET", f"/bookings/{b['id']}/financial-record", ravi)
    tx = record["ledger_transactions"][0]
    check("ledger: debit clearing ₹500 = credit worker ₹450 + credit platform ₹50",
          tx["balanced"] and {(e["account"], e["direction"], e["amount_paise"]) for e in tx["entries"]} == {
              ("simulated_customer_payment_clearing", "debit", 50000), ("simulated_worker_entitlement", "credit", 45000),
              ("simulated_platform_fee_allocation", "credit", 5000)})
    check("settlement is labelled simulated", done["settlement"]["is_simulated"] and "SIMULATED" in done["settlement"]["label"])
    immut = subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "sahakar", "-d", "sahakar_seva", "-c",
                            f"BEGIN; UPDATE financial_ledger_entries SET amount_paise = 36000 WHERE transaction_id = '{tx['id']}' "
                            f"AND account_code = 'simulated_worker_entitlement'; ROLLBACK;"], capture_output=True, text=True, cwd=ROOT)
    check("database refuses to edit a posted ledger entry", "append-only" in immut.stderr)
    immut = subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "sahakar", "-d", "sahakar_seva", "-c",
                            f"BEGIN; UPDATE settlements SET payout_paise = 36000 WHERE booking_id = '{b['id']}'; ROLLBACK;"],
                           capture_output=True, text=True, cwd=ROOT)
    check("database refuses to edit the simulated settlement", "immutable" in immut.stderr)

    section("Demo 3 — Attempted hidden deduction (on a COPY of the receipt)")
    _, worker_receipt = call("GET", f"/bookings/{b['id']}/receipt", ravi)
    _, customer_receipt = call("GET", f"/bookings/{b['id']}/receipt", asha)
    (out / "worker-receipt.json").write_text(json.dumps(worker_receipt, indent=2))
    (out / "customer-receipt.json").write_text(json.dumps(customer_receipt, indent=2))
    check("customer and worker receipts carry identical committed events", worker_receipt["events"] == customer_receipt["events"])
    forged = copy.deepcopy(worker_receipt)
    forged["summary"].update(customer_total_paise=40000, worker_share_paise=36000, platform_fee_paise=4000)
    (out / "tampered-worker-receipt.json").write_text(json.dumps(forged, indent=2))
    v = verify(out / "tampered-worker-receipt.json")
    check("verifier detects ₹400 shown to the worker / ₹360 payout", v["result"] == "VERIFICATION FAILED",
          "; ".join(f["check"] for f in v["failures"][:3]))
    deep = copy.deepcopy(forged)
    for ev in deep["events"]:
        q = ev["payload"]["data"].get("quote")
        if q:
            q.update(customer_total_paise=40000, worker_share_paise=36000, platform_fee_paise=4000)
    (out / "tampered-payload-receipt.json").write_text(json.dumps(deep, indent=2))
    v = verify(out / "tampered-payload-receipt.json")
    check("verifier detects an edited committed quote payload", v["result"] == "VERIFICATION FAILED",
          "; ".join(f["check"] for f in v["failures"][:2]))

    section("Demo 4 — Independent verification")
    _, cfg = call("GET", "/trust/anchoring")
    anchored = False
    if cfg.get("tsa_configured"):
        deadline = time.time() + args.anchor_wait
        while time.time() < deadline:
            _, view = call("GET", f"/bookings/{b['id']}", asha)
            if view["evidence"]["anchor"]["status"] == "EXTERNALLY_ANCHORED" and view["evidence"]["anchor"]["events_externally_anchored"] == view["evidence"]["anchor"]["events_total"]:
                anchored = True
                break
            time.sleep(5)
    _, final_receipt = call("GET", f"/bookings/{b['id']}/receipt", asha)
    (out / "customer-receipt-final.json").write_text(json.dumps(final_receipt, indent=2))
    local = verify(out / "customer-receipt-final.json")
    check("offline verifier (no API, no DB): local integrity verified",
          local["local_integrity"] == "VERIFIED", local.get("message") or local["result"])
    if anchored:
        ext = verify(out / "customer-receipt-final.json", "--tsa-ca", str(TSA_CA))
        check(f"external RFC 3161 timestamp from {cfg['tsa_name']} verified against the pinned root",
              ext["result"] == "EXTERNALLY TIMESTAMPED AND VERIFIED", ext["external"][0]["detail"] if ext["external"] else "")
    else:
        check("no TSA evidence yet: verifier honestly reports local integrity only",
              local["result"] == "LOCAL INTEGRITY VERIFIED" and local["external_timestamp"] == "EXTERNAL EVIDENCE UNAVAILABLE",
              "Local integrity verified — independent timestamp not yet available.")
    hist = verify(out / "customer-receipt-final.json", "--compare", str(out / "customer-receipt.json"))
    check("history unchanged since the customer's earlier copy", hist["local_integrity"] == "VERIFIED" and not hist["failures"])

    section("Demo 5 — Retention: repeat booking, history, protection terms, dispute route")
    call("POST", "/worker-profiles/me/availability", ravi, {"starts_at": at(5, 14), "ends_at": at(5, 16)})
    s, opts = call("GET", f"/bookings/{b['id']}/repeat-options", asha)
    check("customer gets 'book again' options with current rate and free slots", s == 200 and opts["eligible"] and len(opts["available_slots"]) > 0)
    s, again = call("POST", "/bookings", asha, {"worker_profile_id": ravi_profile["id"], "slot_id": opts["available_slots"][0]["id"], "skill_id": desk,
                                                 **HSR, "address_details": opts["address_details"], "repeat_of_booking_id": b["id"]})
    check("repeat request is a NEW booking with a new quote v1, awaiting worker consent",
          s == 201 and again["id"] != b["id"] and again["status"] == "requested" and again["agreement"]["awaiting_acceptance_from"] == "worker")
    _, original = call("GET", f"/bookings/{b['id']}", asha)
    check("original booking unchanged", original["status"] == "completed" and original["agreement"]["customer_total_paise"] == 50000)
    _, mine = call("GET", "/bookings/mine", asha)
    check("booking history lists both bookings", {b["id"], again["id"]} <= {x["id"] for x in mine})
    check("dispute route offered on the completed booking", "dispute" in original["allowed_actions"])

    section("Demo 6 — Revenue sustainability")
    s, policy = call("GET", "/fee-policy")
    check("public fee policy is the active policy record (labelled example)",
          s == 200 and policy["active_policy"]["definition_hash"] == ap_["definition_hash"] and policy["active_policy"]["is_example"]
          and policy["rules"]["payments_mode"] == "simulated")
    candidate = {"label": "Scenario: ₹25 customer booking fee + 3% worker fee (candidate)", "is_example": True, "max_total_charge_bps": 1500,
                 "components": [{"code": "booking_fee", "kind": "platform_fee", "label": "Booking fee", "bearer": "customer", "fixed_paise": 2500},
                                {"code": "service_fee", "kind": "platform_fee", "label": "Service fee", "bearer": "worker", "percent_bps": 300}]}
    s, sim = call("POST", "/pricing/simulate", None, {"definition": candidate, "sample_service_prices_paise": [20000, 50000, 200000]})
    item = next(i for i in sim["samples"]["items"] if i["service_price_paise"] == 50000)
    check("pricing engine evaluates a candidate hybrid policy without activating it",
          s == 200 and sim["pricing_model"] == "hybrid" and (item["customer_total_paise"], item["worker_payout_paise"], item["platform_fee_paise"]) == (52500, 48500, 4000))
    _, still = call("GET", "/fee-policy")
    check("active policy unchanged by simulation", still["active_policy"]["definition_hash"] == ap_["definition_hash"])
    meena = login("meena")
    _, org = call("POST", "/organizations", meena, {"name": "Demo Housing Coop", "organization_type": "cooperative"})
    worker2, profile2, _ = worker_with_slot("kiran", 30000, 4, 9, 11, desk)
    _, job = call("POST", "/jobs", meena, {"skill_id": desk, "title": "Assemble two office desks", "description": "Two flat-pack desks for the coop office.",
                                           **HSR, "address_details": "Coop office, ground floor", "starts_at": at(6, 9), "duration_minutes": 120,
                                           "budget_paise": 70000, "organization_id": org["id"]})
    _, app_ = call("POST", f"/jobs/{job['id']}/applications", worker2, {})
    _, jb = call("POST", f"/jobs/{job['id']}/applications/{app_['id']}/select", meena)
    call("POST", f"/bookings/{jb['id']}/accept", worker2, {"quote_version": 1})
    call("POST", f"/bookings/{jb['id']}/start", worker2)
    call("POST", f"/bookings/{jb['id']}/complete", meena)
    s, summary = call("GET", f"/organizations/{org['id']}/financial-summary", meena)
    check("business dashboard shows recorded org bookings and fees",
          s == 200 and summary["completed_bookings"] == 1 and summary["agreed_spend_completed_paise"] == 70000 and summary["platform_fees_completed_paise"] == 7000)
    s, _ = call("GET", f"/organizations/{org['id']}/financial-summary", asha)
    check("non-members cannot see the organization's records", s == 404)
    s, _ = call("GET", "/economics/summary", asha)
    check("platform totals are staff-only", s == 403)

    passed = sum(1 for result in RESULTS if result[1] is True)
    print(f"\n{passed}/{len(RESULTS)} trust checks passed. Receipts and tampered copies: {out}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
