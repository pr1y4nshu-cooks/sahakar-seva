"""Configurable fee policies end to end (isolated test DB, rolled back). All policies here are ILLUSTRATIVE
test inputs, not SAHAKAR–SEVA pricing."""

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models.marketplace import Booking
from app.models.organization import OrganizationMembership
from app.models.trust import FeePolicy, FinancialEvent, PriceQuoteVersion
from app.models.user import User
from app.services import fee_policy_service as fps
from app.trust import anchoring, integrity
from marketplace_helpers import HSR, Api, api, at  # noqa: F401
from test_trust_ledger import _grant, _receipt, _settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verifier_path import verifier_path  # noqa: E402

spec = importlib.util.spec_from_file_location("verify_receipt_fp", verifier_path())
verify_receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_receipt)


def _activate(db: Session, components, policy_id="test-policy", ceiling=2000, promotions=(), org=None) -> FeePolicy:
    fp = fps.create_version(db, {"label": f"Test {policy_id} (illustrative)", "is_example": True, "max_total_charge_bps": ceiling,
                                 "components": list(components), "promotions": list(promotions)}, policy_id, organization_id=org)
    return fps.activate(db, fp)


def _done(api: Api, worker: str, customer: str, rate: int) -> dict:
    w = api.make_worker(worker, rate_paise=rate)
    b = api.book(customer, w).json()
    assert api.post(f"/bookings/{b['id']}/accept", worker, {"quote_version": 1}).status_code == 200
    api.post(f"/bookings/{b['id']}/start", worker)
    r = api.post(f"/bookings/{b['id']}/complete", customer)
    assert r.status_code == 200, r.text
    return r.json()


FIXED_CUSTOMER = [{"code": "booking_fee", "kind": "platform_fee", "label": "Booking fee", "bearer": "customer", "fixed_paise": 2500}]


def test_fixed_customer_fee_booking_end_to_end(api: Api, db: Session) -> None:
    _activate(db, FIXED_CUSTOMER)
    b = _done(api, "fx", "fxc", 25000)  # 2 h x 250 = 500 service price
    for who in ("fx", "fxc"):
        a = api.get(f"/bookings/{b['id']}", who).json()["agreement"]
        assert (a["service_price_paise"], a["customer_total_paise"], a["worker_share_paise"], a["platform_fee_paise"]) == (50000, 52500, 50000, 2500)
        assert a["pricing_model"] == "fixed" and a["fee_policy_id"] == "test-policy" and a["line_items"][0]["bearer"] == "customer"
    assert b["settlement"]["gross_paise"] == 52500 and b["settlement"]["payout_paise"] == 50000
    rec = api.get(f"/bookings/{b['id']}/financial-record", "fx").json()
    tx = rec["ledger_transactions"][0]
    assert tx["balanced"] and tx["total_debits_paise"] == 52500
    out = verify_receipt.verify(_receipt(api, b["id"], "fxc"))
    assert out["result"] == "LOCAL INTEGRITY VERIFIED", out["failures"]
    assert integrity.verify_database(db)["ok"]


def test_hybrid_waiver_and_platform_absorbed_charge_verify(api: Api, db: Session) -> None:
    _activate(db, [
        {"code": "platform_service_fee", "kind": "platform_fee", "label": "Service fee", "bearer": "worker", "percent_bps": 500, "fixed_paise": 1000, "max_paise": 4000},
        {"code": "convenience_fee", "kind": "platform_fee", "label": "Convenience fee", "bearer": "customer", "fixed_paise": 1500},
        {"code": "processing", "kind": "processing_charge", "label": "Modeled processing", "bearer": "platform", "percent_bps": 200},
    ], promotions=[{"code": "launch_waiver", "label": "Launch: no convenience fee", "waives": ["convenience_fee"]}])
    b = _done(api, "hy", "hyc", 25000)
    a = b["agreement"]
    assert a["pricing_model"] == "hybrid"
    assert (a["customer_total_paise"], a["worker_share_paise"], a["platform_fee_paise"]) == (50000, 46500, 3500)
    waived = next(l for l in a["line_items"] if l["code"] == "convenience_fee")
    assert waived["amount_paise"] == 0 and waived["computed_paise"] == 1500 and waived["waived_by"] == "launch_waiver"
    tx = api.get(f"/bookings/{b['id']}/financial-record", "hy").json()["ledger_transactions"][0]
    accounts = {(e["account"], e["direction"]): e["amount_paise"] for e in tx["entries"]}
    assert accounts[("simulated_platform_promotion_expense", "debit")] == 1000 and accounts[("simulated_processing_charge_allocation", "credit")] == 1000
    receipt = _receipt(api, b["id"], "hyc")
    assert verify_receipt.verify(receipt)["result"] == "LOCAL INTEGRITY VERIFIED"
    if os.environ.get("WRITE_RECEIPT_FIXTURE"):  # regenerates apps/web/src/fixtures/receipt-hybrid.json
        Path(os.environ["WRITE_RECEIPT_FIXTURE"]).write_text(json.dumps(receipt, indent=2))
    # Tamper: hide the waiver (charge the customer the convenience fee) without touching the totals.
    q = receipt["events"][0]["payload"]["data"]["quote"]
    q["line_items"][1]["amount_paise"] = 1500
    assert verify_receipt.verify(receipt)["result"] == "VERIFICATION FAILED"
    # Tamper: substitute a cheaper-looking policy definition.
    receipt = _receipt(api, b["id"], "hyc")
    receipt["events"][0]["payload"]["data"]["quote"]["policy_definition"]["components"][0]["percent_bps"] = 100
    assert verify_receipt.verify(receipt)["result"] == "VERIFICATION FAILED"


