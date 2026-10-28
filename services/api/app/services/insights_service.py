"""Retention and revenue views built on recorded data: repeat booking, organization spending reports,
and the internal unit-economics summary. Every figure here is computed from persisted rows; nothing is
estimated or invented. Scenario inputs (CAC, leakage, ...) live only in the browser calculator.
"""

from __future__ import annotations

import csv
import io
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, forbidden, not_found
from app.models.marketplace import Booking, Job, Settlement
from app.models.organization import Organization
from app.models.service_taxonomy import Skill
from app.models.trust import LedgerEntry, LedgerTransaction
from app.models.user import User, WorkerProfile
from app.repositories import marketplace_repository as mrepo
from app.services import fee_policy_service as fps
from app.services import trust_service as trust
from app.services.dispute_service import is_reviewer
from app.services.marketplace_common import managed_organization_ids, price_for_slot, verification_label
from app.services.worker_setup_service import skill_dict

SIMULATED_NOTE = "Simulated settlements only. These are recorded agreement values, not cash revenue or real payouts."


# --- repeat booking ------------------------------------------------------------------------


def repeat_options(db: Session, user: User, booking_id: UUID) -> dict:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.customer_user_id != user.id:
        raise not_found("Booking not found.")
    worker = db.get(WorkerProfile, booking.worker_profile_id)
    settings = mrepo.get_service_settings(db, worker.id)
    eligible = booking.status == "completed" and worker.onboarding_status != "restricted" and settings is not None
    slots = []
    policy = fps.active_policy(db)
    if eligible:
        for s in mrepo.free_slots_for_workers(db, [worker.id], None, None):
            service = price_for_slot(settings.hourly_rate_paise, s["starts_at"], s["ends_at"])
            try:
                ev = fps.evaluate(policy, service, "direct", False) if policy else None
            except ApiError:
                ev = None
            slots.append({
                "id": s["id"], "starts_at": s["starts_at"], "ends_at": s["ends_at"], "price_paise": service,
                "service_price_paise": service,
                "customer_total_paise": ev["customer_total_paise"] if ev else None,
                "worker_payout_paise": ev["worker_payout_paise"] if ev else None,
            })
    skill = db.get(Skill, booking.skill_id)
    return {
        "previous_booking_id": booking.id,
        "eligible": eligible,
        "reason": None if eligible else "Repeat booking is available after a completed booking with an active worker.",
        "worker_profile_id": worker.id,
        "worker_display_name": worker.display_name,
        "worker_verification_label": verification_label(worker.onboarding_status),
        "current_hourly_rate_paise": settings.hourly_rate_paise if settings else None,
        "skill": skill_dict(skill),
        "locality": booking.locality,
        "address_details": booking.address_details,  # the customer's own address from their own booking
        "available_slots": slots,
        "fee_policy": fps.policy_view(policy) if policy else None,
        "terms": (
            "A repeat request is a new booking at the worker's current rate under the fee policy active now. "
            "The worker must accept it. Your earlier booking is not changed."
        ),
    }


# --- organization reporting ----------------------------------------------------------------


def _require_org_manager(db: Session, user: User, organization_id: UUID) -> Organization:
    org = db.get(Organization, organization_id)
    # Members and outsiders get the same 404 so organization existence does not leak.
    if org is None or organization_id not in managed_organization_ids(db, user.id):
        raise not_found("Organization not found.")
    return org


def _org_booking_rows(db: Session, organization_id: UUID) -> list[tuple[Booking, Job, Settlement | None]]:
    rows = db.execute(
        select(Booking, Job, Settlement)
        .join(Job, Job.id == Booking.job_id)
        .outerjoin(Settlement, Settlement.booking_id == Booking.id)
        .where(Job.organization_id == organization_id)
        .order_by(Booking.starts_at.desc())
    ).all()
    return [(b, j, s) for b, j, s in rows]


def organization_summary(db: Session, user: User, organization_id: UUID) -> dict:
    org = _require_org_manager(db, user, organization_id)
    jobs_posted = db.scalar(select(func.count()).select_from(Job).where(Job.organization_id == organization_id)) or 0
    rows = _org_booking_rows(db, organization_id)
    completed = [(b, j, s) for b, j, s in rows if s is not None]
    items = []
    for b, j, s in rows:
        tx = trust.settlement_transaction(db, b.id)
        reversed_ = bool(tx and trust.reversal_of(db, tx.id))
        q = trust.agreement_summary(db, b)
        items.append({
            "booking_id": b.id, "job_id": j.id, "job_title": j.title, "skill_name": db.get(Skill, b.skill_id).name,
            "starts_at": b.starts_at, "status": b.status,
            "worker_display_name": db.get(WorkerProfile, b.worker_profile_id).display_name,
            "quote_version": q["quote_version"], "evidence_level": q["evidence_level"],
            "customer_total_paise": q["customer_total_paise"], "platform_fee_paise": q["platform_fee_paise"],
            "worker_share_paise": q["worker_share_paise"],
            "simulated_settlement": s is not None, "ledger_reversed": reversed_,
        })
    return {
        "organization_id": org.id,
        "organization_name": org.name,
        "organization_type": org.organization_type,
        "jobs_posted": jobs_posted,
        "bookings_created": len(rows),
        "completed_bookings": len(completed),
        "agreed_spend_completed_paise": sum(s.gross_paise for _, _, s in completed),
        "platform_fees_completed_paise": sum(s.fee_paise for _, _, s in completed),
        "agreed_spend_open_paise": sum(b.price_paise for b, _, s in rows if s is None and b.status in ("requested", "confirmed", "in_progress")),
        "bookings": items,
        "note": SIMULATED_NOTE,
        "scope_note": "Only bookings created from this organization's own job posts are included.",
    }


