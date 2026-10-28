import os, sys, json, base64, subprocess
sys.path.insert(0, "../../services/api"); os.environ["DATABASE_URL"] = "postgresql+psycopg://sahakar_test:sahakar_test@localhost:55432/sahakar_audit2_test"
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.services import trust_service
from app.models.marketplace import Booking
from app.trust import integrity
eng = create_engine(os.environ["DATABASE_URL"])
with eng.connect() as c:
    assert c.execute(text("select current_database()")).scalar() == "sahakar_audit2_test"
    c.rollback(); t = c.begin()
    c.execute(text("ALTER TABLE anchor_checkpoints DISABLE TRIGGER USER"))
    garbage = base64.b64encode(os.urandom(300)).decode()
    c.execute(text("update anchor_checkpoints set anchor_status='EXTERNALLY_ANCHORED', tsa_response_b64=:g, tsa_gen_time=now(), verified_at=now(), last_error=null where anchor_status<>'EXTERNALLY_ANCHORED'"), {"g": garbage})
    db = Session(bind=c)
    bk = db.query(Booking).join(__import__("app.models.trust", fromlist=["FinancialEvent"]).FinancialEvent, __import__("app.models.trust", fromlist=["FinancialEvent"]).FinancialEvent.booking_id == Booking.id).order_by(Booking.created_at.desc()).first()
    ev = trust_service.evidence_summary(db, bk, None)
    print("API evidence badge when a checkpoint's 'token' is 300 random bytes + operator set status ->", ev["anchor"]["status"], "|", ev["anchor"]["label"])
    rep = integrity.verify_database(db); print("verify_ledger ->", "OK (does not inspect tokens)" if rep["ok"] else rep["problems"][:2])
    rc = trust_service.receipt(db, bk, "worker"); open("/tmp/sahakar-audit/a2_forged_status.json", "w").write(json.dumps(rc, default=str))
    t.rollback()
r = subprocess.run([sys.executable, "../verify_receipt.py", "/tmp/sahakar-audit/a2_forged_status.json", "--tsa-ca", "../../services/api/trust/tsa/digicert-trusted-root-g4.pem"], capture_output=True, text=True)
print("offline verifier ->", r.stdout.splitlines()[0], "| exit", r.returncode)
print([l for l in r.stdout.splitlines() if "checkpoint" in l and ("failed" in l.lower() or "token" in l.lower())][:2])
