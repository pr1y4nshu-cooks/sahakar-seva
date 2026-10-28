"""Audit 2: does the application ever report external anchoring without genuine evidence?
Runs a hostile local 'TSA' against a SEPARATE throwaway DB (sahakar_audit2_test); app instance on :8101; no dev data touched."""
import base64, http.server, json, os, subprocess, sys, threading, time, urllib.request, shutil, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api")); sys.path.insert(0, str(ROOT / "services" / "api" / "tests"))
os.environ["AUDIT_API"] = "http://127.0.0.1:8101/api/v1"
from common import *
from tsa_double import make_tsa
from app.trust import timestamping, crypto

DB2 = "postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit2_test"
def sh(*a, **k): return subprocess.run(a, capture_output=True, text=True, cwd=k.pop("cwd", ROOT), **k)
sh("docker","compose","exec","-T","db","psql","-U","sahakar","-d","postgres","-c","DROP DATABASE IF EXISTS sahakar_audit2_test WITH (FORCE)","-c","CREATE DATABASE sahakar_audit2_test OWNER sahakar_test")
sh("docker","compose","exec","-T","db","psql","-U","sahakar","-d","sahakar_audit2_test","-c","CREATE EXTENSION postgis","-c","CREATE EXTENSION btree_gist WITH SCHEMA public")
env = {**os.environ, "DATABASE_URL": DB2, "APP_ENV": "development", "DEV_AUTH_ENABLED": "true", "DEV_AUTH_SECRET": "x"*48, "DEV_AUTH_PASSCODE": PASS,
       "TSA_URL": "http://127.0.0.1:9999/tsa", "TSA_NAME": "Hostile test TSA", "TSA_CA_FILE": "trust/tsa/digicert-trusted-root-g4.pem",
       "ANCHOR_WORKER_ENABLED": "false", "ANCHOR_MAX_ATTEMPTS": "1", "ANCHOR_RETRY_BASE_SECONDS": "0"}
api_dir = ROOT / "services" / "api"
for cmd in ([f"{api_dir}/.venv/bin/alembic","upgrade","head"], [VENV_PY,"-m","app.db.seed"], [VENV_PY,"-m","app.cli.fee_policy","bootstrap-example"]):
    r = subprocess.run(cmd, cwd=api_dir, env=env, capture_output=True, text=True); assert r.returncode == 0, r.stderr[-300:]
server = subprocess.Popen([f"{api_dir}/.venv/bin/uvicorn","app.main:app","--host","127.0.0.1","--port","8101"], cwd=api_dir, env=env, stdout=open("/tmp/sahakar-audit/api2.log","w"), stderr=subprocess.STDOUT)
time.sleep(4)

# --- hostile TSA -------------------------------------------------------------------------------
attacker = make_tsa(Path(tempfile.mkdtemp()), "Attacker")
MODE = {"m": "honest"}; LAST = {}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])); m = MODE["m"]; LAST["req"] = body
        def send(code, ctype, data): self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def digicert(b):
            r = urllib.request.Request("http://timestamp.digicert.com", data=b, headers={"Content-Type": "application/timestamp-query"}); return urllib.request.urlopen(r, timeout=20).read()
        if m == "http500": return send(500, "text/plain", b"boom")
        if m == "html200": return send(200, "text/html", b"<html>200 OK granted</html>")
        if m == "garbage_tsr": return send(200, "application/timestamp-reply", os.urandom(200))
        if m == "attacker_ca": return send(200, "application/timestamp-reply", attacker.reply(body))
        if m == "honest": return send(200, "application/timestamp-reply", digicert(body))
        if m == "replay_other_digest":
            if "stored" not in LAST: LAST["stored"] = digicert(timestamping.build_request(crypto.sha256_hex(b"some other checkpoint")).der)
            return send(200, "application/timestamp-reply", LAST["stored"])
        if m == "strip_nonce":
            from asn1crypto import tsp
            req = tsp.TimeStampReq.load(body); d = req.native
            nr = timestamping.build_request(d["message_imprint"]["hashed_message"].hex()); nr2 = tsp.TimeStampReq({"version":"v1","message_imprint":req["message_imprint"],"cert_req":True})
            return send(200, "application/timestamp-reply", digicert(nr2.dump()))
        send(500, "text/plain", b"?")
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 9999), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

