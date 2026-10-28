"""Demo seeder tests. They run the seeder against the ISOLATED TEST database inside the rolled-back test
transaction (the permitted way to test it); the seeder's own CLI safety gate is tested separately and refuses
that database by design."""

import io
import json
import subprocess
import sys
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.cli import seed_demo as seed_cli
from app.core.errors import ApiError
from app.demo import dataset as ds
from app.demo import seed as seeder
from app.demo.verify import verify
from app.models.demo import DemoSeedRecord
from app.models.marketplace import Booking, Dispute, Job, JobApplication, Settlement
from app.models.trust import FinancialEvent, LedgerEntry, LedgerTransaction, PriceQuoteVersion
from app.models.user import User, WorkerProfile
from marketplace_helpers import api  # noqa: F401  (fixture: seeds taxonomy + the illustrative default policy)


@pytest.fixture
def seeded(api, db: Session):
    ctx = seeder.run_seed(db)
    return ctx


def counts(db: Session) -> dict[str, int]:
    return {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in (
        "users", "worker_profiles", "organizations", "jobs", "job_applications", "bookings", "settlements", "disputes",
        "financial_events", "price_quote_versions", "financial_ledger_transactions", "financial_ledger_entries", "fee_policies", "demo_seed_records")}


# --- safety --------------------------------------------------------------------------------


@pytest.mark.parametrize("url,env", [
    ("postgresql+psycopg://u:p@db.x.supabase.co:5432/postgres", "development"),
    ("postgresql+psycopg://u:p@aws-0-ap.pooler.supabase.com:6543/postgres", "development"),
    ("postgresql+psycopg://u:p@localhost:55432/sahakar_seva_test", "development"),
    ("postgresql+psycopg://u:p@localhost:55432/some_other_db", "development"),
    ("postgresql+psycopg://u:p@203.0.113.9:5432/sahakar_seva", "development"),
    ("postgresql+psycopg://u:p@db:5432/sahakar_seva", "production"),
    ("postgresql+psycopg://u:p@db:5432/sahakar_seva", "staging"),
    ("sqlite:///demo.db", "development"),
])
def test_seeder_refuses_remote_test_production_and_unknown_databases(url, env) -> None:
    with pytest.raises(seeder.SeedSafetyError):
        seeder.check_safety(url, env)


def test_seeder_accepts_only_the_local_development_database() -> None:
    assert seeder.check_safety("postgresql+psycopg://u:p@db:5432/sahakar_seva", "development").database == "sahakar_seva"
    assert seeder.check_safety("postgresql+psycopg://u:p@localhost:55432/sahakar_seva", "development").host == "localhost"


def test_cli_exits_3_and_writes_nothing_against_the_test_database(monkeypatch, test_database_url) -> None:
    """The real CLI entry point, pointed at the test DB, must refuse before opening a session."""
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "database_url", test_database_url)
    monkeypatch.setattr(config.get_settings(), "app_env", "development")
    out = io.StringIO()
    err = io.StringIO()
    import contextlib
    with contextlib.redirect_stderr(err), redirect_stdout(out):
        code = seed_cli.main(["--apply"])
    assert code == 3 and "REFUSED" in err.getvalue() and "test database" in err.getvalue()


# --- dry run / idempotency -----------------------------------------------------------------


def test_dry_run_plan_performs_no_writes(api, db: Session) -> None:
    before = counts(db)
    lines = seeder.plan(db)
    assert before == counts(db) and any("expected" in l for l in lines)


def test_apply_creates_the_dataset_and_a_rerun_creates_nothing(api, db: Session) -> None:
    ctx = seeder.run_seed(db)
    after_first = counts(db)
    non_demo_after = seeder.non_demo_counts(db)
    assert ctx.created["worker_profile"] == len(ds.WORKERS) and ctx.created["organization"] == len(ds.ORGS)
    second = seeder.run_seed(db)
    assert counts(db) == after_first, {k: (after_first[k], counts(db)[k]) for k in after_first if after_first[k] != counts(db)[k]}
    assert not second.created and seeder.non_demo_counts(db) == non_demo_after
    reg = seeder.registered_counts(db)
    for k, v in seeder.expected_counts().items():
        assert reg[k] == v, (k, reg[k], v)


