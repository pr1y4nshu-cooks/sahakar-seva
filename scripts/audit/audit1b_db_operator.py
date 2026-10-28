"""Audit 1D: attackers with database access, on the throwaway DB only (sahakar_audit_test)."""
import copy, json, os, shutil, subprocess, sys, time
os.environ["DATABASE_URL"] = "postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit_test"
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "services" / "api"))
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from common import *
from app.trust import crypto, integrity
from app.services import trust_service
from app.models.marketplace import Booking

eng = create_engine(AUDIT_DB_URL)
with eng.connect() as c:
    assert c.execute(text("select current_database()")).scalar() == "sahakar_audit_test", "WRONG DATABASE"
bid = (OUT / "a1_booking_id").read_text()
for who in ("customer", "worker"): shutil.copy(OUT / f"a1_{who}_receipt.json", OUT / f"retained_{who}_receipt.json")
RET_C, RET_W = OUT / "retained_customer_receipt.json", OUT / "retained_worker_receipt.json"
print("target booking", bid)
o = verify(RET_C, "--tsa-ca", DIGICERT_ROOT); check("baseline: retained receipt is EXTERNALLY verified", o["result"] == "EXTERNALLY TIMESTAMPED AND VERIFIED")

def db_error(sql, engine=eng, rollback=False, **p):
    """Run one statement; True DDL probes use rollback=True so the probe itself never changes the database."""
    try:
        with engine.connect() as c:
            t = c.begin(); c.execute(text(sql), p)
            (t.rollback if rollback else t.commit)()
        return None
    except Exception as e: return str(e.orig if hasattr(e, "orig") else e).splitlines()[0]

print("\n== D0: SQL as the application's own DB role, triggers intact ==")
tests = {
 "UPDATE ledger entry": "UPDATE financial_ledger_entries SET amount_paise=36000 WHERE account_code='simulated_worker_entitlement' AND transaction_id=(select id from financial_ledger_transactions where booking_id=:b)",
 "UPDATE settlement": "UPDATE settlements SET payout_paise=36000, fee_paise=4000, gross_paise=40000 WHERE booking_id=:b",
 "UPDATE event payload": "UPDATE financial_events SET payload_canonical='{}' WHERE booking_id=:b",
 "DELETE event": "DELETE FROM financial_events WHERE booking_id=:b",
 "UPDATE quote": "UPDATE price_quote_versions SET customer_total_paise=40000 WHERE booking_id=:b",
 "UPDATE checkpoint body": "UPDATE anchor_checkpoints SET merkle_root=repeat('0',64) WHERE checkpoint_index=1",
 "UPDATE anchored checkpoint status": "UPDATE anchor_checkpoints SET anchor_status='LOCAL_ONLY' WHERE anchor_status='EXTERNALLY_ANCHORED'",
 "UPDATE active policy": "UPDATE fee_policies SET definition_canonical='{}' WHERE status='active'",
 "TRUNCATE ledger": "TRUNCATE financial_ledger_entries",
 "UPDATE confirmed booking price (price only)": "UPDATE bookings SET price_paise=40000, fee_paise=4000, payout_paise=36000 WHERE id=:b",
}
for name, sql in tests.items():
    err = db_error(sql, b=bid); check(f"app role blocked: {name}", err is not None, (err or "NOT BLOCKED")[:110])