def test_business_borne_fee_uses_organization_terms(api: Api, db: Session) -> None:
    api.make_worker("bw", slot_hours=None)
    org = api.post("/organizations", "bboss", {"name": "Fee Coop", "organization_type": "cooperative"}).json()
    _activate(db, [{"code": "business_tools_fee", "kind": "platform_fee", "label": "Business booking fee", "bearer": "business",
                    "fixed_paise": 4000, "organization_bookings": "only"}], policy_id="org-terms", org=uuid.UUID(org["id"]))
    job = api.post_job("bboss", org_id=org["id"], budget=70000).json()
    a_ = api.post(f"/jobs/{job['id']}/applications", "bw", {}).json()
    b = api.post(f"/jobs/{job['id']}/applications/{a_['id']}/select", "bboss").json()
    a = b["agreement"]
    assert a["fee_policy_id"] == "org-terms" and (a["customer_total_paise"], a["worker_share_paise"]) == (74000, 70000)
    applicable = api.get(f"/fee-policy/applicable?organization_id={org['id']}", "bboss").json()
    assert applicable["policy_id"] == "org-terms" and applicable["applies_because"] == "organization-specific terms"
    assert api.get(f"/fee-policy/applicable?organization_id={org['id']}", "bw").status_code == 404
    assert api.get("/fee-policy").json()["active_policy"]["policy_id"] != "org-terms"  # private terms not public
    api.post(f"/bookings/{b['id']}/accept", "bw", {"quote_version": 1})
    api.post(f"/bookings/{b['id']}/start", "bw")
    done = api.post(f"/bookings/{b['id']}/complete", "bboss").json()
    tx = api.get(f"/bookings/{b['id']}/financial-record", "bboss").json()["ledger_transactions"][0]
    assert {(e["account"], e["amount_paise"]) for e in tx["entries"] if e["direction"] == "debit"} == {
        ("simulated_customer_payment_clearing", 70000), ("simulated_business_payment_clearing", 4000)}
    assert done["settlement"]["gross_paise"] == 74000
    assert verify_receipt.verify(_receipt(api, b["id"], "bw"))["result"] == "LOCAL INTEGRITY VERIFIED"


def test_policy_change_never_reprices_existing_bookings(api: Api, db: Session) -> None:
    w = api.make_worker("pc", rate_paise=25000)
    old = api.book("pcc", w).json()
    assert old["agreement"]["platform_fee_paise"] == 5000  # illustrative example fixture
    new_fp = _activate(db, FIXED_CUSTOMER, policy_id="next-policy")
    assert db.scalar(select(FeePolicy).where(FeePolicy.policy_id == fps.EXAMPLE_POLICY_ID)).status == "retired"
    # Requested booking: keeps its quote, even through acceptance and a revision.
    again = api.get(f"/bookings/{old['id']}", "pcc").json()["agreement"]
    assert (again["fee_policy_id"], again["customer_total_paise"]) == (fps.EXAMPLE_POLICY_ID, 50000)
    rev = api.post(f"/bookings/{old['id']}/quote-revisions", "pc", {"service_price_paise": 60000}).json()["agreement"]
    assert rev["fee_policy_id"] == fps.EXAMPLE_POLICY_ID and rev["platform_fee_paise"] == 6000  # revision keeps the agreed terms
    api.post(f"/bookings/{old['id']}/quotes/2/accept", "pcc")
    confirmed = api.post(f"/bookings/{old['id']}/accept", "pc", {"quote_version": 2}).json()
    assert confirmed["agreement"]["customer_total_paise"] == 60000
    # A new booking uses the newly active policy.
    slot = api.post("/worker-profiles/me/availability", "pc", {"starts_at": at(7, 10).isoformat(), "ends_at": at(7, 12).isoformat()}).json()
    fresh = api.book("pcc2", w, slot_id=slot["id"]).json()["agreement"]
    assert (fresh["fee_policy_id"], fresh["fee_policy_version"], fresh["customer_total_paise"]) == ("next-policy", "1", 52500)
    assert fresh["policy_definition_hash"] == new_fp.definition_hash
    # Activation is in the hash chain.
    ev = db.scalar(select(FinancialEvent).where(FinancialEvent.id == new_fp.activation_event_id))
    assert ev.event_type == "fee_policy_activated" and new_fp.definition_hash in ev.payload_canonical
    history = api.get("/fee-policies").json()
    assert [(h["policy_id"], h["status"]) for h in history][:2] == [("next-policy", "active"), (fps.EXAMPLE_POLICY_ID, "retired")]


