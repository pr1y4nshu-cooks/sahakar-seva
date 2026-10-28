"""Trust ledger integration tests (isolated TEST_DATABASE_URL; every test rolled back).

Covers transparent pricing, versioned quotes and acceptance, the balanced append-only ledger, the
hash-chained event log, checkpoints, receipts and the independent offline verifier, external-anchor
honesty, disputes with corrections, repeat booking, organization reporting and the public fee policy.
"""

import copy
import importlib.util
import json
import subprocess
import sys
import uuid
from contextlib import nullcontext
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.models.marketplace import Booking, PlatformReviewer, Settlement
from app.models.organization import OrganizationMembership
from app.models.trust import AnchorCheckpoint, FinancialEvent, LedgerEntry, LedgerTransaction, PriceQuoteVersion
from app.models.user import User
from app.services import trust_service
from app.services.marketplace_common import FeeCapExceededError, compute_fee_split
from app.trust import anchoring, crypto, integrity, timestamping
from marketplace_helpers import HSR, Api, api, at  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsa_double import make_tsa  # noqa: E402
from verifier_path import verifier_path  # noqa: E402

VERIFIER = verifier_path()


def _verifier():
    spec = importlib.util.spec_from_file_location("verify_receipt_db", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_receipt = _verifier()


def _uid(db: Session, name: str) -> uuid.UUID:
    return db.scalar(select(User.id).where(User.email == f"{name}@marketplace.test"))


def _grant(db: Session, api: Api, name: str) -> None:
    api.get("/users/me", name)
    db.add(PlatformReviewer(user_id=_uid(db, name), note="test"))
    db.flush()


def _book(api: Api, worker: str, customer: str, rate: int, *, complete: bool = True) -> dict:
    w = api.make_worker(worker, rate_paise=rate)
    b = api.book(customer, w).json()
    assert api.post(f"/bookings/{b['id']}/accept", worker, {"quote_version": 1}).status_code == 200
    if complete:
        api.post(f"/bookings/{b['id']}/start", worker)
        r = api.post(f"/bookings/{b['id']}/complete", customer)
        assert r.status_code == 200, r.text
        return r.json()
    return api.get(f"/bookings/{b['id']}", customer).json()


def _receipt(api: Api, booking_id: str, who: str) -> dict:
    r = api.get(f"/bookings/{booking_id}/receipt", who)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    return r.json()


def _settings(**kw) -> Settings:
    # Tests never use a real TSA: start from "not configured" regardless of the developer's .env.
    base = {**get_settings().model_dump(), "tsa_url": None, "tsa_name": None, "tsa_ca_file": None}
    base.update(kw)
    return Settings(**base)


# --- Slice A: transparent pricing and mutual agreement -----------------------------------------


@pytest.mark.parametrize("rate,total,worker_share,fee", [(25000, 50000, 45000, 5000), (35000, 70000, 63000, 7000)])
def test_both_parties_see_one_identical_agreement(api: Api, rate, total, worker_share, fee) -> None:
    b = _book(api, f"w{rate}", f"c{rate}", rate, complete=False)
    as_customer = api.get(f"/bookings/{b['id']}", f"c{rate}").json()
    as_worker = api.get(f"/bookings/{b['id']}", f"w{rate}").json()
    for view in (as_customer, as_worker):
        a = view["agreement"]
        assert (a["customer_total_paise"], a["worker_share_paise"], a["platform_fee_paise"]) == (total, worker_share, fee)
        assert a["worker_share_paise"] + a["platform_fee_paise"] + a["additional_charges_paise"] + a["tax_paise"] == a["customer_total_paise"]
        assert a["quote_version"] == 1 and a["evidence_level"] == "versioned" and a["taxes_modeled"] is False
        assert view["price"]["price_paise"] == total and a["matches_booking_snapshot"] is True
    keys = ("quote_id", "quote_version", "customer_total_paise", "worker_share_paise", "platform_fee_paise", "fee_bps", "fee_policy_version")
    assert {k: as_customer["agreement"][k] for k in keys} == {k: as_worker["agreement"][k] for k in keys}
    assert as_customer["agreement"]["customer_accepted_at"] and as_worker["agreement"]["worker_accepted_at"]


def test_job_selection_creates_quote_accepted_by_manager_then_worker(api: Api) -> None:
    api.make_worker("jw", slot_hours=None)
    job = api.post_job("jm", budget=70000).json()
    app_ = api.post(f"/jobs/{job['id']}/applications", "jw", {}).json()
    b = api.post(f"/jobs/{job['id']}/applications/{app_['id']}/select", "jm").json()
    assert b["agreement"]["source"] == "job_selection" and b["agreement"]["customer_accepted_at"]
    assert b["agreement"]["awaiting_acceptance_from"] == "worker"
    assert (b["agreement"]["customer_total_paise"], b["agreement"]["platform_fee_paise"]) == (70000, 7000)
    assert api.post(f"/bookings/{b['id']}/accept", "jw", {"quote_version": 1}).json()["status"] == "confirmed"


def test_negative_invalid_and_over_cap_prices_rejected(api: Api, db: Session) -> None:
    with pytest.raises(ApiError):
        compute_fee_split(-100)
    with pytest.raises(FeeCapExceededError):
        compute_fee_split(50000, 1600, 1500)
    b = _book(api, "neg", "negc", 25000, complete=False)
    qid = uuid.UUID(b["agreement"]["quote_id"])
    event_id = db.scalar(select(PriceQuoteVersion.financial_event_id).where(PriceQuoteVersion.id == qid))
    base = dict(booking_id=uuid.UUID(b["id"]), source="revision", pricing_basis="t", currency="INR",
                fee_policy_id="p", fee_policy_version="v", initiated_by_role="customer", financial_event_id=event_id)
    bad_rows = [
        dict(version=7, customer_total_paise=50000, worker_share_paise=46000, platform_fee_paise=5000, fee_bps=1000, fee_cap_bps=1500),  # does not reconcile
        dict(version=8, customer_total_paise=50000, worker_share_paise=55000, platform_fee_paise=-5000, fee_bps=1000, fee_cap_bps=1500),  # negative
        dict(version=9, customer_total_paise=50000, worker_share_paise=40000, platform_fee_paise=10000, fee_bps=2000, fee_cap_bps=1500),  # over cap
    ]
    for row in bad_rows:
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(PriceQuoteVersion(**base, **row))
                db.flush()
    r = api.post(f"/bookings/{b['id']}/quote-revisions", "negc", {"service_price_paise": -5})
    assert r.status_code == 422


def test_revised_quote_needs_renewed_acceptance_and_never_rewrites_history(api: Api, db: Session) -> None:
    w = api.make_worker("rv", rate_paise=25000)
    b = api.book("rvc", w).json()
    r = api.post(f"/bookings/{b['id']}/quote-revisions", "rv", {"service_price_paise": 60000})
    assert r.status_code == 201 and r.json()["agreement"]["quote_version"] == 2
    assert r.json()["agreement"]["awaiting_acceptance_from"] == "customer"
    # The worker cannot confirm before the customer accepts the worker's new price.
    assert api.post(f"/bookings/{b['id']}/accept", "rv", {"quote_version": 2}).json()["error"]["code"] == "QUOTE_NOT_ACCEPTED"
    as_customer = api.get(f"/bookings/{b['id']}", "rvc").json()
    assert "accept_quote" in as_customer["agreement_actions"]
    assert api.post(f"/bookings/{b['id']}/quotes/1/accept", "rvc").json()["error"]["code"] == "QUOTE_VERSION_MISMATCH"
    assert api.post(f"/bookings/{b['id']}/quotes/2/accept", "rvc").status_code == 200
    # Stale or missing version on accept is refused.
    assert api.post(f"/bookings/{b['id']}/accept", "rv", {"quote_version": 1}).json()["error"]["code"] == "QUOTE_VERSION_MISMATCH"
    assert api.post(f"/bookings/{b['id']}/accept", "rv").json()["error"]["code"] == "QUOTE_VERSION_REQUIRED"
    ok = api.post(f"/bookings/{b['id']}/accept", "rv", {"quote_version": 2}).json()
    assert ok["status"] == "confirmed" and ok["agreement"]["customer_total_paise"] == 60000 and ok["agreement"]["worker_share_paise"] == 54000
    # Version 1 is still stored, unchanged.
    versions = list(db.scalars(select(PriceQuoteVersion).where(PriceQuoteVersion.booking_id == uuid.UUID(b["id"])).order_by(PriceQuoteVersion.version)))
    assert [(v.version, v.customer_total_paise) for v in versions] == [(1, 50000), (2, 60000)]
    # After confirmation nobody can change the price: API, quote rows, or booking columns.
    assert api.post(f"/bookings/{b['id']}/quote-revisions", "rvc", {"service_price_paise": 40000}).json()["error"]["code"] == "PRICE_LOCKED"
    with pytest.raises(DBAPIError, match="append-only"):
        with db.begin_nested():
            db.execute(text("UPDATE price_quote_versions SET customer_total_paise = 40000 WHERE id = :id"), {"id": versions[1].id})
    with pytest.raises(DBAPIError, match="cannot be changed"):
        with db.begin_nested():
            db.execute(text("UPDATE bookings SET price_paise = 40000, payout_paise = 36000, fee_paise = 4000 WHERE id = :id"), {"id": b["id"]})
    assert api.post(f"/bookings/{b['id']}/quote-revisions", "stranger", {"service_price_paise": 1000000}).status_code == 404


# --- Slice B: append-only ledger -----------------------------------------------------------------


def test_completion_posts_one_balanced_ledger_transaction(api: Api, db: Session) -> None:
    b = _book(api, "lw", "lc", 25000)
    assert b["status"] == "completed" and b["settlement"]["gross_paise"] == 50000
    ev = b["evidence"]
    assert ev["ledger_status"] == "posted" and ev["ledger_balanced"] is True
    assert ev["payment_evidence_status"] == "SIMULATED"
    record = api.get(f"/bookings/{b['id']}/financial-record", "lw").json()
    [tx] = record["ledger_transactions"]
    assert tx["total_debits_paise"] == tx["total_credits_paise"] == 50000
    assert {(e["account"], e["direction"], e["amount_paise"]) for e in tx["entries"]} == {
        ("simulated_customer_payment_clearing", "debit", 50000),
        ("simulated_worker_entitlement", "credit", 45000),
        ("simulated_platform_fee_allocation", "credit", 5000),
    }
    assert [e["event_type"] for e in record["events"]] == [
        "quote_created", "quote_accepted", "quote_accepted", "booking_confirmed", "booking_completed", "simulated_settlement_recorded"]
    earnings = api.get("/earnings/mine", "lw").json()
    assert earnings["settlements"][0]["ledger_status"] == "posted"
    assert api.get(f"/bookings/{b['id']}/financial-record", "stranger").status_code == 404


def test_no_duplicate_ledger_posting(api: Api, db: Session) -> None:
    b = _book(api, "dw1", "dc1", 25000)
    booking = db.get(Booking, uuid.UUID(b["id"]))
    settlement = db.scalar(select(Settlement).where(Settlement.booking_id == booking.id))
    tx = trust_service.settlement_transaction(db, booking.id)
    customer = db.get(User, booking.customer_user_id)
    assert trust_service.post_settlement(db, booking, settlement, customer).id == tx.id  # idempotent
    assert db.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.booking_id == booking.id)) == 1
    for dup in ({"idempotency_key": tx.idempotency_key, "settlement_id": None}, {"idempotency_key": "other", "settlement_id": settlement.id}):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(LedgerTransaction(booking_id=booking.id, transaction_type="simulated_booking_settlement", currency="INR",
                                         amount_paise=50000, source_event_id=tx.source_event_id, **{**{"settlement_id": settlement.id}, **dup}))
                db.flush()
    assert api.post(f"/bookings/{b['id']}/complete", "dc1").json()["error"]["code"] == "INVALID_TRANSITION"