def organization_csv(db: Session, user: User, organization_id: UUID) -> str:
    summary = organization_summary(db, user, organization_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["# " + SIMULATED_NOTE])
    writer.writerow(["booking_id", "job_title", "skill", "starts_at", "status", "worker", "quote_version",
                     "evidence_level", "customer_total_inr", "platform_fee_inr", "worker_share_inr",
                     "simulated_settlement", "ledger_reversed"])
    for r in summary["bookings"]:
        writer.writerow([
            r["booking_id"], _csv_safe(r["job_title"]), r["skill_name"], r["starts_at"].isoformat(), r["status"],
            _csv_safe(r["worker_display_name"]), r["quote_version"] or "", r["evidence_level"],
            f"{r['customer_total_paise'] / 100:.2f}", f"{r['platform_fee_paise'] / 100:.2f}",
            f"{r['worker_share_paise'] / 100:.2f}", r["simulated_settlement"], r["ledger_reversed"],
        ])
    return buf.getvalue()


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection in user-controlled text."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


# --- internal unit economics ---------------------------------------------------------------


def economics_summary(db: Session, user: User) -> dict:
    if not is_reviewer(db, user):
        raise forbidden("Recorded platform totals are visible to platform staff (dispute reviewers) only.")
    count, gross, fee, payout = db.execute(
        select(func.count(Settlement.id), func.coalesce(func.sum(Settlement.gross_paise), 0),
               func.coalesce(func.sum(Settlement.fee_paise), 0), func.coalesce(func.sum(Settlement.payout_paise), 0))
    ).one()
    reversed_count, reversed_amount = db.execute(
        select(func.count(LedgerTransaction.id), func.coalesce(func.sum(LedgerTransaction.amount_paise), 0))
        .where(LedgerTransaction.transaction_type == "simulated_settlement_reversal")
    ).one()
    ledger_count = db.scalar(
        select(func.count(LedgerTransaction.id)).where(LedgerTransaction.transaction_type == "simulated_booking_settlement")
    ) or 0
    platform_fee_alloc = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .where(LedgerTransaction.transaction_type == "simulated_booking_settlement",
               LedgerEntry.account_code == "simulated_platform_fee_allocation")
    ) or 0
    processing_alloc = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .where(LedgerTransaction.transaction_type == "simulated_booking_settlement",
               LedgerEntry.account_code == "simulated_processing_charge_allocation")
    ) or 0
    legacy_fee = db.scalar(
        select(func.coalesce(func.sum(Settlement.fee_paise), 0)).where(
            ~select(LedgerTransaction.id).where(LedgerTransaction.settlement_id == Settlement.id).exists())
    ) or 0
    policy = fps.active_policy(db)
    return {
        "source": "Persisted local demo records (simulated settlements).",
        "completed_bookings": count,
        "total_booking_value_paise": int(gross),
        "total_simulated_platform_fees_paise": int(platform_fee_alloc) + int(legacy_fee),
        "total_party_borne_charges_paise": int(fee),
        "ledger_platform_fee_allocations_paise": int(platform_fee_alloc),
        "ledger_processing_charge_allocations_paise": int(processing_alloc),
        "total_simulated_worker_payouts_paise": int(payout),
        "average_booking_value_paise": int(gross) // count if count else 0,
        "average_fee_per_booking_paise": int(fee) // count if count else 0,
        "effective_fee_bps": (int(fee) * 10000 // int(gross)) if gross else 0,  # all party-borne charges / customer totals
        "active_policy": {"policy_id": policy.policy_id, "version": policy.version, "label": policy.label,
                          "is_example": policy.is_example, "pricing_model": policy.pricing_model} if policy else None,
        "settlements_with_ledger_evidence": ledger_count,
        "legacy_settlements_without_ledger": count - ledger_count,
        "reversed_settlements": reversed_count,
        "reversed_value_paise": int(reversed_amount),
        "note": SIMULATED_NOTE + " Demo data is created by test scripts and is not market evidence.",
    }
