"""Shared helpers for the independent audit harness. Talks ONLY to the isolated audit API (:8100) and the
throwaway database sahakar_audit_test. Refuses to run against anything else."""
import json, os, subprocess, sys, time, urllib.error, urllib.request, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = os.environ.get("AUDIT_API", "http://127.0.0.1:8100/api/v1")
PASS = Path("/tmp/sahakar-audit/passcode").read_text().strip()
OUT = Path("/tmp/sahakar-audit"); OUT.mkdir(exist_ok=True)
VERIFIER = ROOT / "scripts" / "verify_receipt.py"
DIGICERT_ROOT = ROOT / "services" / "api" / "trust" / "tsa" / "digicert-trusted-root-g4.pem"
AUDIT_DB_URL = "postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit_test"
VENV_PY = str(ROOT / "services" / "api" / ".venv" / "bin" / "python")
TAG = uuid.uuid4().hex[:6]
RESULTS = []

assert API.split(":")[2].split("/")[0] in ("8100", "8101"), "audit harness must target an isolated audit API (8100/8101), never the dev API (8000)"

def call(method, path, token=None, body=None):
    req = urllib.request.Request(f"{API}{path}", method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(); return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: return e.code, json.loads(raw)
        except Exception: return e.code, {"raw": raw.decode(errors="replace")[:300]}

def login(who):
    s, b = call("POST", "/dev-auth/token", body={"email": f"{who}-{TAG}@demo.sahakar.test", "passcode": PASS, "display_name": who.title()})
    assert s == 200, (s, b); return b["access_token"]

def at(days, hour):
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=days)
    return base.replace(hour=hour).isoformat()

def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'OBSERVED-OK' if ok else 'DEVIATION'}] {name}{(' — ' + str(detail)) if detail else ''}")

def verify(path, *extra):
    p = subprocess.run([sys.executable, str(VERIFIER), str(path), "--json", *map(str, extra)], capture_output=True, text=True)
    try: out = json.loads(p.stdout)
    except Exception: out = {"result": "CRASH", "stderr": p.stderr[-400:], "failures": []}
    out["_exit"] = p.returncode; return out

def save(name, obj):
    p = OUT / name; p.write_text(json.dumps(obj, indent=2, default=str)); return p

def setup_worker(name, rate_paise, day, h0, h1, skill_id, where=None):
    where = where or {"locality": "Koramangala", "latitude": 12.9352, "longitude": 77.6245}
    t = login(name)
    call("POST", "/worker-profiles", t, {"display_name": f"{name.title()} {TAG}"})
    call("POST", "/worker-profiles/me/skills", t, {"skill_id": skill_id})
    call("PUT", "/worker-profiles/me/service-settings", t, {**where, "radius_km": 5, "hourly_rate_paise": rate_paise})
    _, slot = call("POST", "/worker-profiles/me/availability", t, {"starts_at": at(day, h0), "ends_at": at(day, h1)})
    _, prof = call("GET", "/worker-profiles/me", t)
    return t, prof, slot

HSR = {"locality": "HSR Layout", "latitude": 12.9116, "longitude": 77.6474}
def skill(slug="desk-assembly"):
    _, s = call("GET", "/skills"); return next(x["id"] for x in s if x["slug"] == slug)

def complete_booking(worker_tok, cust_tok, prof, slot, skill_id):
    s, b = call("POST", "/bookings", cust_tok, {"worker_profile_id": prof["id"], "slot_id": slot["id"], "skill_id": skill_id, **HSR,
                "address_details": "Flat 9, Audit Residency", "customer_notes": "audit"})
    assert s == 201, (s, b)
    assert call("POST", f"/bookings/{b['id']}/accept", worker_tok, {"quote_version": 1})[0] == 200
    call("POST", f"/bookings/{b['id']}/start", worker_tok)
    s, done = call("POST", f"/bookings/{b['id']}/complete", cust_tok); assert s == 200, (s, done)
    return done

def wait_anchored(booking_id, tok, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        _, v = call("GET", f"/bookings/{booking_id}", tok)
        a = v["evidence"]["anchor"]
        if a["status"] == "EXTERNALLY_ANCHORED" and a["events_externally_anchored"] == a["events_total"]: return v
        time.sleep(4)
    return v