def test_policy_rows_are_immutable_and_single_active(api: Api, db: Session) -> None:
    fp = fps.active_policy(db)
    for sql, match in (
        ("UPDATE fee_policies SET definition_canonical = '{}' WHERE id = :id", "immutable"),
        ("UPDATE fee_policies SET status = 'draft', activated_at = NULL WHERE id = :id", "draft -> active"),
        ("DELETE FROM fee_policies WHERE id = :id", "cannot be deleted"),
    ):
        with pytest.raises(DBAPIError, match=match):
            with db.begin_nested():
                db.execute(text(sql), {"id": fp.id})
    draft = fps.create_version(db, {"label": "Another example", "is_example": True, "max_total_charge_bps": 1000, "components": []}, "other")
    with pytest.raises(IntegrityError, match="uq_fee_policies_active_default"):
        with db.begin_nested():
            db.execute(text("UPDATE fee_policies SET status='active', activated_at=now() WHERE id = :id"), {"id": draft.id})
    with pytest.raises(IntegrityError, match="ck_fee_policies_charge_ceiling"):
        with db.begin_nested():
            db.add(FeePolicy(policy_id="x", version=1, scope="default", label="x", is_example=True, pricing_model="fixed",
                             max_total_charge_bps=2500, definition_canonical="{}", definition_hash="0" * 64, status="draft"))
            db.flush()


def test_ceiling_refusal_creates_nothing(api: Api, db: Session) -> None:
    _activate(db, [{"code": "flat", "kind": "platform_fee", "label": "Flat fee", "bearer": "worker", "fixed_paise": 20000}], ceiling=1000)
    w = api.make_worker("cl", rate_paise=25000)
    before = db.scalar(select(func.count()).select_from(Booking))
    r = api.book("clc", w)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CHARGE_CEILING_EXCEEDED"
    assert db.scalar(select(func.count()).select_from(Booking)) == before


def test_no_active_policy_fails_closed(api: Api, db: Session) -> None:
    fp = fps.active_policy(db)
    db.execute(text("UPDATE fee_policies SET status='retired', retired_at=now() WHERE id = :id"), {"id": fp.id})
    w = api.make_worker("na", rate_paise=25000)
    r = api.book("nac", w)
    assert r.status_code == 503 and r.json()["error"]["code"] == "NO_ACTIVE_FEE_POLICY"
    assert api.get("/fee-policy").json()["active_policy"] is None


def test_preview_and_simulator(api: Api, db: Session) -> None:
    p = api.post("/pricing/preview", None, {"service_price_paise": 50000}).json()
    assert p["evaluation"]["customer_total_paise"] == 50000 and p["policy"]["is_example"] is True
    candidate = {"label": "Candidate: ₹20 customer fee (scenario)", "is_example": True, "max_total_charge_bps": 1500,
                 "components": [dict(FIXED_CUSTOMER[0], fixed_paise=2000)]}
    sim = api.post("/pricing/simulate", None, {"definition": candidate, "sample_service_prices_paise": [10000, 50000]}).json()
    # ₹20 on a ₹100 service is 20% > the 15% ceiling: refused, not clamped.
    assert sim["pricing_model"] == "fixed" and sim["samples"]["totals"]["platform_fee_paise"] == 2000
    assert sim["samples"]["totals"]["refused"] == 1 and sim["samples"]["items"][0]["refused"] == "CHARGE_CEILING_EXCEEDED"
    assert api.post("/pricing/simulate", None, {"definition": candidate, "include_recorded_bookings": True}).status_code == 403
    _done(api, "sm", "smc", 25000)
    _grant(db, api, "simrev")
    sim = api.post("/pricing/simulate", "simrev", {"definition": candidate, "include_recorded_bookings": True}).json()
    assert sim["recorded_bookings"]["totals"]["bookings"] >= 1 and "Hypothetical" in sim["recorded_note"]
    bad = api.post("/pricing/simulate", None, {"definition": {**candidate, "max_total_charge_bps": 5000}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_FEE_POLICY"
    assert db.scalar(select(func.count()).select_from(FeePolicy).where(FeePolicy.label.like("Candidate%"))) == 0  # nothing stored


def test_anchoring_and_integrity_cover_policy_events(api: Api, db: Session) -> None:
    _activate(db, FIXED_CUSTOMER, policy_id="anchored-policy")
    _done(api, "an", "anc", 25000)
    cp = anchoring.create_checkpoint(db, _settings())
    assert cp is not None
    report = integrity.verify_database(db)
    assert report["ok"], report["problems"]
    quotes = db.scalars(select(PriceQuoteVersion).where(PriceQuoteVersion.fee_policy_id == "anchored-policy")).all()
    assert quotes and all(json.loads(q.line_items_canonical) for q in quotes)
    _ = User, OrganizationMembership  # imported for type context