print("\n== D0b: a trigger-guard gap probe (status change + price change in ONE statement) on a fresh requested booking ==")
desk = skill(); wt, prof, slot = setup_worker("gap", 25000, 6, 10, 12, desk); ct = login("gapc")
s, b = call("POST", "/bookings", ct, {"worker_profile_id": prof["id"], "slot_id": slot["id"], "skill_id": desk, **HSR, "address_details": "Flat 1, Gap Probe"})
gid = b["id"]
err = db_error("UPDATE bookings SET status='confirmed', price_paise=40000, fee_paise=4000, payout_paise=36000 WHERE id=:b", b=gid)
_, wv = call("GET", f"/bookings/{gid}", wt)
print("   price update + confirm in one statement ->", "BLOCKED: " + err if err else "ACCEPTED by DB")
if not err:
    print("   API worker view: price block =", wv["price"]["price_paise"], wv["price"]["payout_paise"], "| agreement block =", wv["agreement"]["customer_total_paise"], wv["agreement"]["worker_share_paise"], "| matches_booking_snapshot =", wv["agreement"]["matches_booking_snapshot"])
    check("FINDING candidate: DB price guard bypassed when status changes in the same UPDATE", False, "booking columns diverge from the accepted quote; API shows two different prices")
    with eng.begin() as c: c.execute(text("ALTER TABLE bookings DISABLE TRIGGER USER")); c.execute(text("UPDATE bookings SET status='requested', price_paise=50000, fee_paise=5000, payout_paise=45000 WHERE id=:b"), {"b": gid}); c.execute(text("ALTER TABLE bookings ENABLE TRIGGER USER"))
else:
    check("price guard blocks combined status+price change", True, err[:100])

print("\n== D1: table-owner (the app role) disables triggers and tampers PARTIALLY; server integrity check + receipt export in the same txn, then ROLLBACK ==")
def tampered(label, sql_list, expect_codes):
    with eng.connect() as conn:
        t = conn.begin()
        for tbl in ("financial_events","financial_ledger_entries","financial_ledger_transactions","price_quote_versions","quote_acceptances"): conn.execute(text(f"ALTER TABLE {tbl} DISABLE TRIGGER USER"))
        conn.execute(text("ALTER TABLE settlements DISABLE TRIGGER USER")); conn.execute(text("ALTER TABLE bookings DISABLE TRIGGER USER"))
        for q in sql_list: conn.execute(text(q), {"b": bid})
        db = Session(bind=conn)
        rep = integrity.verify_database(db)
        codes = {p["code"] for p in rep["problems"]}
        booking = db.get(Booking, bid)
        rc = trust_service.receipt(db, booking, "worker"); p = save(f"d1_{label}.json", json.loads(json.dumps(rc, default=str)))
        t.rollback()
    ov = verify(p, "--tsa-ca", DIGICERT_ROOT)
    check(f"{label}: server integrity check flags it", not rep["ok"] and bool(codes & expect_codes), sorted(codes)[:4])
    return ov
ov = tampered("ledger_entry_only", ["UPDATE financial_ledger_entries SET amount_paise=36000 WHERE account_code='simulated_worker_entitlement' AND transaction_id=(select id from financial_ledger_transactions where booking_id=:b)"], {"LEDGER_UNBALANCED", "LEDGER_DIFFERS_FROM_COMMITTED_EVENT", "SETTLEMENT_LEDGER_MISMATCH"})
print("      exported receipt after ledger-only tamper ->", ov["result"], "(receipt is built from events; ledger rows are not in it)")
ov = tampered("settlement_only", ["UPDATE settlements SET payout_paise=36000, fee_paise=4000, gross_paise=40000 WHERE booking_id=:b"], {"SETTLEMENT_LEDGER_MISMATCH"})
check("settlement-only tamper: exported receipt fails offline verification", ov["result"] == "VERIFICATION FAILED", ov["result"])
ov = tampered("event_payload_no_rehash", ["UPDATE financial_events SET payload_canonical=replace(payload_canonical,'45000','36000') WHERE booking_id=:b"], {"PAYLOAD_HASH_MISMATCH"})
check("event payload tamper without re-hash: exported receipt fails offline verification", ov["result"] == "VERIFICATION FAILED", ov["result"])
ov = tampered("quote_row_only", ["UPDATE price_quote_versions SET customer_total_paise=40000, service_price_paise=40000, worker_share_paise=36000, platform_fee_paise=4000 WHERE booking_id=:b"], set())
print("      quote-row-only tamper: server integrity check ->", "see below")
with eng.connect() as conn:
    t = conn.begin(); conn.execute(text("ALTER TABLE price_quote_versions DISABLE TRIGGER USER"))
    conn.execute(text("UPDATE price_quote_versions SET customer_total_paise=40000, service_price_paise=40000, worker_share_paise=36000, platform_fee_paise=4000 WHERE booking_id=:b"), {"b": bid})
    rep = integrity.verify_database(Session(bind=conn)); t.rollback()