desk = skill(); n = {"i": 0}
def pending_event():
    n["i"] += 1
    wt, prof, slot = setup_worker(f"w{n['i']}", 25000, 3 + n["i"], 10, 12, desk); ct = login(f"c{n['i']}")
    return call("POST", "/bookings", ct, {"worker_profile_id": prof["id"], "slot_id": slot["id"], "skill_id": desk, **HSR, "address_details": "Flat 1, Hostile TSA test"})[1]["id"], ct
def anchor_once():
    r = subprocess.run([VENV_PY,"-m","app.cli.anchor","--once"], cwd=api_dir, env=env, capture_output=True, text=True); return r
def last_cp():
    q = "select checkpoint_index, anchor_status, coalesce(left(last_error,110),''), (tsa_response_b64 is not null), digest from anchor_checkpoints order by 1 desc limit 1"
    return sh("docker","compose","exec","-T","db","psql","-U","sahakar","-d","sahakar_audit2_test","-At","-F","|","-c",q).stdout.strip().split("|")

print("== A2.1 hostile / faulty TSA behaviours: the application's reported status ==")
EXPECT = {"honest": {"EXTERNALLY_ANCHORED"}, "http500": {"ANCHOR_FAILED", "ANCHOR_PENDING"}, "html200": {"ANCHOR_FAILED", "ANCHOR_PENDING"},
          "garbage_tsr": {"PROOF_INVALID"}, "attacker_ca": {"PROOF_INVALID"}, "replay_other_digest": {"PROOF_INVALID"}, "strip_nonce": {"PROOF_INVALID"}}
rows = {}
for mode in ["honest", "http500", "html200", "garbage_tsr", "attacker_ca", "replay_other_digest", "strip_nonce"]:
    MODE["m"] = mode; bid, ct = pending_event(); anchor_once(); idx, status, err, has_token, digest = last_cp()
    _, v = call("GET", f"/bookings/{bid}", ct); shown = v["evidence"]["anchor"]["status"]
    rows[mode] = (status, err)
    ok = status in EXPECT[mode] and (mode == "honest" or (status != "EXTERNALLY_ANCHORED" and shown != "EXTERNALLY_ANCHORED" and has_token != "t"))
    check(f"TSA mode '{mode}' -> checkpoint {idx} status {status}; booking badge '{shown}'", ok, err[:90] if err else "")
# unreachable TSA (nothing listening)
srv.shutdown(); srv.server_close()
bid, ct = pending_event(); anchor_once(); idx, status, err, has_token, _ = last_cp(); _, v = call("GET", f"/bookings/{bid}", ct)
check(f"TSA unreachable -> {status}; badge '{v['evidence']['anchor']['status']}'", status in ("ANCHOR_FAILED", "ANCHOR_PENDING") and v["evidence"]["anchor"]["status"] != "EXTERNALLY_ANCHORED", err[:70])
check("booking completion/request is independent of TSA availability (booking was created while TSA down)", bid is not None)

print("\n== A2.2 wrong trust anchor configured on the server ==")
other = Path(tempfile.mkdtemp()) / "other.pem"
import re, ssl
pem = open("/Users/shresthchauhan/.agentflow/.venv/lib/python3.14/site-packages/certifi/cacert.pem").read()
m = re.search(r"# Label: \"DigiCert Global Root G2\".*?(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)", pem, re.S); other.write_text(m.group(1) + "\n")
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 9999), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); MODE["m"] = "honest"
env2 = {**env, "TSA_CA_FILE": str(other)}
bid, ct = pending_event(); r = subprocess.run([VENV_PY,"-m","app.cli.anchor","--once"], cwd=api_dir, env=env2, capture_output=True, text=True); idx, status, err, has_token, _ = last_cp()
check(f"genuine DigiCert token under a DIFFERENT pinned root (DigiCert Global Root G2) -> {status}", status == "PROOF_INVALID", err[:100])
srv.shutdown()
server.terminate()
save("audit2_hostile_tsa.json", rows)
ok = sum(1 for r in RESULTS if r[1]); print(f"\n{ok}/{len(RESULTS)}"); save("audit2a_results.json", RESULTS)
