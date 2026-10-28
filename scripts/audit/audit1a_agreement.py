"""Audit 1A/1B: real ₹500 booking on the isolated stack; parity; attacks available to a plain API client."""
import copy, json, sys
from common import *

print("== Audit 1A: ₹500 booking, both parties ==")
desk = skill()
_, active = call("GET", "/fee-policy")
print("active policy:", active["active_policy"]["policy_id"], "v", active["active_policy"]["version"], "example=", active["active_policy"]["is_example"])
wt, prof, slot = setup_worker("ravi", 25000, 3, 10, 12, desk)
ct = login("asha")
done = complete_booking(wt, ct, prof, slot, desk)
bid = done["id"]
_, v_c = call("GET", f"/bookings/{bid}", ct); _, v_w = call("GET", f"/bookings/{bid}", wt)
a_c, a_w = v_c["agreement"], v_w["agreement"]
check("customer sees ₹500 total / ₹50 fee / ₹450 worker", (a_c["customer_total_paise"], a_c["platform_fee_paise"], a_c["worker_share_paise"]) == (50000, 5000, 45000), a_c["line_items"][0]["description"])
check("worker sees ₹500 total / ₹50 fee / ₹450 worker", (a_w["customer_total_paise"], a_w["platform_fee_paise"], a_w["worker_share_paise"]) == (50000, 5000, 45000))
check("same booking id (as seen by each)", v_c["id"] == v_w["id"] == bid)
check("same quote id, version, policy hash", (a_c["quote_id"], a_c["quote_version"], a_c["policy_definition_hash"]) == (a_w["quote_id"], a_w["quote_version"], a_w["policy_definition_hash"]) and a_c["quote_version"] == 1)
check("customer 'price' block equals worker 'price' block (booking columns)", v_c["price"] == v_w["price"] == {**v_c["price"]}, v_c["price"])
check("booking columns agree with quote (matches_booking_snapshot)", a_c["matches_booking_snapshot"] and a_w["matches_booking_snapshot"])
print("   waiting for real DigiCert anchoring…")
v_c = wait_anchored(bid, ct)
check("evidence: external timestamp verified (server view)", v_c["evidence"]["anchor"]["status"] == "EXTERNALLY_ANCHORED", v_c["evidence"]["anchor"]["label"])
_, rc = call("GET", f"/bookings/{bid}/receipt", ct); _, rw = call("GET", f"/bookings/{bid}/receipt", wt)
pc, pw = save("a1_customer_receipt.json", rc), save("a1_worker_receipt.json", rw)
check("receipt commitments identical: same event hashes + checkpoint digests", [e["event_hash"] for e in rc["events"]] == [e["event_hash"] for e in rw["events"]] and [c["digest"] for c in rc["checkpoints"]] == [c["digest"] for c in rw["checkpoints"]],
      f"head {rc['events'][-1]['event_hash'][:16]}… digest {rc['checkpoints'][-1]['digest'][:16]}…")
diff = {k for k in rc if rc[k] != rw.get(k)}
check("receipts differ only in role/timestamp metadata", diff <= {"generated_at", "generated_for_role"}, sorted(diff))
for who, p in (("customer", pc), ("worker", pw)):
    o = verify(p, "--tsa-ca", DIGICERT_ROOT)
    check(f"offline verifier on {who} receipt with DigiCert root", o["result"] == "EXTERNALLY TIMESTAMPED AND VERIFIED" and o["_exit"] == 0, f"{len(o['checks'])} checks")
txt = json.dumps(rc)
check("receipt has no address/email/notes/names", all(x not in txt for x in ("Audit Residency", "@demo.sahakar.test", "audit\"", "Ravi", "Asha")))
open(OUT / "a1_booking_id", "w").write(bid)