check("quote-row-only tamper (columns differ from the committed quote event) is detected by server integrity check", not rep["ok"], [p["code"] for p in rep["problems"]][:3] or "NOT DETECTED")

print("\n== D2: full coherent rewrite by the DB operator (events, hashes, checkpoints, ledger, settlement, booking) — COMMITTED to the audit DB ==")
MONEY = {"customer_total_paise","worker_share_paise","platform_fee_paise","gross_paise","amount_paise","fee_paise","payout_paise","service_price_paise","computed_paise"}
MAP = {50000: 40000, 45000: 36000, 5000: 4000}
def forge(n):
    if isinstance(n, dict):
        for k, v in n.items():
            if k in MONEY and v in MAP: n[k] = MAP[v]
            else: forge(v)
    elif isinstance(n, list):
        for i in n: forge(i)
def rename(n, m):
    if isinstance(n, dict): return {k: rename(v, m) for k, v in n.items()}
    if isinstance(n, list): return [rename(v, m) for v in n]
    return m.get(n, n) if isinstance(n, str) and len(n) == 64 else n
with eng.begin() as conn:
    for k in (0x5A4B0001, 0x5A4B0002): conn.execute(text("select pg_advisory_xact_lock(:k)"), {"k": k})
    for tbl in ("financial_events","financial_ledger_entries","financial_ledger_transactions","price_quote_versions","quote_acceptances","anchor_checkpoints","settlements","bookings"):
        conn.execute(text(f"ALTER TABLE {tbl} DISABLE TRIGGER USER"))
    evs = [dict(r._mapping) for r in conn.execute(text("select * from financial_events order by sequence"))]
    first = min(e["sequence"] for e in evs if str(e["booking_id"]) == bid)
    renamed, prev, last_by_booking = {}, None, {}
    for e in evs:
        if e["sequence"] < first: prev = e["event_hash"]; continue
        payload = json.loads(e["payload_canonical"])
        if str(e["booking_id"]) == bid: forge(payload)
        payload = rename(payload, renamed)
        if e["booking_id"]: payload["booking_previous_event_hash"] = last_by_booking.get(str(e["booking_id"]), None)
        canon = crypto.canonical(payload).decode(); ph = crypto.payload_hash(payload); eh = crypto.event_hash(e["sequence"], prev, ph)
        renamed[e["event_hash"]] = eh
        if e["booking_id"]: last_by_booking[str(e["booking_id"])] = eh
        conn.execute(text("update financial_events set payload_canonical=:c, payload_hash=:ph, previous_event_hash=:p, event_hash=:eh where id=:i"), {"c": canon, "ph": ph, "p": prev, "eh": eh, "i": e["id"]})
        e["new_hash"] = eh; prev = eh
    # rows that mirror the events
    conn.execute(text("update price_quote_versions set service_price_paise=40000, customer_total_paise=40000, worker_share_paise=36000, platform_fee_paise=4000 where booking_id=:b"), {"b": bid})
    lines = json.loads(conn.execute(text("select line_items_canonical from price_quote_versions where booking_id=:b limit 1"), {"b": bid}).scalar()); forge(lines)
    conn.execute(text("update price_quote_versions set line_items_canonical=:l where booking_id=:b"), {"l": crypto.canonical(lines).decode(), "b": bid})
    conn.execute(text("update financial_ledger_transactions set amount_paise=40000 where booking_id=:b"), {"b": bid})
    conn.execute(text("update financial_ledger_entries set amount_paise=case account_code when 'simulated_customer_payment_clearing' then 40000 when 'simulated_worker_entitlement' then 36000 else 4000 end where transaction_id=(select id from financial_ledger_transactions where booking_id=:b)"), {"b": bid})
    conn.execute(text("update settlements set gross_paise=40000, fee_paise=4000, payout_paise=36000 where booking_id=:b"), {"b": bid})
    conn.execute(text("update bookings set price_paise=40000, fee_paise=4000, payout_paise=36000 where id=:b"), {"b": bid})
    # rebuild checkpoints
    allev = {e["sequence"]: e for e in evs}
    prev_digest, n_cp = crypto.GENESIS_HASH, 0
    for cp in [dict(r._mapping) for r in conn.execute(text("select * from anchor_checkpoints order by checkpoint_index"))]:
        body = json.loads(cp["body_canonical"])
        if cp["last_sequence"] >= first:
            hs = [allev[s].get("new_hash", allev[s]["event_hash"]) for s in range(cp["first_sequence"], cp["last_sequence"] + 1)]
            body.update(merkle_root=crypto.merkle_root(hs), last_event_hash=hs[-1], previous_checkpoint_digest=prev_digest)
            digest = crypto.checkpoint_digest(body)
            conn.execute(text("update anchor_checkpoints set body_canonical=:b, digest=:d, merkle_root=:m, last_event_hash=:l, previous_checkpoint_digest=:p where id=:i"),
                         {"b": crypto.canonical(body).decode(), "d": digest, "m": body["merkle_root"], "l": body["last_event_hash"], "p": prev_digest, "i": cp["id"]})
            prev_digest = digest; n_cp += 1
        else: prev_digest = cp["digest"]
