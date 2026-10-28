import os, sys, json, subprocess
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "services" / "api"))
os.environ["DATABASE_URL"] = "postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit_test"
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from common import *
from app.trust import integrity
from app.services import trust_service
from app.models.marketplace import Booking
eng = create_engine(AUDIT_DB_URL)
with eng.connect() as c: assert c.execute(text("select current_database()")).scalar() == "sahakar_audit_test"
def psql(q, user="sahakar"):
    return subprocess.run(["docker","compose","exec","-T","db","psql","-U",user,"-d","sahakar_audit_test","-At","-c",q],capture_output=True,text=True,cwd=ROOT)
print("\n== F3: table-owner tampering that touches only a MIRROR row (no event change) ==")
bid = (OUT / "a1_booking_id").read_text()
def probe(label, stmts, tables):
    with eng.connect() as conn:
        t = conn.begin()
        for tb in tables: conn.execute(text(f"ALTER TABLE {tb} DISABLE TRIGGER USER"))
        for q in stmts: conn.execute(text(q), {"b": bid})
        db = Session(bind=conn); rep = integrity.verify_database(db)
        b = db.get(Booking, bid); rc = trust_service.receipt(db, b, "worker"); p = save(f"f3_{label}.json", json.loads(json.dumps(rc, default=str)))
        view = trust_service.agreement_summary(db, b)
        t.rollback()
    o = verify(p, "--tsa-ca", DIGICERT_ROOT)
    return rep, o, view
rep, o, view = probe("quote_row", ["UPDATE price_quote_versions SET customer_total_paise=40000, service_price_paise=40000, worker_share_paise=36000, platform_fee_paise=4000 WHERE booking_id=:b"], ["price_quote_versions"])
check("quote-row-only tamper: server integrity check", not rep["ok"], "DETECTED" if not rep["ok"] else "NOT detected (verify_ledger says OK)")
check("quote-row-only tamper: exported receipt fails offline verification", o["result"] == "VERIFICATION FAILED", o["result"])
rep, o, view = probe("booking_row", ["UPDATE bookings SET price_paise=30000, fee_paise=3000, payout_paise=27000 WHERE id=:b"], ["bookings"])
check("booking-row-only tamper: server integrity check", not rep["ok"], "DETECTED" if not rep["ok"] else "NOT detected (verify_ledger says OK)")
print("      agreement.matches_booking_snapshot ->", view["matches_booking_snapshot"], "(per-booking flag exists but is not part of verify_ledger)")
print("\n== F4: integrity checker robustness on a malformed committed event (rolled back) ==")
with eng.connect() as conn:
    t = conn.begin()
    conn.execute(text("ALTER TABLE financial_events DISABLE TRIGGER USER"))
    conn.execute(text("UPDATE financial_events SET payload_canonical='{}' WHERE event_type='simulated_settlement_recorded' AND booking_id=:b"), {"b": bid})
    try:
        rep = integrity.verify_database(Session(bind=conn)); crashed = None
    except Exception as e: crashed = f"{type(e).__name__}: {e}"
    t.rollback()
check("integrity check reports a malformed event as a problem instead of crashing", crashed is None, crashed or "reported")
ok = sum(1 for r in RESULTS if r[1]); print(f"\n{ok}/{len(RESULTS)}"); save("audit1c_results.json", RESULTS)