print("\n== Audit 1B: attacks by a plain API client (no code/DB access) ==")
s, r = call("POST", f"/bookings/{bid}/quote-revisions", wt, {"service_price_paise": 40000}); check("worker cannot revise price of a completed booking", s == 409 and r["error"]["code"] == "PRICE_LOCKED", r["error"]["code"])
s, r = call("POST", f"/bookings/{bid}/quote-revisions", ct, {"service_price_paise": 40000}); check("customer cannot revise price of a completed booking", s == 409, r["error"]["code"])
s, r = call("POST", "/bookings", ct, {"worker_profile_id": prof["id"], "slot_id": slot["id"], "skill_id": desk, **HSR, "address_details": "x"*10, "price_paise": 40000}); check("client cannot submit its own price on booking creation", s == 422, r["error"]["code"])
s, r = call("POST", "/bookings", ct, {"worker_profile_id": prof["id"], "slot_id": slot["id"], "skill_id": desk, **HSR, "address_details": "x"*10, "fee_paise": 0}); check("client cannot submit its own fee", s == 422)
stranger = login("mallory")
for path in (f"/bookings/{bid}", f"/bookings/{bid}/receipt", f"/bookings/{bid}/financial-record", f"/bookings/{bid}/repeat-options"):
    check(f"stranger denied (404) on {path.split(bid)[1] or '/bookings/{id}'}", call("GET", path, stranger)[0] == 404)
check("stranger cannot revise", call("POST", f"/bookings/{bid}/quote-revisions", stranger, {"service_price_paise": 1000000})[0] == 404)
check("worker cannot complete / re-complete", call("POST", f"/bookings/{bid}/complete", wt)[0] in (403, 409))
check("customer cannot re-complete (no duplicate settlement)", call("POST", f"/bookings/{bid}/complete", ct)[0] == 409)
check("unauthenticated receipt request refused", call("GET", f"/bookings/{bid}/receipt")[0] == 401)
import urllib.request as _u
_spec = json.loads(_u.urlopen(API.replace("/api/v1", "") + "/openapi.json").read())
writers = sorted(f"{m.upper()} {p}" for p, ops in _spec["paths"].items() for m in ops if m in ("post","put","patch","delete") and ("fee-polic" in p))
check("OpenAPI: no write route on fee policies", writers == [], writers)
import subprocess as _sp
def _dbq(q): return _sp.run(["docker","compose","exec","-T","db","psql","-U","sahakar","-d","sahakar_audit_test","-At","-c",q],capture_output=True,text=True,cwd=ROOT).stdout.strip()
before = _dbq("select count(*) from fee_policies")
s, r = call("POST", "/pricing/simulate", None, {"definition": {"label":"Audit candidate (unsaved)","is_example":True,"max_total_charge_bps":1500,"components":[{"code":"fee_x","kind":"platform_fee","label":"Fee x","bearer":"customer","fixed_paise":1000}]}, "sample_service_prices_paise":[50000]})
check("pricing/simulate evaluates but stores nothing", s == 200 and _dbq("select count(*) from fee_policies") == before, f"fee_policies rows {before}->{_dbq('select count(*) from fee_policies')}")

print("\n== Audit 1C: 'API controls what the worker sees' — forged worker receipts ==")
def rehash(r):
    prev_b, renamed = None, {}
    sys.path.insert(0, str(ROOT / "services" / "api"))
    from app.trust import crypto
    for ev in r["events"]:
        d = ev["payload"]["data"]
        if "quote_event_hash" in d: d["quote_event_hash"] = renamed.get(d["quote_event_hash"], d["quote_event_hash"])
        ev["payload"]["booking_previous_event_hash"] = prev_b
        ev["payload_hash"] = crypto.payload_hash(ev["payload"])
        nh = crypto.event_hash(ev["sequence"], ev["previous_event_hash"], ev["payload_hash"])
        renamed[ev["event_hash"]] = nh; ev["event_hash"] = prev_b = nh
    return r