print(f"   rewrote {sum(1 for e in evs if e['sequence']>=first)} events and {n_cp} checkpoint(s) from sequence {first}; anchor status/token columns left untouched")

with Session(eng) as db: rep = integrity.verify_database(db)
check("(limit) server-side integrity check ('verify_ledger') reports OK on the rewritten database", rep["ok"], f"{rep['events_checked']} events, {rep['checkpoints_checked']} checkpoints")
wt2 = login("ravi") if False else None
# read through the real API as the original worker/customer
def tok_for(role_receipt):  # re-login not possible by id; use the same TAG users created in audit1a? find via db email
    pass
with eng.connect() as c:
    em = dict(c.execute(text("select u.email, 'x' from users u join worker_profiles w on w.user_id=u.id join bookings b on b.worker_profile_id=w.id where b.id=:b"), {"b": bid}).fetchall()[0]._mapping)
    cem = c.execute(text("select u.email from users u join bookings b on b.customer_user_id=u.id where b.id=:b"), {"b": bid}).scalar()
def tok(email):
    s, r = call("POST", "/dev-auth/token", body={"email": email, "passcode": PASS}); return r["access_token"]
wtok, ctok = tok(em["email"]), tok(cem)
_, v = call("GET", f"/bookings/{bid}", wtok)
a = v["agreement"]
print("   API worker view after rewrite:", a["customer_total_paise"], a["worker_share_paise"], a["platform_fee_paise"], "| anchor badge:", v["evidence"]["anchor"]["label"])
check("API serves the rewritten ₹400/₹360 to the worker (expected: operator controls what the API reads)", (a["customer_total_paise"], a["worker_share_paise"]) == (40000, 36000))
check("DEVIATION CANDIDATE: API still claims 'External timestamp verified' for the rewritten record", v["evidence"]["anchor"]["status"] != "EXTERNALLY_ANCHORED", v["evidence"]["anchor"]["status"] + " / " + v["evidence"]["anchor"]["label"])
_, fresh = call("GET", f"/bookings/{bid}/receipt", wtok); pf = save("d2_fresh_rewritten_receipt.json", fresh)
o = verify(pf, "--tsa-ca", DIGICERT_ROOT)
check("offline verifier on the rewritten receipt (old token kept): does not report external success", o["result"] != "EXTERNALLY TIMESTAMPED AND VERIFIED", f"{o['result']} :: {[f['check'] for f in o['failures']][:2]}")
o = verify(RET_W, "--tsa-ca", DIGICERT_ROOT); check("worker's retained ORIGINAL receipt still verifies externally (the original ₹500 existed by the TSA time)", o["result"] == "EXTERNALLY TIMESTAMPED AND VERIFIED")
o = verify(pf, "--tsa-ca", DIGICERT_ROOT, "--compare", RET_W); check("retained copy vs rewritten receipt: --compare exposes the rewrite", o["result"] == "VERIFICATION FAILED" and any("history" in f["check"] for f in o["failures"]), len(o["failures"]))
# Operator variant 1: hide the status
with eng.begin() as conn:
    conn.execute(text("ALTER TABLE anchor_checkpoints DISABLE TRIGGER USER"))
    conn.execute(text("update anchor_checkpoints set anchor_status='LOCAL_ONLY', tsa_response_b64=null, tsa_gen_time=null, verified_at=null, tsa_serial=null where last_sequence>=:f or :f between first_sequence and last_sequence"), {"f": first})