def test_real_users_and_bookings_are_never_modified(api, db: Session) -> None:
    real = api.make_worker("realworker", rate_paise=21100)
    real_booking = api.book("realcustomer", real).json()
    before = db.execute(text("SELECT price_paise, status FROM bookings WHERE id = :i"), {"i": real_booking["id"]}).one()
    seeder.run_seed(db)
    after = db.execute(text("SELECT price_paise, status FROM bookings WHERE id = :i"), {"i": real_booking["id"]}).one()
    assert before == after
    assert db.scalar(select(func.count()).select_from(DemoSeedRecord).where(DemoSeedRecord.entity_id == real_booking["id"])) == 0
    assert db.scalar(select(User.email).where(User.email == "realworker@marketplace.test")) is not None


# --- dataset shape ---------------------------------------------------------------------------


def test_workers_skills_service_settings_and_labels(seeded, db: Session) -> None:
    profiles = list(db.scalars(select(WorkerProfile).where(WorkerProfile.id.in_(
        select(DemoSeedRecord.entity_id).where(DemoSeedRecord.entity_type == "worker_profile")))))
    assert len(profiles) == len(ds.WORKERS) >= 18
    assert not any(p.onboarding_status == "approved" for p in profiles)           # no invented verification
    assert sum(p.onboarding_status == "restricted" for p in profiles) == 2
    assert len({p.display_name for p in profiles}) == len(profiles)               # distinct profiles
    assert len({p.bio for p in profiles}) == len(profiles)
    assert all(p.user_id and (db.get(User, p.user_id).email.endswith("@demo.sahakar.test")) for p in profiles)


def test_search_returns_seeded_workers_filters_work_and_excludes_restricted(seeded, db: Session, api) -> None:
    cats = {c["slug"]: c["id"] for c in api.get("/service-categories").json()}
    loc = ds.LOCALITY if False else seeder.LOCALITY["Koramangala"]

    def search(**extra):
        r = api.get("/workers/search", params={"latitude": loc.latitude, "longitude": loc.longitude, "radius_km": 10, **extra})
        assert r.status_code == 200, r.text
        return r.json()

    furniture = search(category_id=cats["furniture-assembly"])
    names = {w["display_name"] for w in furniture["results"]}
    assert "Ravi Kumar" in names and "Restricted Test A" not in names and "Restricted Test B" not in names
    assert all(any(s["slug"] in ("desk-assembly", "shelf-assembly") for s in w["skills"]) for w in furniture["results"])
    desk = {w["display_name"] for w in search(skill_id=api.skill_id("desk-assembly"))["results"]}
    shelf = {w["display_name"] for w in search(skill_id=api.skill_id("shelf-assembly"))["results"]}
    assert desk != shelf and "Ravi Kumar" in desk & shelf
    cleaning = {w["display_name"] for w in search(category_id=cats["household-cleaning"])["results"]}
    garden = {w["display_name"] for w in search(category_id=cats["gardening"])["results"]}
    assert cleaning and garden and not (cleaning & garden) and "Lakshmi Devi" in cleaning
    assert all(w["verification_label"].startswith("Not verified") for w in furniture["results"])
    assert any(w["available_slots"] for w in furniture["results"])
    rates = {w["hourly_rate_paise"] for w in furniture["results"]}
    assert len(rates) >= 3                                                           # distinct price points


def test_job_board_returns_open_seeded_jobs_for_a_seeded_worker(seeded, db: Session, api) -> None:
    ravi = seeded.users["ravi"]
    # Use the real API with a test token for the seeded worker's identity.
    from app.core.security import VerifiedUser

    def tok_user(local):
        return f"u:{local}"
    # The test verifier maps u:<name> -> test|<name>; use the service directly for the seeded dev identity.
    from app.services import job_service
    jobs = job_service.nearby_jobs(db, ravi, None, None)
    titles = {j["title"] for j in jobs}
    assert "Assemble a flat-pack wardrobe and desk" in titles and len(jobs) >= 3
    assert all(j["status"] == "open" and j.get("address_details") is None for j in jobs)   # private address never reaches the board
    assert sum(1 for j in db.scalars(select(Job).where(Job.id.in_(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.entity_type == "job")))) if j.status == "open") >= 10