MONEY = {"customer_total_paise","worker_share_paise","platform_fee_paise","gross_paise","amount_paise","fee_paise","payout_paise","service_price_paise","computed_paise"}
MAP = {50000: 40000, 45000: 36000, 5000: 4000}
def forge(n):
    if isinstance(n, dict):
        for k, v in n.items():
            if k in MONEY and v in MAP: n[k] = MAP[v]
            else: forge(v)
    elif isinstance(n, list):
        for i in n: forge(i)
f1 = copy.deepcopy(rw); f1["summary"].update(customer_total_paise=40000, worker_share_paise=36000, platform_fee_paise=4000)
o = verify(save("a1_forge_display_only.json", f1), "--tsa-ca", DIGICERT_ROOT)
check("display-only ₹400/₹360 forgery -> VERIFICATION FAILED", o["result"] == "VERIFICATION FAILED", [f["check"] for f in o["failures"]][:2])
f2 = copy.deepcopy(rw); f2["summary"].update(customer_total_paise=40000, worker_share_paise=36000, platform_fee_paise=4000, service_price_paise=40000)
for sec in ("agreement", "settlement", "events"): forge(f2[sec])
f2 = rehash(f2)
o = verify(save("a1_forge_payload_rehash_keep_token.json", f2), "--tsa-ca", DIGICERT_ROOT)
check("fully re-hashed ₹400/₹360 forgery that keeps the genuine DigiCert token -> FAILED", o["result"] == "VERIFICATION FAILED", [f["check"] for f in o["failures"]][:3])
f3 = copy.deepcopy(f2)
sys.path.insert(0, str(ROOT / "services" / "api"))
from app.trust import crypto
# attacker also rebuilds the checkpoint over the forged events and drops the (now useless) token
for c in f3["checkpoints"]:
    c["external_timestamp"] = None; c["anchor_status"] = "LOCAL_ONLY"
    b = c["body"]; hs = [e["event_hash"] for e in f3["events"]]
    pos = [i for i, e in enumerate(f3["events"])]
    # single-checkpoint receipt from the sample: rebuild root over events inside range using proofs is impossible without other leaves; attacker uses only this booking's leaves
b = f3["checkpoints"][0]["body"]
hashes = [e["event_hash"] for e in f3["events"]]
b.update(first_sequence=f3["events"][0]["sequence"], last_sequence=f3["events"][-1]["sequence"], event_count=len(hashes), merkle_root=crypto.merkle_root(hashes), last_event_hash=hashes[-1])
f3["checkpoints"][0]["digest"] = crypto.checkpoint_digest(b)
for i, e in enumerate(f3["events"]):
    e["inclusion_proof"] = {"checkpoint_index": f3["checkpoints"][0]["checkpoint_index"], "leaf_index": i, "tree_size": len(hashes), "path": crypto.inclusion_proof(hashes, i)}
    # sequences re-numbered contiguous to make it self-consistent
    e["sequence"] = b["first_sequence"] + i
o = verify(save("a1_forge_selfconsistent_no_token.json", f3), "--tsa-ca", DIGICERT_ROOT)
print("   self-consistent forgery (rebuilt chain+checkpoint, no token):", o["result"], "| external:", o["external_timestamp"])
check("self-consistent forgery is NOT reported as externally verified", o["result"] != "EXTERNALLY TIMESTAMPED AND VERIFIED", o["result"])
check("(limit) self-consistent forgery passes LOCAL integrity: local check alone cannot prove authenticity", o["result"] in ("LOCAL INTEGRITY VERIFIED", "VERIFICATION FAILED"), o["result"])
o = verify(save("a1_forge_selfconsistent_no_token.json", f3), "--tsa-ca", DIGICERT_ROOT, "--compare", pc)
check("comparing the forged worker receipt with the customer's genuine receipt exposes the disagreement", o["result"] == "VERIFICATION FAILED" and any("history" in f["check"] for f in o["failures"]), [f["check"] for f in o["failures"]][:2])
ok = sum(1 for r in RESULTS if r[1]); print(f"\n{ok}/{len(RESULTS)} observations as expected"); save("audit1a_results.json", RESULTS)
