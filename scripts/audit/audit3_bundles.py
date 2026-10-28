"""Audit 3: portable verification. Runs the verifier from an isolated dir, clean venv, NETWORK DENIED (macOS sandbox)."""
import base64, copy, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api")); sys.path.insert(0, str(ROOT / "services" / "api" / "tests"))
from common import *
from app.trust import crypto, timestamping
from tsa_double import make_tsa

W = Path("/tmp/sahakar-audit/a3"); shutil.rmtree(W, ignore_errors=True); W.mkdir()
shutil.copy(VERIFIER, W / "verify_receipt.py"); shutil.copy("/tmp/sahakar-audit/a2/g4.pem", W / "digicert_root.pem")   # root: fresh from DigiCert (Audit 2)
PY = "/tmp/sahakar-audit/cleanvenv/bin/python"
SB = '(version 1)(allow default)(deny network*)'
def run(name, rec, *extra, root=True):
    f = W / f"{name}.json"; f.write_text(json.dumps(rec))
    args = [PY, "verify_receipt.py", f.name, "--json"] + (["--tsa-ca", "digicert_root.pem"] if root else []) + list(extra)
    p = subprocess.run(["sandbox-exec", "-p", SB] + args, cwd=W, capture_output=True, text=True, env={"PATH": os.environ.get("AUDIT_PATH", "/opt/homebrew/bin:/usr/bin:/bin"), "HOME": str(W)})
    try: o = json.loads(p.stdout)
    except Exception: o = {"result": "CRASH:" + p.stderr[-200:], "failures": []}
    o["_exit"] = p.returncode; return o

genuine = json.load(open("/tmp/sahakar-audit/retained_customer_receipt.json"))
other = json.load(open("/tmp/sahakar-audit/retained_worker_receipt.json"))   # same booking, other party's copy
EXT = "EXTERNALLY TIMESTAMPED AND VERIFIED"
o = run("genuine", genuine)
check(f"GENUINE bundle -> {o['result']} (exit {o['_exit']}, {len(o['checks'])} checks, sandbox: no network)", o["result"] == EXT and o["_exit"] == 0)
o = run("genuine_worker", other); check("GENUINE worker copy -> externally verified", o["result"] == EXT)
o = run("genuine_noroot", genuine, root=False); check(f"genuine bundle WITHOUT a trust anchor -> {o['result']} (must not claim external)", o["result"] == "LOCAL INTEGRITY VERIFIED" and o["external_timestamp"] != "VERIFIED")

def mut(fn): r = copy.deepcopy(genuine); fn(r); return r
ev = lambda r, t: next(e for e in r["events"] if e["event_type"] == t)
q = lambda r: ev(r, "quote_created")["payload"]["data"]["quote"]
tamper = {
 "01 customer total (summary)": mut(lambda r: r["summary"].update(customer_total_paise=40000)),
 "02 worker payout (summary)": mut(lambda r: r["summary"].update(worker_share_paise=36000)),
 "03 platform fee (summary)": mut(lambda r: r["summary"].update(platform_fee_paise=14000)),
 "04 booking id (summary)": mut(lambda r: r["summary"].update(booking_id="00000000-0000-0000-0000-000000000001")),
 "05 quote version (summary)": mut(lambda r: r["summary"].update(quote_version=2)),
 "06 event hash": mut(lambda r: r["events"][2].update(event_hash="ab" * 32)),
 "07 committed quote amount": mut(lambda r: q(r).update(worker_share_paise=36000)),
 "08 committed line item (hide fee)": mut(lambda r: q(r)["line_items"][0].update(amount_paise=0)),
 "09 committed policy percent (cheaper policy)": mut(lambda r: q(r)["policy_definition"]["components"][0].update(percent_bps=100)),
 "10 checkpoint merkle root": mut(lambda r: r["checkpoints"][-1]["body"].update(merkle_root="00" * 32)),
 "11 checkpoint digest": mut(lambda r: r["checkpoints"][-1].update(digest="11" * 32)),
 "12 drop a middle event": mut(lambda r: r["events"].pop(2)),
 "13 reorder two events": mut(lambda r: r["events"].__setitem__(slice(1, 3), [r["events"][2], r["events"][1]])),
 "14 splice in an event of another booking": mut(lambda r: r["events"].append({**copy.deepcopy(r["events"][0]), "sequence": r["events"][-1]["sequence"] + 1})),
 "15 claim anchored, token removed": mut(lambda r: r["checkpoints"][-1].update(external_timestamp=None)),
 "16 token from a DIFFERENT checkpoint (dev #1)": mut(lambda r: r["checkpoints"][-1]["external_timestamp"].update(time_stamp_response_der_b64=json.load(open('/tmp/sahakar-audit/a2/cp1.json'))["time_stamp_response_der_b64"])),
 "17 receipt format version changed": mut(lambda r: r.update(receipt_format="sahakar-seva/receipt/v2")),
 "18 attacker adds 'platform_public_key' + 'signature' fields AND changes amounts": mut(lambda r: (r.update(platform_public_key="-----BEGIN PUBLIC KEY-----MFkw...", signature="deadbeef"), r["summary"].update(worker_share_paise=36000))),
}
for name, rec in tamper.items():
    o = run(name.split()[0], rec); check(f"TAMPER {name} -> {o['result']}", o["result"] == "VERIFICATION FAILED", (o["failures"][0]["check"] if o["failures"] else ""))

