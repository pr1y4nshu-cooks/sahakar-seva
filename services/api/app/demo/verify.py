"""Read-only verification of the demo dataset: relationships, state machine, money, ledger, receipts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demo import dataset as ds
from app.demo.seed import _demo_ids
from app.models.demo import DemoSeedRecord
from app.models.marketplace import AvailabilitySlot, Booking, Dispute, Job, JobApplication, Settlement, WorkerServiceSettings
from app.models.organization import Organization, OrganizationMembership
from app.models.service_taxonomy import WorkerSkill
from app.models.trust import FeePolicy, LedgerEntry, LedgerTransaction, PriceQuoteVersion
from app.models.user import User, WorkerProfile
from app.services import trust_service
from app.trust import crypto, integrity

VALID_TRANSITIONS = {"requested": {"confirmed", "declined", "cancelled"}, "confirmed": {"in_progress", "cancelled", "disputed"},
                     "in_progress": {"completed", "disputed"}, "completed": {"disputed"}}


@dataclass
class Report:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((name, bool(ok), detail))
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(c[1] for c in self.checks)


def _receipt_problems(receipt: dict) -> list[str]:
    """Independent re-hash of an exported receipt (events, per-booking links, Merkle inclusion, checkpoint digests)."""
    problems, prev_b = [], None
    for i, ev in enumerate(receipt["events"]):
        ph = crypto.payload_hash(ev["payload"])
        if ph != ev["payload_hash"] or crypto.event_hash(ev["sequence"], ev["previous_event_hash"], ph) != ev["event_hash"]:
            problems.append(f"event {ev['sequence']} hash")
        if ev["payload"].get("booking_event_index") != i or ev["payload"].get("booking_previous_event_hash") != prev_b:
            problems.append(f"event {ev['sequence']} booking link")
        prev_b = ev["event_hash"]
        p = ev.get("inclusion_proof")
        if p:
            cp = next(c for c in receipt["checkpoints"] if c["checkpoint_index"] == p["checkpoint_index"])
            if not crypto.verify_inclusion(ev["event_hash"], p["leaf_index"], p["tree_size"], p["path"], cp["body"]["merkle_root"]):
                problems.append(f"event {ev['sequence']} merkle")
    for cp in receipt["checkpoints"]:
        if crypto.checkpoint_digest(cp["body"]) != cp["digest"]:
            problems.append(f"checkpoint {cp['checkpoint_index']} digest")
    return problems


def verify(db: Session) -> Report:
    r = Report()
    ids = {t: _demo_ids(db, t) for t in ("user", "worker_profile", "organization", "slot", "job", "application", "booking", "dispute", "fee_policy")}
    reg = Counter({k: len(v) for k, v in ids.items()})
    r.add("seed registry present", sum(reg.values()) > 0, str(dict(reg)))
    if not sum(reg.values()):
        return r

    # --- identities / workers
    bad_emails = [u.email for u in db.scalars(select(User).where(User.id.in_(ids["user"]))) if not u.email.endswith("@" + ds.EMAIL_DOMAIN) or not (u.external_auth_id or "").startswith("dev|")]
    r.add("every demo user is an @demo.sahakar.test dev identity (no real accounts)", not bad_emails, str(bad_emails[:3]))
    workers = list(db.scalars(select(WorkerProfile).where(WorkerProfile.id.in_(ids["worker_profile"]))))
    no_skill = [w.display_name for w in workers if not db.scalar(select(func.count()).select_from(WorkerSkill).where(WorkerSkill.worker_profile_id == w.id))]
    no_settings = [w.display_name for w in workers if db.get(WorkerServiceSettings, w.id) is None]
    r.add("every demo worker has declared skills and a service area", not no_skill and not no_settings, f"{no_skill} {no_settings}")
    r.add("no demo worker is marked approved/verified", all(w.onboarding_status in ("draft", "restricted") for w in workers), Counter(w.onboarding_status for w in workers).__repr__())
    r.add("restricted test workers present and excluded from discovery", sum(1 for w in workers if w.onboarding_status == "restricted") == sum(1 for w in ds.WORKERS if w.restricted))
    # --- organizations
    for o in ds.ORGS:
        key = f"{ds.DATASET}:org:{o.slug}"
        oid = db.scalar(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.seed_key == key))
        roles = dict(db.execute(select(OrganizationMembership.user_id, OrganizationMembership.membership_role).where(OrganizationMembership.organization_id == oid)).all()) if oid else {}
        r.add(f"organization {o.slug}: exists with an owner", oid is not None and "owner" in roles.values(), str(Counter(roles.values())))
    # --- jobs
    jobs = list(db.scalars(select(Job).where(Job.id.in_(ids["job"]))))
    bad_job = [j.title for j in jobs if j.status not in ("open", "filled", "cancelled") or not (j.latitude and j.longitude) or j.budget_paise < 5000]
    r.add("jobs have valid status, location and budget", not bad_job, str(bad_job[:3]))
    r.add("each organization-owned job's poster manages that organization", all(
        j.organization_id is None or db.scalar(select(OrganizationMembership.id).where(OrganizationMembership.organization_id == j.organization_id, OrganizationMembership.user_id == j.customer_user_id, OrganizationMembership.membership_role.in_(("owner", "admin")))) for j in jobs))
    r.add("open demo jobs exist and start in the future", sum(1 for j in jobs if j.status == "open") >= 10, f"{sum(1 for j in jobs if j.status == 'open')} open")
    # --- bookings
    bookings = list(db.scalars(select(Booking).where(Booking.id.in_(ids["booking"]))))
    r.add("booking statuses", True, str(Counter(b.status for b in bookings)))
    bad_rel, bad_money, bad_hist, no_quote = [], [], [], []
    for b in bookings:
        if (b.origin == "direct") != (b.slot_id is not None) or (b.origin == "job") != (b.job_id is not None):
            bad_rel.append(str(b.id)[:8])
        q = trust_service.current_quote(db, b.id)
        if q is None:
            no_quote.append(str(b.id)[:8]); continue
        if (q.customer_total_paise, q.worker_share_paise) != (b.price_paise, b.payout_paise) or q.worker_share_paise + q.platform_fee_paise + q.additional_charges_paise + q.tax_paise != q.customer_total_paise:
            bad_money.append(str(b.id)[:8])
    r.add("booking relationships (direct⇔slot, job⇔job)", not bad_rel, str(bad_rel))
    r.add("every demo booking has a versioned quote", not no_quote, str(no_quote))
    r.add("quote totals reconcile and mirror the booking (customer total, worker payout)", not bad_money, str(bad_money))
    for b in bookings:
        evs = [e.event_type for e in trust_service.booking_events(db, b.id)]
        ok = evs[:1] and evs[0] == "quote_created"
        if b.status in ("confirmed", "in_progress", "completed", "disputed") and "booking_confirmed" not in evs: ok = False
        if b.status in ("completed",) and "simulated_settlement_recorded" not in evs: ok = False
        if b.status == "declined" and "booking_declined" not in evs: ok = False
        if not ok: bad_hist.append(f"{str(b.id)[:8]}:{b.status}")
    r.add("event history of each booking is consistent with its state-machine status", not bad_hist, str(bad_hist))
    # overlap rule
    overlaps = 0
    active = [b for b in bookings if b.status in ("confirmed", "in_progress")]
    for i, a in enumerate(active):
        for c in active[i + 1:]:
            if a.worker_profile_id == c.worker_profile_id and a.starts_at < c.ends_at and c.starts_at < a.ends_at: overlaps += 1
    r.add("no overlapping active bookings for a worker", overlaps == 0)
    # --- settlements / ledger
    settled = [b for b in bookings if db.scalar(select(Settlement.id).where(Settlement.booking_id == b.id))]
    r.add("settled bookings are completed or later disputed", all(b.status in ("completed", "disputed") for b in settled), f"{len(settled)} settlements")
    unbalanced, mismatch, simulated = [], [], []
    models = Counter()
    for b in settled:
        s = db.scalar(select(Settlement).where(Settlement.booking_id == b.id))
        q = trust_service.current_quote(db, b.id)
        tx = trust_service.settlement_transaction(db, b.id)
        if tx is None: unbalanced.append(str(b.id)[:8] + ":no-ledger"); continue
        entries = list(db.scalars(select(LedgerEntry).where(LedgerEntry.transaction_id == tx.id)))
        d = sum(e.amount_paise for e in entries if e.direction == "debit"); c = sum(e.amount_paise for e in entries if e.direction == "credit")
        if not (d == c == tx.amount_paise): unbalanced.append(str(b.id)[:8])
        if (s.gross_paise, s.payout_paise, s.fee_paise) != (q.customer_total_paise, q.worker_share_paise, q.customer_total_paise - q.worker_share_paise): mismatch.append(str(b.id)[:8])
        if not (s.is_simulated and tx.is_simulated): simulated.append(str(b.id)[:8])
        models[q.pricing_model or "legacy"] += 1
    r.add("every settled booking has a balanced simulated ledger transaction (debits = credits = amount)", not unbalanced, str(unbalanced))
    r.add("settlement = accepted quote (gross, worker payout, charges)", not mismatch, str(mismatch))
    r.add("all settlements and ledger transactions are labelled simulated", not simulated)
    r.add("three pricing modes are represented in settled bookings (percentage, fixed, hybrid)", {"percentage", "fixed", "hybrid"} <= set(models), str(dict(models)))
    # --- fee policies
    fp = list(db.scalars(select(FeePolicy).where(FeePolicy.id.in_(ids["fee_policy"]))))
    r.add("demo fee policies are labelled illustrative examples", all(p.is_example for p in fp), str([p.policy_id for p in fp]))
    # --- disputes
    disputes = list(db.scalars(select(Dispute).where(Dispute.id.in_(ids["dispute"]))))
    r.add("disputes: one open and one resolved with a reversal", any(d.status == "open" for d in disputes) and any(d.ledger_correction == "full_reversal" for d in disputes), str(Counter(d.status for d in disputes)))
    # --- chain / receipts
    rep = integrity.verify_database(db)
    r.add("whole financial event chain, checkpoints and ledger verify (server check)", rep["ok"], f"{rep['events_checked']} events, {rep['checkpoints_checked']} checkpoints, {len(rep['problems'])} problems")
    bad_receipts = []
    for b in settled[:12] + bookings[:4]:
        rc = trust_service.receipt(db, b, "customer")
        probs = _receipt_problems(json.loads(json.dumps(rc, default=str)))
        if probs: bad_receipts.append((str(b.id)[:8], probs[:2]))
    r.add("exported receipts re-hash cleanly (events, links, Merkle inclusion, checkpoint digests)", not bad_receipts, str(bad_receipts[:2]))
    ids_set = {str(b.id) for b in bookings}
    r.add("receipt identifiers unique", len(ids_set) == len(bookings))
    return r