_, fresh2 = call("GET", f"/bookings/{bid}/receipt", wtok); pf2 = save("d2_rewritten_local_only.json", fresh2)
o = verify(pf2, "--tsa-ca", DIGICERT_ROOT)
check("(limit) rewritten, token-stripped receipt verifies as LOCAL INTEGRITY ONLY (self-consistent forgery)", o["result"] == "LOCAL INTEGRITY VERIFIED", o["result"])
o = verify(pf2, "--tsa-ca", DIGICERT_ROOT, "--compare", RET_W); check("…but the retained original exposes it", o["result"] == "VERIFICATION FAILED")
# Operator variant 2: re-anchor the forged history at the real TSA
with eng.begin() as conn:
    conn.execute(text("update anchor_checkpoints set anchor_status='ANCHOR_PENDING', attempt_count=0, next_attempt_at=now() where anchor_status='LOCAL_ONLY' and last_sequence>=:f"), {"f": first})
end = time.time() + 60
while time.time() < end:
    _, fresh3 = call("GET", f"/bookings/{bid}/receipt", wtok)
    if all(c["anchor_status"] == "EXTERNALLY_ANCHORED" for c in fresh3["checkpoints"]): break
    time.sleep(3)
pf3 = save("d2_rewritten_reanchored.json", fresh3)
o = verify(pf3, "--tsa-ca", DIGICERT_ROOT)
print("   re-anchored forged history verifies as:", o["result"])
check("(limit) a DB operator can obtain a GENUINE later timestamp over a rewritten history", o["result"] == "EXTERNALLY TIMESTAMPED AND VERIFIED", o["result"])
old_t = RET_W.read_text(); new_t = json.loads(pf3.read_text()); old = json.loads(old_t)
print("      original TSA time:", old["checkpoints"][-1]["external_timestamp"]["gen_time"], "| forged-history TSA time:", new_t["checkpoints"][-1]["external_timestamp"]["gen_time"])
o = verify(pf3, "--tsa-ca", DIGICERT_ROOT, "--compare", RET_W); check("only the participant-retained original (or a public mirror of earlier checkpoint digests) exposes the re-anchored rewrite", o["result"] == "VERIFICATION FAILED")