print("\n== trust-anchor tests: does the verifier trust key material that arrives inside the bundle? ==")
att = make_tsa(Path(tempfile.mkdtemp()), "Attacker")
digest = genuine["checkpoints"][-1]["digest"]; req = timestamping.build_request(digest, int(genuine["checkpoints"][-1]["external_timestamp"]["request_nonce"]))
forged_tok = base64.b64encode(att.reply(req.der)).decode()
f = copy.deepcopy(genuine); f["checkpoints"][-1]["external_timestamp"]["time_stamp_response_der_b64"] = forged_tok
f["checkpoints"][-1]["external_timestamp"]["embedded_trust_anchor_pem"] = att.ca_pem.read_text()   # attacker ships its CA inside the bundle
o = run("forged_token_real_root", f); check(f"attacker-signed token + attacker CA embedded in bundle, verified with DigiCert root -> {o['result']}", o["result"] == "VERIFICATION FAILED")
o = run("forged_token_no_root", f, root=False); check(f"same bundle, NO --tsa-ca -> {o['result']} (must not be 'externally verified')", o["result"] != EXT)
shutil.copy(att.ca_pem, W / "attacker_ca.pem"); o = run("forged_token_user_error", f, root=False, *["--tsa-ca", "attacker_ca.pem"])
print(f"   [USER-ERROR CASE] attacker's CA supplied by the verifying person as --tsa-ca -> {o['result']}")
print("      verifier output identifies the trust anchor used:", any("fingerprint" in json.dumps(x).lower() or "digicert" in json.dumps(x).lower() or "subject" in json.dumps(x).lower() for x in o.get("external", [])), "->", o.get("external"))
check("(limit) verifier output echoes the trust-anchor identity/fingerprint so a user can notice a wrong anchor", any("fingerprint" in json.dumps(x).lower() or "sha256" in json.dumps(x).lower() for x in o.get("external", [])) , "it does not; wrong-anchor use is only caught by the user")

print("\n== completeness / unauthenticated-field probes ==")
trunc = mut(lambda r: r["events"].pop())      # suppress the last event (settlement)
o = run("trunc_last", trunc); print(f"   receipt with the LAST event (settlement) removed -> {o['result']}")
check("(limit) a receipt truncated at the tail still verifies: receipts prove history up to their last event, not completeness", o["result"] == EXT, o["result"])
t2 = mut(lambda r: (r["events"].pop(), r["settlement"].update(payout_paise=36000, fee_paise=4000)))
o = run("trunc_and_forge_settlement_section", t2); print(f"   last event removed AND the top-level 'settlement' section forged to 360/40 -> {o['result']}")
check("top-level 'settlement' section cannot be forged once the settlement event is removed", o["result"] == "VERIFICATION FAILED", o["result"])
t3 = mut(lambda r: r["booking"].update(status="cancelled")); o = run("status_field", t3); print(f"   unauthenticated booking.status forged to 'cancelled' -> {o['result']}")
check("(limit) descriptive 'booking.status' is not covered by the proof", o["result"] == "VERIFICATION FAILED", o["result"])
t4 = mut(lambda r: r.update(notice="Payments are REAL and bank-confirmed.")); o = run("notice_field", t4); print(f"   notice text replaced with a false claim -> {o['result']}")
ok = sum(1 for r in RESULTS if r[1]); print(f"\n{ok}/{len(RESULTS)} observations as expected (DEVIATION = finding / documented limit)"); save("audit3_results.json", RESULTS)
