"""Public marketplace overview, public open-jobs board, and the development-only demo guide / showcase.

The overview and board expose only aggregate counts and non-private job fields (no addresses, no user ids).
The guide and showcase receipts exist only when APP_ENV=development AND synthetic seed records exist, and a
showcase receipt can only ever be one of the specific bookings the seeder registered as a showcase.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import not_found
from app.demo import dataset as ds
from app.models.demo import DemoSeedRecord
from app.models.marketplace import Booking, Job, WorkerServiceSettings
from app.models.organization import Organization
from app.models.service_taxonomy import ServiceCategory, Skill, WorkerSkill
from app.models.trust import AnchorCheckpoint
from app.models.user import WorkerProfile
from app.services import trust_service
from app.services.marketplace_common import verification_label
from app.services.worker_setup_service import skill_dict

DEMO_LABEL = "Demo marketplace — sample data"


def is_demo(db: Session, entity_type: str, entity_id: UUID) -> bool:
    return db.scalar(select(DemoSeedRecord.id).where(DemoSeedRecord.entity_type == entity_type, DemoSeedRecord.entity_id == entity_id)) is not None


def demo_ids(db: Session, entity_type: str) -> set[UUID]:
    return set(db.scalars(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.entity_type == entity_type)))


def dataset_present(db: Session) -> bool:
    return db.scalar(select(DemoSeedRecord.id).where(DemoSeedRecord.dataset == ds.DATASET).limit(1)) is not None


def _discoverable_workers(db: Session) -> set[UUID]:
    q = (select(WorkerProfile.id).join(WorkerServiceSettings, WorkerServiceSettings.worker_profile_id == WorkerProfile.id)
         .where(WorkerProfile.onboarding_status != "restricted",
                select(WorkerSkill.id).join(Skill, Skill.id == WorkerSkill.skill_id).join(ServiceCategory, ServiceCategory.id == Skill.category_id)
                .where(WorkerSkill.worker_profile_id == WorkerProfile.id, Skill.is_active, ServiceCategory.is_active).exists()))
    return set(db.scalars(q))


def overview(db: Session) -> dict:
    workers = _discoverable_workers(db)
    demo_workers = workers & demo_ids(db, "worker_profile")
    open_jobs = set(db.scalars(select(Job.id).where(Job.status == "open", Job.starts_at > func.now())))
    demo_jobs = open_jobs & demo_ids(db, "job")
    present = dataset_present(db)
    return {
        "available_workers": len(workers),
        "service_categories": db.scalar(select(func.count()).select_from(ServiceCategory).where(ServiceCategory.is_active)) or 0,
        "skills": db.scalar(select(func.count()).select_from(Skill).where(Skill.is_active)) or 0,
        "open_jobs": len(open_jobs),
        "is_demo_dataset": present,
        "demo_label": DEMO_LABEL if present else None,
        "sample_data_share": {"workers": len(demo_workers), "open_jobs": len(demo_jobs)},
        "default_locality": ds.DEFAULT_SEARCH_LOCALITY if present else None,
        "note": ("Counts shown are the synthetic sample dataset created for a demonstration. They are not platform traction."
                 if present else None),
    }


def open_jobs(db: Session, skill_id: UUID | None, locality: str | None, limit: int = 60, sample_only: bool = False) -> list[dict]:
    q = (select(Job).options(joinedload(Job.skill).joinedload(Skill.category))
         .where(Job.status == "open", Job.starts_at > func.now()).order_by(Job.starts_at).limit(min(limit, 100)))
    if skill_id:
        q = q.where(Job.skill_id == skill_id)
    if locality:
        q = q.where(func.lower(Job.locality) == locality.lower())
    demo = demo_ids(db, "job")
    if sample_only:
        q = q.where(Job.id.in_(demo))
    out = []
    for j in db.scalars(q):
        org = db.scalar(select(Organization.name).where(Organization.id == j.organization_id)) if j.organization_id else None
        out.append({
            "id": j.id, "title": j.title, "description": j.description, "skill": skill_dict(j.skill), "locality": j.locality,
            "starts_at": j.starts_at, "ends_at": j.ends_at, "budget_paise": j.budget_paise, "organization_name": org,
            "is_synthetic_demo": j.id in demo,
        })
    return out


# --- development-only guide ---------------------------------------------------------------------

STEPS = [
    ("Explore workers", "/hire", "Anyone. Default locality is preselected; filter by service."),
    ("View a posted job", "/find-work", "Anyone can browse; sign in as a worker (e.g. ravi) to apply."),
    ("Inspect a completed booking", "/bookings", "Sign in as asha (customer). The ₹500-service booking is completed."),
    ("Compare as worker", "/bookings", "Sign in as ravi (worker): same booking, same quote, same amounts."),
    ("Open Transaction Transparency", "/bookings", "On the booking, press 'Transaction transparency': Agreement, Ledger, Proof, Verification."),
    ("Download and verify the receipt", "/verify", "Download from the booking, then check it here or run scripts/verify_receipt.py."),
    ("Demonstrate tampering", "/demo/tamper", "Edit a copy of a receipt; real verification runs and fails."),
    ("Repeat booking and business reporting", "/organizations", "asha: 'Book again'. meena/vikram: Organizations → Booking and spending records."),
]


def _require_dev(db: Session) -> None:
    if get_settings().app_env.lower() != "development" or not dataset_present(db):
        raise not_found("No demo dataset is available.")


def guide(db: Session) -> dict:
    _require_dev(db)
    show = db.execute(select(DemoSeedRecord.showcase_key, DemoSeedRecord.entity_id).where(DemoSeedRecord.showcase_key.is_not(None))).all()
    # the org/fixed/hybrid showcases are tagged by the seeder on the job bookings
    items = []
    for key, bid in show:
        b = db.get(Booking, bid)
        if b is None:
            continue
        a = trust_service.agreement_summary(db, b)
        ev = trust_service.evidence_summary(db, b, None)
        label, desc = ds.SHOWCASE_LABELS.get(key, (key, ""))
        items.append({
            "key": key, "label": label, "description": desc, "status": b.status, "service": b.skill.name if b.skill else None,
            "locality": b.locality, "pricing_model": a["pricing_model"], "fee_policy_id": a["fee_policy_id"],
            "service_price_paise": a["service_price_paise"], "customer_total_paise": a["customer_total_paise"],
            "worker_payout_paise": a["worker_share_paise"], "platform_charges_paise": a["platform_fee_paise"] + a["additional_charges_paise"],
            "anchor_status": ev["anchor"]["status"], "anchor_label": ev["anchor"]["label"],
        })
    order = list(ds.SHOWCASE_LABELS)
    items.sort(key=lambda i: order.index(i["key"]) if i["key"] in order else 99)
    anchors = db.execute(select(AnchorCheckpoint.anchor_status, func.count()).group_by(AnchorCheckpoint.anchor_status)).all()
    s = get_settings()
    return {
        "enabled": True, "label": DEMO_LABEL, "dataset": ds.DATASET, "dataset_version": ds.DATASET_VERSION,
        "personas": [{"email": ds.email(p.local), "name": p.name, "role": p.role} for p in ds.PERSONAS],
        "steps": [{"title": t, "route": r, "hint": h} for t, r, h in STEPS],
        "showcase": items,
        "external_anchoring": {"tsa_configured": s.tsa_configured, "tsa_name": s.tsa_name if s.tsa_configured else None,
                               "checkpoints_by_status": {k: v for k, v in anchors}},
        "passcode_note": "The demo passcode is DEV_AUTH_PASSCODE in the git-ignored root .env. It is never sent to the browser or printed.",
        "synthetic_note": ds.SYNTHETIC_NOTE,
    }


def showcase_receipt(db: Session, key: str) -> dict:
    _require_dev(db)
    bid = db.scalar(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.showcase_key == key))
    booking = db.get(Booking, bid) if bid else None
    if booking is None:
        raise not_found("Showcase not found.")
    return trust_service.receipt(db, booking, "public_demo")