def test_settlement_and_ledger_are_atomic(api: Api, db: Session, monkeypatch) -> None:
    w = api.make_worker("aw", rate_paise=25000)
    b = api.book("ac", w).json()
    api.post(f"/bookings/{b['id']}/accept", "aw", {"quote_version": 1})
    api.post(f"/bookings/{b['id']}/start", "aw")

    def broken(*a, **k):
        raise ApiError(500, "LEDGER_UNBALANCED", "simulated ledger failure")

    monkeypatch.setattr(trust_service, "post_settlement", broken)
    r = api.post(f"/bookings/{b['id']}/complete", "ac")
    assert r.status_code == 500 and r.json()["error"]["code"] == "LEDGER_UNBALANCED"
    db.rollback()  # what closing the request session does in production
    booking = db.get(Booking, uuid.UUID(b["id"]))
    db.refresh(booking)
    assert booking.status == "in_progress"
    assert db.scalar(select(Settlement).where(Settlement.booking_id == booking.id)) is None
    types = [e.event_type for e in db.scalars(select(FinancialEvent).where(FinancialEvent.booking_id == booking.id))]
    assert "booking_completed" not in types and "simulated_settlement_recorded" not in types
    monkeypatch.undo()
    assert api.post(f"/bookings/{b['id']}/complete", "ac").json()["evidence"]["ledger_status"] == "posted"


