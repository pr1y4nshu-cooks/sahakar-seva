"""Worker onboarding: declared skills, service area/rate and availability slots."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, conflict, not_found, unprocessable
from app.models.marketplace import ACTIVE_BOOKING_STATUSES, AvailabilitySlot, Booking, WorkerServiceSettings
from app.models.service_taxonomy import ServiceCategory, Skill, WorkerSkill
from app.models.user import User
from app.repositories import marketplace_repository as mrepo
from app.repositories import service_taxonomy_repository as taxonomy
from app.repositories.exceptions import (
    SkillInactiveError,
    SkillNotFoundError,
    WorkerSkillExistsError,
    WorkerSkillNotFoundError,
)
from app.services.marketplace_common import (
    WORKER_CENTRE_DECIMALS,
    geo_point,
    require_worker_profile,
    round_coord,
    utcnow,
)

WORKER_SKILL_LIMIT = 20
MIN_SLOT = timedelta(minutes=30)
MAX_SLOT = timedelta(hours=12)


def skill_dict(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "category_id": skill.category_id,
        "slug": skill.slug,
        "name": skill.name,
        "description": skill.description,
        "is_active": bool(skill.is_active and skill.category.is_active),
    }


def category_dict(category: ServiceCategory) -> dict:
    return {"id": category.id, "slug": category.slug, "name": category.name, "description": category.description}


# --- skills ----------------------------------------------------------------------------


def list_skills(db: Session, category_id: UUID | None, category_slug: str | None) -> list[dict]:
    if category_slug:
        category = taxonomy.get_category_by_slug(db, category_slug)
        if category is None or not category.is_active:
            raise not_found("Unknown service category.")
        category_id = category.id
    elif category_id is not None:
        category = taxonomy.get_category_by_id(db, category_id)
        if category is None or not category.is_active:
            raise not_found("Unknown service category.")
    return [skill_dict(s) for s in taxonomy.list_active_skills(db, category_id=category_id)]


def _worker_skill_dict(ws: WorkerSkill) -> dict:
    return {
        "skill": skill_dict(ws.skill),
        "category": category_dict(ws.skill.category),
        "declared_at": ws.created_at,
        "is_self_declared": True,
    }


def list_my_skills(db: Session, user: User) -> list[dict]:
    profile = require_worker_profile(db, user)
    return [_worker_skill_dict(ws) for ws in taxonomy.list_worker_skills(db, profile.id)]


def add_my_skill(db: Session, user: User, skill_id: UUID) -> dict:
    profile = require_worker_profile(db, user)
    count = db.scalar(select(func.count()).select_from(WorkerSkill).where(WorkerSkill.worker_profile_id == profile.id))
    if count >= WORKER_SKILL_LIMIT:
        raise unprocessable("WORKER_SKILL_LIMIT", f"A worker may declare at most {WORKER_SKILL_LIMIT} skills.")
    try:
        ws = taxonomy.add_worker_skill(db, profile.id, skill_id)
    except (SkillNotFoundError, SkillInactiveError) as exc:
        raise unprocessable("SKILL_NOT_AVAILABLE", "That skill does not exist or is not currently offered.") from exc
    except WorkerSkillExistsError as exc:
        raise conflict("WORKER_SKILL_EXISTS", "You have already declared this skill.") from exc
    return _worker_skill_dict(ws)


def remove_my_skill(db: Session, user: User, skill_id: UUID) -> None:
    profile = require_worker_profile(db, user)
    try:
        taxonomy.remove_worker_skill(db, profile.id, skill_id)
    except WorkerSkillNotFoundError as exc:
        raise not_found("You have not declared this skill.") from exc


def worker_declares_skill(db: Session, worker_profile_id: UUID, skill_id: UUID) -> bool:
    return (
        db.scalar(
            select(WorkerSkill.id)
            .join(Skill, Skill.id == WorkerSkill.skill_id)
            .join(ServiceCategory, ServiceCategory.id == Skill.category_id)
            .where(
                WorkerSkill.worker_profile_id == worker_profile_id,
                WorkerSkill.skill_id == skill_id,
                Skill.is_active.is_(True),
                ServiceCategory.is_active.is_(True),
            )
        )
        is not None
    )


# --- service settings ------------------------------------------------------------------


def settings_dict(s: WorkerServiceSettings) -> dict:
    return {
        "locality": s.locality,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "radius_km": s.radius_km,
        "hourly_rate_paise": s.hourly_rate_paise,
        "updated_at": s.updated_at,
    }


def get_my_settings(db: Session, user: User) -> dict:
    profile = require_worker_profile(db, user)
    s = mrepo.get_service_settings(db, profile.id)
    if s is None:
        raise not_found("Service area and rate have not been set yet.")
    return settings_dict(s)


def put_my_settings(db: Session, user: User, *, locality: str, latitude: float, longitude: float, radius_km: int, hourly_rate_paise: int) -> dict:
    profile = require_worker_profile(db, user)
    lat = round_coord(latitude, WORKER_CENTRE_DECIMALS)
    lng = round_coord(longitude, WORKER_CENTRE_DECIMALS)
    s = mrepo.get_service_settings(db, profile.id)
    if s is None:
        s = WorkerServiceSettings(worker_profile_id=profile.id)
        db.add(s)
    s.locality = locality
    s.latitude = lat
    s.longitude = lng
    s.radius_km = radius_km
    s.hourly_rate_paise = hourly_rate_paise
    s.service_point = geo_point(lat, lng)
    db.commit()
    db.refresh(s)
    return settings_dict(s)


# --- availability ----------------------------------------------------------------------


def _active_booking_by_slot(db: Session, slot_ids: list[UUID]) -> dict[UUID, str]:
    if not slot_ids:
        return {}
    rows = db.execute(
        select(Booking.slot_id, Booking.status).where(
            Booking.slot_id.in_(slot_ids), Booking.status.in_(("confirmed", "in_progress", "requested"))
        )
    )
    held: dict[UUID, str] = {}
    for slot_id, status in rows:
        # A confirmed/in-progress booking outranks pending requests for display.
        if held.get(slot_id) not in ("confirmed", "in_progress"):
            held[slot_id] = status
    return held


def list_my_slots(db: Session, user: User) -> list[dict]:
    profile = require_worker_profile(db, user)
    slots = list(
        db.scalars(
            select(AvailabilitySlot)
            .where(
                AvailabilitySlot.worker_profile_id == profile.id,
                AvailabilitySlot.is_active.is_(True),
                AvailabilitySlot.ends_at > utcnow() - timedelta(days=1),
            )
            .order_by(AvailabilitySlot.starts_at)
        )
    )
    held = _active_booking_by_slot(db, [s.id for s in slots])
    return [
        {"id": s.id, "starts_at": s.starts_at, "ends_at": s.ends_at, "is_active": s.is_active, "booking_status": held.get(s.id)}
        for s in slots
    ]


def add_my_slot(db: Session, user: User, starts_at, ends_at) -> dict:
    profile = require_worker_profile(db, user)
    if ends_at <= starts_at:
        raise unprocessable("INVALID_TIME_RANGE", "The slot must end after it starts.")
    if not MIN_SLOT <= ends_at - starts_at <= MAX_SLOT:
        raise unprocessable("INVALID_TIME_RANGE", "A slot must be between 30 minutes and 12 hours long.")
    if starts_at <= utcnow():
        raise unprocessable("INVALID_TIME_RANGE", "A slot must start in the future.")
    if mrepo.slot_overlaps_active_slot(db, profile.id, starts_at, ends_at):
        raise conflict("SLOT_OVERLAP", "This slot overlaps one of your existing available slots.")
    slot = AvailabilitySlot(worker_profile_id=profile.id, starts_at=starts_at, ends_at=ends_at, is_active=True)
    try:
        with db.begin_nested():
            db.add(slot)
            db.flush()
        db.commit()
    except IntegrityError as exc:  # exclusion constraint: concurrent overlapping insert
        db.rollback()
        raise conflict("SLOT_OVERLAP", "This slot overlaps one of your existing available slots.") from exc
    db.refresh(slot)
    return {"id": slot.id, "starts_at": slot.starts_at, "ends_at": slot.ends_at, "is_active": True, "booking_status": None}


def remove_my_slot(db: Session, user: User, slot_id: UUID) -> None:
    profile = require_worker_profile(db, user)
    slot = db.get(AvailabilitySlot, slot_id)
    if slot is None or slot.worker_profile_id != profile.id:
        raise not_found("Slot not found.")
    active = db.scalar(
        select(Booking.id).where(Booking.slot_id == slot.id, Booking.status.in_(ACTIVE_BOOKING_STATUSES)).limit(1)
    )
    if active is not None:
        raise conflict("SLOT_IN_USE", "This slot has a pending or confirmed booking. Decline or cancel it first.")
    has_history = db.scalar(select(Booking.id).where(Booking.slot_id == slot.id).limit(1)) is not None
    if has_history:
        slot.is_active = False  # keep the row for booking history (FK RESTRICT)
    else:
        db.delete(slot)
    db.commit()


def ensure_discoverable(db: Session, worker_profile_id: UUID, onboarding_status: str) -> WorkerServiceSettings:
    if onboarding_status == "restricted":
        raise ApiError(422, "WORKER_NOT_ELIGIBLE", "This worker is not currently accepting bookings.")
    s = mrepo.get_service_settings(db, worker_profile_id)
    if s is None:
        raise ApiError(422, "WORKER_NOT_ELIGIBLE", "This worker has not set a service area yet.")
    return s