def test_booking_states_state_machine_history_and_no_overlaps(seeded, db: Session) -> None:
    ids = select(DemoSeedRecord.entity_id).where(DemoSeedRecord.entity_type == "booking")
    statuses = Counter(db.scalars(select(Booking.status).where(Booking.id.in_(ids))))
    assert len(statuses) >= 6 and sum(statuses.values()) >= 12
    assert {"requested", "confirmed", "in_progress", "completed", "cancelled", "declined", "disputed"} <= set(statuses)
    report = verify(db)
    failed = [c for c in report.checks if not c[1]]
    assert not failed, failed


def test_pricing_modes_reconcile_with_the_active_policy_at_quote_time(seeded, db: Session) -> None:
    qs = list(db.scalars(select(PriceQuoteVersion).where(PriceQuoteVersion.booking_id.in_(
        select(DemoSeedRecord.entity_id).where(DemoSeedRecord.entity_type == "booking")))))
    by_model = Counter(q.pricing_model for q in qs)
    assert {"percentage", "fixed", "hybrid"} <= set(by_model), by_model
    for q in qs:
        assert q.worker_share_paise + q.platform_fee_paise + q.additional_charges_paise + q.tax_paise == q.customer_total_paise
        assert q.fee_policy_id and q.policy_definition_hash
    headline = db.scalar(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.seed_key == "judge-demo:booking:direct:headline"))
    hq = [q for q in qs if q.booking_id == headline][0]
    assert (hq.service_price_paise, hq.customer_total_paise, hq.worker_share_paise, hq.platform_fee_paise) == (50000, 50000, 45000, 5000)  # example policy: 10% worker-borne
    fixed = [q for q in qs if q.pricing_model == "fixed"][0]
    assert fixed.customer_total_paise == fixed.service_price_paise + 4000 and fixed.worker_share_paise == fixed.service_price_paise
    waived = [q for q in qs if q.pricing_model == "hybrid" and '"waived_by":"coop_launch_waiver"' in q.line_items_canonical]
    unwaived = [q for q in qs if q.pricing_model == "hybrid" and '"waived_by":null' in q.line_items_canonical and "coop_convenience_fee" in q.line_items_canonical]
    assert waived and unwaived


def test_settlements_ledger_and_reversal(seeded, db: Session) -> None:
    ids = select(DemoSeedRecord.entity_id).where(DemoSeedRecord.entity_type == "booking")
    settlements = db.scalars(select(Settlement).where(Settlement.booking_id.in_(ids))).all()
    assert len(settlements) >= 6 and all(s.is_simulated for s in settlements)
    txs = db.scalars(select(LedgerTransaction).where(LedgerTransaction.booking_id.in_(ids))).all()
    for tx in txs:
        entries = db.scalars(select(LedgerEntry).where(LedgerEntry.transaction_id == tx.id)).all()
        assert sum(e.amount_paise for e in entries if e.direction == "debit") == sum(e.amount_paise for e in entries if e.direction == "credit") == tx.amount_paise
    assert any(t.transaction_type == "simulated_settlement_reversal" for t in txs)


def test_provenance_and_synthetic_acceptance_marked(seeded, db: Session) -> None:
    from app.models.marketplace import AuditEvent

    bid = db.scalar(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.seed_key == "judge-demo:booking:direct:headline"))
    ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == bid, AuditEvent.action == "demo_seeded"))
    assert ev.details["synthetic_demo"] is True and "No human accepted" in ev.details["note"]
    types = {t for t in db.scalars(select(DemoSeedRecord.entity_type))}
    assert {"user", "worker_profile", "organization", "job", "booking", "slot", "application", "dispute", "fee_policy"} <= types


def test_no_external_anchoring_is_fabricated_by_the_seeder(seeded, db: Session) -> None:
    from app.models.trust import AnchorCheckpoint

    assert db.scalar(select(func.count()).select_from(AnchorCheckpoint)) == 0   # seeder never creates checkpoints or tokens