def test_finalized_ledger_and_events_cannot_be_edited_or_unbalanced(api: Api, db: Session) -> None:
    b = _book(api, "tw", "tc", 25000)
    tx = trust_service.settlement_transaction(db, uuid.UUID(b["id"]))
    for sql in (
        "UPDATE financial_ledger_entries SET amount_paise = 36000 WHERE transaction_id = :id AND account_code = 'simulated_worker_entitlement'",
        "DELETE FROM financial_ledger_entries WHERE transaction_id = :id",
        "UPDATE financial_ledger_transactions SET amount_paise = 40000 WHERE id = :id",
        "UPDATE financial_events SET payload_canonical = '{}' WHERE booking_id = (SELECT booking_id FROM financial_ledger_transactions WHERE id = :id)",
        "DELETE FROM financial_events WHERE booking_id = (SELECT booking_id FROM financial_ledger_transactions WHERE id = :id)",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            with db.begin_nested():
                db.execute(text(sql), {"id": tx.id})
    # Adding an extra, unbalancing entry is caught by the deferred balance trigger at commit time.
    with pytest.raises(DBAPIError, match="not balanced"):
        with db.begin_nested():
            db.add(LedgerEntry(transaction_id=tx.id, entry_index=9, account_code="simulated_platform_fee_allocation", direction="credit", amount_paise=100))
            db.flush()
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    db.execute(text("SET CONSTRAINTS ALL DEFERRED"))


# --- Slice C: event chain and integrity verification --------------------------------------------


def test_database_chain_verifies_and_detects_tampering(api: Api, db: Session) -> None:
    _book(api, "cw", "cc", 25000)
    _book(api, "cw2", "cc2", 35000)
    cp = anchoring.create_checkpoint(db, _settings())
    assert cp is not None and cp.anchor_status == "LOCAL_ONLY"
    events, checkpoints, txs, settlements = integrity.load_records(db)
    report = integrity.verify_records(events, checkpoints, txs, settlements)
    assert report["ok"], report["problems"]

    def codes(ev=events, cps=checkpoints, t=txs, s=settlements):
        return {p["code"] for p in integrity.verify_records(ev, cps, t, s)["problems"]}

    settle = next(i for i, e in enumerate(events) if e["event_type"] == "simulated_settlement_recorded")
    for field, new in (("customer", '"gross_paise":40000'), ("worker", '"worker_share_paise":36000'), ("fee", '"platform_fee_paise":14000')):
        tampered = copy.deepcopy(events)
        old = {"customer": '"gross_paise":50000', "worker": '"worker_share_paise":45000', "fee": '"platform_fee_paise":5000'}[field]
        assert old in tampered[settle]["payload_canonical"]
        tampered[settle]["payload_canonical"] = tampered[settle]["payload_canonical"].replace(old, new)
        assert "PAYLOAD_HASH_MISMATCH" in codes(ev=tampered), field
    # Removing an intermediate event is detected by the sequence and the checkpoint range.
    removed = events[:2] + events[3:]
    assert {"SEQUENCE_GAP_OR_REORDER", "EVENTS_MISSING_FROM_CHECKPOINT_RANGE"} <= codes(ev=removed)
    # Reordering two events breaks the chain and the Merkle root.
    reordered = events[:1] + [events[2], events[1]] + events[3:]
    assert {"SEQUENCE_GAP_OR_REORDER", "CHAIN_BROKEN"} <= codes(ev=reordered)
    # Fully re-hashing a rewritten history still disagrees with the checkpoint.
    rewritten = copy.deepcopy(events)
    rewritten[settle]["payload_canonical"] = rewritten[settle]["payload_canonical"].replace('"worker_share_paise":45000', '"worker_share_paise":36000')
    prev = crypto.GENESIS_HASH
    for e in rewritten:
        e["payload_hash"] = crypto.payload_hash(json.loads(e["payload_canonical"]))
        e["previous_event_hash"] = prev
        e["event_hash"] = crypto.event_hash(e["sequence"], prev, e["payload_hash"])
        prev = e["event_hash"]
    assert "MERKLE_ROOT_MISMATCH" in codes(ev=rewritten)
    # Ledger rows that differ from the committed event are detected.
    bad_tx = copy.deepcopy(txs)
    bad_tx[0]["entries"][1]["amount_paise"] -= 9000
    assert {"LEDGER_UNBALANCED", "LEDGER_DIFFERS_FROM_COMMITTED_EVENT"} & codes(t=bad_tx)


def test_checkpoint_recomputes_and_body_is_immutable(api: Api, db: Session) -> None:
    _book(api, "kw", "kc", 25000)
    cp = anchoring.create_checkpoint(db, _settings())
    hashes = list(db.scalars(select(FinancialEvent.event_hash).where(FinancialEvent.sequence.between(cp.first_sequence, cp.last_sequence)).order_by(FinancialEvent.sequence)))
    assert len(hashes) == cp.event_count and crypto.merkle_root(hashes) == cp.merkle_root
    body = json.loads(cp.body_canonical)
    assert crypto.checkpoint_digest(body) == cp.digest and body["previous_checkpoint_digest"] == crypto.GENESIS_HASH
    assert anchoring.create_checkpoint(db, _settings()) is None  # nothing new to checkpoint
    _book(api, "kw2", "kc2", 25000)
    cp2 = anchoring.create_checkpoint(db, _settings())
    assert cp2.first_sequence == cp.last_sequence + 1 and json.loads(cp2.body_canonical)["previous_checkpoint_digest"] == cp.digest
    with pytest.raises(DBAPIError, match="immutable"):
        with db.begin_nested():
            db.execute(text("UPDATE anchor_checkpoints SET merkle_root = :r WHERE id = :id"), {"r": "00" * 32, "id": cp.id})
    with pytest.raises(DBAPIError, match="cannot be deleted"):
        with db.begin_nested():
            db.execute(text("DELETE FROM anchor_checkpoints WHERE id = :id"), {"id": cp.id})


# --- Slice D/E: receipts, offline verifier, external anchoring ------------------------------------


def _run_cli(tmp_path: Path, receipt: dict, *args: str) -> tuple[int, dict]:
    path = tmp_path / f"r-{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps(receipt))
    proc = subprocess.run([sys.executable, str(VERIFIER), str(path), "--json", *args], capture_output=True, text=True, timeout=60)
    return proc.returncode, json.loads(proc.stdout)


def _rehash(receipt: dict) -> dict:
    """An attacker who rewrites the receipt and recomputes every hash and cross-reference."""
    prev_booking, renamed = None, {}
    for ev in receipt["events"]:
        data = ev["payload"]["data"]
        if "quote_event_hash" in data:
            data["quote_event_hash"] = renamed.get(data["quote_event_hash"], data["quote_event_hash"])
        ev["payload"]["booking_previous_event_hash"] = prev_booking
        ev["payload_hash"] = crypto.payload_hash(ev["payload"])
        new_hash = crypto.event_hash(ev["sequence"], ev["previous_event_hash"], ev["payload_hash"])
        renamed[ev["event_hash"]] = new_hash
        ev["event_hash"] = prev_booking = new_hash
    return receipt


_FORGED = {50000: 40000, 45000: 36000, 5000: 4000}
_MONEY_KEYS = {"customer_total_paise", "worker_share_paise", "platform_fee_paise", "gross_paise", "amount_paise", "fee_paise", "payout_paise", "service_price_paise", "computed_paise"}


def _forge_amounts(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _MONEY_KEYS and v in _FORGED:
                node[k] = _FORGED[v]
            else:
                _forge_amounts(v)
    elif isinstance(node, list):
        for item in node:
            _forge_amounts(item)


def _hidden_deduction(receipt: dict, *, payload_too: bool) -> dict:
    """Demo 3: the worker is shown a ₹400 total and ₹360 payout while the customer agreed to ₹500."""
    r = copy.deepcopy(receipt)
    r["summary"].update(customer_total_paise=40000, worker_share_paise=36000, platform_fee_paise=4000)
    if payload_too:
        r["summary"]["service_price_paise"] = 40000
        for section in ("agreement", "settlement", "events"):
            _forge_amounts(r[section])
    return r


def test_offline_verifier_accepts_genuine_and_rejects_tampered_receipts(api: Api, db: Session, tmp_path: Path) -> None:
    b = _book(api, "vw", "vc", 25000)
    anchoring.create_checkpoint(db, _settings())
    customer_copy, worker_copy = _receipt(api, b["id"], "vc"), _receipt(api, b["id"], "vw")
    assert customer_copy["events"] == worker_copy["events"] and customer_copy["summary"] == worker_copy["summary"]
    assert customer_copy["summary"]["customer_total_paise"] == 50000 and customer_copy["summary"]["worker_share_paise"] == 45000
    text_dump = json.dumps(customer_copy)
    assert "Example Residency" not in text_dump and "@marketplace.test" not in text_dump and "Two IKEA" not in text_dump
    assert api.get(f"/bookings/{b['id']}/receipt", "stranger").status_code == 404

    code, out = _run_cli(tmp_path, customer_copy)
    assert code == 3 and out["result"] == "LOCAL INTEGRITY VERIFIED" and out["external_timestamp"] == "EXTERNAL EVIDENCE UNAVAILABLE"
    assert out["message"] == "Local integrity verified — independent timestamp not yet available."

    def tampered(mutate) -> dict:
        r = copy.deepcopy(customer_copy)
        mutate(r)
        return r

    settle = next(i for i, e in enumerate(customer_copy["events"]) if e["event_type"] == "simulated_settlement_recorded")
    cases = {
        "customer total": tampered(lambda r: r["summary"].update(customer_total_paise=40000)),
        "worker payout": tampered(lambda r: r["summary"].update(worker_share_paise=36000)),
        "platform fee": tampered(lambda r: r["summary"].update(platform_fee_paise=14000)),
        "booking id": tampered(lambda r: r["summary"].update(booking_id=str(uuid.uuid4()))),
        "quote version": tampered(lambda r: r["summary"].update(quote_version=2)),
        "event hash": tampered(lambda r: r["events"][0].update(event_hash="ab" * 32)),
        "settlement payout in payload": tampered(lambda r: r["events"][settle]["payload"]["data"].update(worker_share_paise=36000)),
        "checkpoint": tampered(lambda r: r["checkpoints"][0]["body"].update(last_sequence=r["checkpoints"][0]["body"]["last_sequence"] + 1)),
        "removed event": tampered(lambda r: r["events"].pop(2)),
        "hidden deduction (display only)": _hidden_deduction(customer_copy, payload_too=False),
        "hidden deduction (payload rehashed)": _rehash(_hidden_deduction(customer_copy, payload_too=True)),
    }
    for name, receipt in cases.items():
        code, out = _run_cli(tmp_path, receipt)
        assert code == 1 and out["result"] == "VERIFICATION FAILED", name
    # The worker's independently held copy exposes a later rewrite even if it is internally consistent.
    rewritten = _rehash(_hidden_deduction(worker_copy, payload_too=True))
    rewritten["checkpoints"] = []
    for ev in rewritten["events"]:
        ev["inclusion_proof"] = None
    assert verify_receipt.verify(rewritten)["result"] == "LOCAL INTEGRITY VERIFIED"  # self-consistent forgery...
    older = tmp_path / "older.json"
    older.write_text(json.dumps(worker_copy))
    code, out = _run_cli(tmp_path, rewritten, "--compare", str(older))
    assert code == 1 and any("history" in f["check"] for f in out["failures"])  # ...caught by the retained copy


@pytest.fixture
def test_tsa(tmp_path_factory):
    return make_tsa(tmp_path_factory.mktemp("tsa-db"), "DBTest")


def _factory(db: Session):
    return lambda: nullcontext(db)


def test_external_anchor_verified_only_with_genuine_evidence(api: Api, db: Session, tmp_path: Path, test_tsa, monkeypatch) -> None:
    b = _book(api, "xw", "xc", 25000)
    settings = _settings(tsa_url="http://tsa.test/", tsa_name="Isolated test TSA", tsa_ca_file=str(test_tsa.ca_pem))
    cp = anchoring.create_checkpoint(db, settings)
    assert cp.anchor_status == "ANCHOR_PENDING"
    monkeypatch.setattr(timestamping, "submit", lambda url, req, timeout=15.0: test_tsa.reply(req.der))
    [result] = anchoring.process_due(_factory(db), settings)
    assert result["status"] == "EXTERNALLY_ANCHORED", result
    db.refresh(cp)
    assert cp.tsa_response_b64 and cp.tsa_gen_time and cp.verified_at
    view = api.get(f"/bookings/{b['id']}", "xc").json()
    assert view["evidence"]["anchor"]["status"] == "EXTERNALLY_ANCHORED"
    receipt = _receipt(api, b["id"], "xw")

    code, out = _run_cli(tmp_path, receipt, "--tsa-ca", str(test_tsa.ca_pem))
    assert code == 0 and out["result"] == "EXTERNALLY TIMESTAMPED AND VERIFIED", out["failures"]
    # Without a trust anchor supplied by the verifying person, external evidence is not claimed.
    code, out = _run_cli(tmp_path, receipt)
    assert code == 3 and out["result"] == "LOCAL INTEGRITY VERIFIED"
    # Under a different (untrusted) anchor the token fails.
    other = make_tsa(tmp_path / "other", "Other")
    code, out = _run_cli(tmp_path, receipt, "--tsa-ca", str(other.ca_pem))
    assert code == 1
    # A token signed by another TSA for the same digest is rejected under the pinned anchor.
    forged = copy.deepcopy(receipt)
    req = timestamping.build_request(forged["checkpoints"][0]["digest"], int(forged["checkpoints"][0]["external_timestamp"]["request_nonce"]))
    forged["checkpoints"][0]["external_timestamp"]["time_stamp_response_der_b64"] = timestamping.b64(other.reply(req.der))
    assert _run_cli(tmp_path, forged, "--tsa-ca", str(test_tsa.ca_pem))[0] == 1
    # Claiming anchoring without a token is a failure, never a pass.
    stripped = copy.deepcopy(receipt)
    stripped["checkpoints"][0]["external_timestamp"] = None
    assert _run_cli(tmp_path, stripped, "--tsa-ca", str(test_tsa.ca_pem))[0] == 1
    # The anchored checkpoint is final.
    with pytest.raises(DBAPIError, match="final"):
        with db.begin_nested():
            db.execute(text("UPDATE anchor_checkpoints SET anchor_status = 'ANCHOR_PENDING' WHERE id = :id"), {"id": cp.id})


def test_unavailable_or_lying_tsa_never_yields_externally_anchored(api: Api, db: Session, test_tsa, tmp_path: Path, monkeypatch) -> None:
    b = _book(api, "uw", "uc", 25000)
    settings = _settings(tsa_url="http://tsa.test/", tsa_ca_file=str(test_tsa.ca_pem), anchor_max_attempts=2, anchor_retry_base_seconds=0)
    cp = anchoring.create_checkpoint(db, settings)

    def down(*a, **k):
        raise timestamping.TimestampError("TSA unreachable: ConnectError")

    monkeypatch.setattr(timestamping, "submit", down)
    # Zero backoff: both attempts run in one cycle; the retry budget is then exhausted.
    assert [r["status"] for r in anchoring.process_due(_factory(db), settings)] == ["ANCHOR_PENDING", "ANCHOR_FAILED"]
    assert anchoring.process_due(_factory(db), settings) == []  # bounded retries
    db.refresh(cp)
    assert cp.anchor_status == "ANCHOR_FAILED" and cp.tsa_response_b64 is None and "unreachable" in cp.last_error
    assert api.get(f"/bookings/{b['id']}", "uc").json()["evidence"]["anchor"]["status"] == "ANCHOR_FAILED"
    # A TSA that answers with a token for a different digest, or signed by an untrusted CA, is PROOF_INVALID.
    assert anchoring.retry_failed(db, settings) == 1
    other = make_tsa(tmp_path / "liar", "Liar")
    monkeypatch.setattr(timestamping, "submit", lambda url, req, timeout=15.0: other.reply(req.der))
    assert anchoring.process_due(_factory(db), settings)[0]["status"] == "PROOF_INVALID"
    db.refresh(cp)
    assert cp.anchor_status == "PROOF_INVALID" and cp.verified_at is None
    receipt = _receipt(api, b["id"], "uc")
    assert receipt["checkpoints"][0]["external_timestamp"] is None
    assert verify_receipt.verify(receipt, str(test_tsa.ca_pem))["result"] == "LOCAL INTEGRITY VERIFIED"
    # With no TSA configured, checkpoints stay LOCAL_ONLY and nothing is submitted.
    assert anchoring.process_due(_factory(db), _settings(tsa_url=None, tsa_ca_file=None)) == []


# --- Slice H: disputes -----------------------------------------------------------------------------


def test_financial_dispute_with_reviewer_reversal_is_traceable(api: Api, db: Session) -> None:
    b = _book(api, "fw", "fc", 25000)
    receipt = _receipt(api, b["id"], "fw")
    settle_hash = receipt["events"][-1]["event_hash"]
    bad = api.post(f"/bookings/{b['id']}/disputes", "fw", {"description": "Payout differs from the agreement", "category": "worker_payout_differs", "receipt_event_hash": "ab" * 32})
    assert bad.status_code == 422
    r = api.post(f"/bookings/{b['id']}/disputes", "fw", {"description": "Payout differs from the agreement", "category": "worker_payout_differs", "receipt_event_hash": settle_hash})
    assert r.status_code == 201
    d = r.json()["dispute"]
    assert d["category"] == "worker_payout_differs" and d["related_quote_version"] == 1 and d["related_ledger_transaction_id"]
    body = {"outcome": "resolved_for_customer", "reason": "Reviewed the receipt and the ledger entries.", "ledger_correction": "full_reversal"}
    _grant(db, api, "fw")
    assert api.post(f"/disputes/{d['id']}/resolve", "fw", body).status_code == 403  # a party never reviews itself
    _grant(db, api, "frev")
    queue = api.get("/disputes/review-queue", "frev").json()
    assert queue[0]["category"] == "worker_payout_differs" and queue[0]["has_simulated_settlement"] is True
    assert api.post(f"/disputes/{d['id']}/resolve", "frev", body).status_code == 200
    record = api.get(f"/bookings/{b['id']}/financial-record", "fc").json()
    assert [t["transaction_type"] for t in record["ledger_transactions"]] == ["simulated_booking_settlement", "simulated_settlement_reversal"]
    original, reversal = record["ledger_transactions"]
    assert all(t["balanced"] for t in record["ledger_transactions"]) and reversal["reverses_transaction_id"] == original["id"]
    assert record["evidence"]["ledger_status"] == "reversed"
    assert record["events"][-2]["event_type"] == "dispute_decision_recorded" and record["events"][-1]["event_type"] == "ledger_reversal_posted"
    assert db.scalar(select(Settlement).where(Settlement.booking_id == uuid.UUID(b["id"]))) is not None  # history kept
    assert verify_receipt.verify(_receipt(api, b["id"], "fc"))["result"] == "LOCAL INTEGRITY VERIFIED"
    assert integrity.verify_database(db)["ok"]
    earnings = api.get("/earnings/mine", "fw").json()
    assert earnings["ledger_totals"]["net_simulated_payout_paise"] == 0 and earnings["settlements"][0]["reversed"] is True


def test_reversal_needs_a_settlement(api: Api, db: Session) -> None:
    b = _book(api, "nw", "nc", 25000, complete=False)
    d = api.post(f"/bookings/{b['id']}/disputes", "nc", {"description": "Worker did not arrive on time"}).json()["dispute"]
    _grant(db, api, "nrev")
    r = api.post(f"/disputes/{d['id']}/resolve", "nrev", {"outcome": "no_fault", "reason": "Both parties agreed to reschedule.", "ledger_correction": "full_reversal"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOTHING_TO_REVERSE"


# --- Slice I: repeat booking -----------------------------------------------------------------------


def test_repeat_booking_creates_a_fresh_booking_needing_worker_consent(api: Api, db: Session) -> None:
    first = _book(api, "pw", "pc", 25000)
    assert "repeat" in first["agreement_actions"]
    # The worker raises their rate; a new free slot is published.
    api.put("/worker-profiles/me/service-settings", "pw", {"locality": "Koramangala", "latitude": 12.9352, "longitude": 77.6245, "radius_km": 5, "hourly_rate_paise": 30000})
    slot = api.post("/worker-profiles/me/availability", "pw", {"starts_at": at(6, 10).isoformat(), "ends_at": at(6, 12).isoformat()}).json()
    options = api.get(f"/bookings/{first['id']}/repeat-options", "pc").json()
    assert options["eligible"] and options["current_hourly_rate_paise"] == 30000
    offered = next(s for s in options["available_slots"] if s["id"] == slot["id"])
    assert offered["price_paise"] == 60000
    assert api.get(f"/bookings/{first['id']}/repeat-options", "pw").status_code == 404  # customers only
    assert api.get(f"/bookings/{first['id']}/repeat-options", "stranger").status_code == 404
    locality, lat, lng = HSR
    body = {"worker_profile_id": first["worker_profile_id"], "slot_id": slot["id"], "skill_id": first["skill"]["id"], "locality": locality,
            "latitude": lat, "longitude": lng, "address_details": options["address_details"], "repeat_of_booking_id": first["id"]}
    assert api.post("/bookings", "stranger", body).status_code == 404  # cannot repeat someone else's booking
    r = api.post("/bookings", "pc", body)
    assert r.status_code == 201, r.text
    again = r.json()
    assert again["id"] != first["id"] and again["status"] == "requested" and again["repeat_of_booking_id"] == first["id"]
    assert again["agreement"]["quote_version"] == 1 and again["agreement"]["customer_total_paise"] == 60000
    assert again["agreement"]["awaiting_acceptance_from"] == "worker"
    unchanged = api.get(f"/bookings/{first['id']}", "pc").json()
    assert unchanged["status"] == "completed" and unchanged["agreement"]["customer_total_paise"] == 50000


# --- Slice I/J: organization reporting, fee policy, economics, public checkpoints ----------------


def test_organization_financial_summary_is_owner_admin_only(api: Api, db: Session) -> None:
    api.make_worker("ow", slot_hours=None)
    org = api.post("/organizations", "oboss", {"name": "Blue Coop", "organization_type": "cooperative"}).json()
    job = api.post_job("oboss", org_id=org["id"], budget=70000).json()
    a = api.post(f"/jobs/{job['id']}/applications", "ow", {}).json()
    b = api.post(f"/jobs/{job['id']}/applications/{a['id']}/select", "oboss").json()
    api.post(f"/bookings/{b['id']}/accept", "ow", {"quote_version": 1})
    api.post(f"/bookings/{b['id']}/start", "ow")
    api.post(f"/bookings/{b['id']}/complete", "oboss")
    api.get("/users/me", "omember")
    db.add(OrganizationMembership(organization_id=uuid.UUID(org["id"]), user_id=_uid(db, "omember"), membership_role="member"))
    db.flush()
    s = api.get(f"/organizations/{org['id']}/financial-summary", "oboss").json()
    assert (s["jobs_posted"], s["bookings_created"], s["completed_bookings"]) == (1, 1, 1)
    assert (s["agreed_spend_completed_paise"], s["platform_fees_completed_paise"]) == (70000, 7000)
    assert "address" not in json.dumps(s).lower()
    for who in ("omember", "ow", "stranger"):
        assert api.get(f"/organizations/{org['id']}/financial-summary", who).status_code == 404
    csv_r = api.get(f"/organizations/{org['id']}/financial-report.csv", "oboss")
    assert csv_r.status_code == 200 and csv_r.headers["content-type"].startswith("text/csv")
    assert "700.00" in csv_r.text and "Simulated" in csv_r.text
    assert api.get(f"/organizations/{org['id']}/financial-report.csv", "omember").status_code == 404


def test_public_fee_policy_reports_the_active_policy_record(api: Api, db: Session) -> None:
    from app.services.fee_policy_service import active_policy

    fp = active_policy(db)
    body = api.get("/fee-policy").json()
    p = body["active_policy"]
    assert (p["policy_id"], p["version"], p["definition_hash"]) == (fp.policy_id, fp.version, fp.definition_hash)
    assert p["is_example"] is True and "NOT final pricing" in p["label"]  # the test fixture is an illustrative example
    assert body["rules"]["payments_mode"] == "simulated"
    assert {e["service_price_paise"] for e in body["examples"]} == {20000, 50000, 200000}


def test_economics_is_staff_only_and_uses_recorded_values(api: Api, db: Session) -> None:
    _book(api, "ew", "ec", 25000)
    assert api.get("/economics/summary", "ec").status_code == 403
    _grant(db, api, "erev")
    e = api.get("/economics/summary", "erev").json()
    gross, fee, n = db.execute(select(func.sum(Settlement.gross_paise), func.sum(Settlement.fee_paise), func.count(Settlement.id))).one()
    assert (e["total_booking_value_paise"], e["total_simulated_platform_fees_paise"], e["completed_bookings"]) == (gross, fee, n)
    assert "not cash revenue" in e["note"]
    assert api.get("/trust/integrity", "ec").status_code == 403
    assert api.get("/trust/integrity", "erev").json()["ok"] is True


def test_public_checkpoints_expose_hashes_only(api: Api, db: Session) -> None:
    _book(api, "hw", "hc", 25000)
    cp = anchoring.create_checkpoint(db, _settings())
    listed = api.get("/trust/checkpoints").json()
    assert listed[0]["digest"] == cp.digest and listed[0]["anchor_status"] == "LOCAL_ONLY"
    one = api.get(f"/trust/checkpoints/{cp.checkpoint_index}").json()
    dump = json.dumps(one)
    assert "booking" not in dump and "@" not in dump and "address" not in dump
    assert api.get("/trust/anchoring").json()["data_sent"].startswith("Only the 32-byte")


def test_legacy_booking_is_labelled_and_not_claimed(api: Api, db: Session) -> None:
    """A pre-0005 style booking (no quote rows) is shown as legacy; completing it later records a
    legacy-snapshot quote without inventing a customer acceptance."""
    w = api.make_worker("gw", rate_paise=25000)
    b = api.book("gc", w).json()
    booking_id = uuid.UUID(b["id"])
    # Simulate a booking created before this migration: same row, no trust rows at all.
    legacy = Booking(**{c.name: getattr(db.get(Booking, booking_id), c.name) for c in Booking.__table__.columns if c.name not in ("id", "created_at", "updated_at")})
    legacy.slot_id = api.post("/worker-profiles/me/availability", "gw", {"starts_at": at(8, 10).isoformat(), "ends_at": at(8, 12).isoformat()}).json()["id"]
    legacy.starts_at, legacy.ends_at = at(8, 10), at(8, 12)
    db.add(legacy)
    db.flush()
    view = api.get(f"/bookings/{legacy.id}", "gc").json()
    assert view["agreement"]["evidence_level"] == "legacy" and "Legacy record" in view["agreement"]["note"]
    assert view["evidence"]["anchor"]["status"] is None
    assert verify_receipt.verify(_receipt(api, str(legacy.id), "gc"))["result"] == "EXTERNAL EVIDENCE UNAVAILABLE"
    accepted = api.post(f"/bookings/{legacy.id}/accept", "gw").json()
    assert accepted["status"] == "confirmed" and accepted["agreement"]["evidence_level"] == "legacy_snapshot"
    assert accepted["agreement"]["customer_accepted_at"] is None and accepted["agreement"]["worker_accepted_at"]


def test_fee_ceiling_check_still_applies_and_price_guard_blocks_confirmed_changes(api: Api, db: Session) -> None:
    w = api.make_worker("cg", rate_paise=25000)
    b = api.book("cgc", w).json()
    # Requested: the price guard allows changes (a revision writes a new quote), but the 20% CHECK still applies.
    with pytest.raises(IntegrityError, match="ck_bookings_fee_ceiling"):
        with db.begin_nested():
            db.execute(text("UPDATE bookings SET fee_bps = 2500 WHERE id = :id"), {"id": b["id"]})
    api.post(f"/bookings/{b['id']}/accept", "cg", {"quote_version": 1})
    with pytest.raises(DBAPIError, match="agreed price of a confirmed booking"):
        with db.begin_nested():
            db.execute(text("UPDATE bookings SET fee_bps = 1200 WHERE id = :id"), {"id": b["id"]})