print("\n== D2b: does verify_ledger notice that triggers were left DISABLED by the operator? ==")
import subprocess as _s
def _psql(q): return _s.run(["docker","compose","exec","-T","db","psql","-U","sahakar","-d","sahakar_audit_test","-At","-c",q],capture_output=True,text=True,cwd=ROOT)
dis = _psql("select c.relname||'.'||t.tgname from pg_trigger t join pg_class c on c.oid=t.tgrelid where not t.tgisinternal and t.tgenabled='D'").stdout.split()
with Session(eng) as db: rep2 = integrity.verify_database(db)
check("verify_ledger / integrity check reports disabled append-only triggers", not dis or not rep2["ok"], f"{len(dis)} triggers left disabled, integrity ok={rep2['ok']} (silent)")
for t in _psql("select distinct c.relname from pg_trigger t join pg_class c on c.oid=t.tgrelid where not t.tgisinternal and t.tgenabled='D'").stdout.split():
    assert _psql(f"ALTER TABLE {t} ENABLE TRIGGER USER").returncode == 0
print("   triggers restored for the privilege tests")

print("\n== D3: who can do this? database privileges ==")
for role, pw in (("sahakar_test", "sahakar_test"),):
    e2 = create_engine(f"postgresql+psycopg://{role}:{pw}@localhost:55432/sahakar_audit_test")
    err = db_error("ALTER TABLE financial_events DISABLE TRIGGER USER", engine=e2, rollback=True); print(f"   app/owner role '{role}': ALTER TABLE … DISABLE TRIGGER ->", "denied: " + err if err else "ALLOWED")
    check("FINDING: the runtime DB role owns the tables and can disable the append-only triggers", err is not None, "allowed" if err is None else err)
    err = db_error("SET session_replication_role = replica", engine=e2, rollback=True); print("   SET session_replication_role=replica ->", "denied" if err else "ALLOWED")
sp = subprocess.run(["docker","compose","exec","-T","db","psql","-U","sahakar","-d","sahakar_audit_test","-At","-c","select rolsuper from pg_roles where rolname='sahakar'"],capture_output=True,text=True,cwd=ROOT).stdout.strip()
print("   Docker superuser 'sahakar' rolsuper =", sp)
print("   Mitigation test: a least-privilege runtime role that does not own the tables")
sql = """
DROP ROLE IF EXISTS audit_runtime;
CREATE ROLE audit_runtime LOGIN PASSWORD 'audit_runtime';
GRANT CONNECT ON DATABASE sahakar_audit_test TO audit_runtime;
GRANT USAGE ON SCHEMA public TO audit_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO audit_runtime;
"""
subprocess.run(["docker","compose","exec","-T","db","psql","-U","sahakar","-d","sahakar_audit_test","-v","ON_ERROR_STOP=1","-c",sql],capture_output=True,text=True,cwd=ROOT)
e3 = create_engine("postgresql+psycopg://audit_runtime:audit_runtime@localhost:55432/sahakar_audit_test")
for label, q in (("DISABLE TRIGGER", "ALTER TABLE financial_events DISABLE TRIGGER USER"), ("session_replication_role", "SET session_replication_role = replica"),
                 ("UPDATE event (trigger active)", "UPDATE financial_events SET payload_canonical='{}' WHERE id=(select id from financial_events order by sequence limit 1)"), ("DROP TRIGGER", "DROP TRIGGER trg_financial_events_append_only ON financial_events")):
    err = db_error(q, engine=e3, rollback=True); check(f"least-privilege role cannot: {label}", err is not None, (err or "ALLOWED")[:90])
subprocess.run(["docker","compose","exec","-T","db","psql","-U","sahakar","-d","sahakar_audit_test","-c","REASSIGN OWNED BY audit_runtime TO sahakar_test; DROP OWNED BY audit_runtime; DROP ROLE audit_runtime;"],capture_output=True,text=True,cwd=ROOT)
ok = sum(1 for r in RESULTS if r[1]); print(f"\n{ok}/{len(RESULTS)} observations as expected (DEVIATION lines are findings)"); save("audit1b_results.json", RESULTS)
