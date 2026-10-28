"""Marketplace queries (PostgreSQL + PostGIS).

All distances use geography (metres). Radii are stored in km and multiplied by 1000; degrees
are never compared with kilometres. Read functions never commit.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Session

from app.models.marketplace import AvailabilitySlot, Booking, Job, WorkerServiceSettings
from app.models.user import WorkerProfile

_POINT = "CAST(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS geography)"

_SEARCH_WORKERS = text(
    f"""
    WITH target AS (SELECT {_POINT} AS pt)
    SELECT wp.id AS worker_profile_id, wp.user_id, wp.display_name, wp.bio, wp.onboarding_status,
           ss.locality, ss.radius_km, ss.hourly_rate_paise,
           ST_Distance(ss.service_point, target.pt) AS distance_m
    FROM worker_profiles wp
    JOIN worker_service_settings ss ON ss.worker_profile_id = wp.id
    CROSS JOIN target
    WHERE wp.onboarding_status <> 'restricted'
      AND ST_DWithin(ss.service_point, target.pt, ss.radius_km * 1000)
      AND ST_DWithin(ss.service_point, target.pt, :search_radius_m)
      AND EXISTS (
          SELECT 1 FROM worker_skills ws
          JOIN skills s ON s.id = ws.skill_id
          JOIN service_categories c ON c.id = s.category_id
          WHERE ws.worker_profile_id = wp.id AND s.is_active AND c.is_active
            AND (CAST(:skill_id AS uuid) IS NULL OR s.id = CAST(:skill_id AS uuid))
            AND (CAST(:category_id AS uuid) IS NULL OR c.id = CAST(:category_id AS uuid)))
      AND (CAST(:exclude_user_id AS uuid) IS NULL OR wp.user_id <> CAST(:exclude_user_id AS uuid))
      AND (NOT CAST(:sample_only AS boolean) OR wp.id IN (SELECT entity_id FROM demo_seed_records WHERE entity_type = 'worker_profile'))
      AND (CAST(:starts_at AS timestamptz) IS NULL OR EXISTS (
          SELECT 1 FROM availability_slots sl
          WHERE sl.worker_profile_id = wp.id AND sl.is_active
            AND sl.starts_at <= CAST(:starts_at AS timestamptz) AND sl.ends_at >= CAST(:ends_at AS timestamptz)
            AND NOT EXISTS (
                SELECT 1 FROM bookings b
                WHERE b.worker_profile_id = wp.id AND b.status IN ('confirmed', 'in_progress')
                  AND tstzrange(b.starts_at, b.ends_at) && tstzrange(sl.starts_at, sl.ends_at))))
    ORDER BY distance_m, wp.display_name
    LIMIT 50
    """
)

_FREE_SLOTS = text(
    """
    SELECT sl.id, sl.worker_profile_id, sl.starts_at, sl.ends_at
    FROM availability_slots sl
    WHERE sl.worker_profile_id = ANY(:ids) AND sl.is_active AND sl.starts_at > now()
      AND (CAST(:starts_at AS timestamptz) IS NULL
           OR (sl.starts_at <= CAST(:starts_at AS timestamptz) AND sl.ends_at >= CAST(:ends_at AS timestamptz)))
      AND NOT EXISTS (
          SELECT 1 FROM bookings b
          WHERE b.worker_profile_id = sl.worker_profile_id AND b.status IN ('confirmed', 'in_progress')
            AND tstzrange(b.starts_at, b.ends_at) && tstzrange(sl.starts_at, sl.ends_at))
    ORDER BY sl.starts_at
    """
).bindparams(bindparam("ids", type_=ARRAY(PGUUID(as_uuid=True))))

_NEARBY_JOBS = text(
    """
    SELECT j.id, ST_Distance(j.job_point, ss.service_point) AS distance_m
    FROM jobs j
    JOIN worker_service_settings ss ON ss.worker_profile_id = :worker_profile_id
    WHERE j.status = 'open' AND j.starts_at > now()
      AND ST_DWithin(j.job_point, ss.service_point, ss.radius_km * 1000)
      AND j.customer_user_id <> :user_id
      AND (CAST(:skill_id AS uuid) IS NULL OR j.skill_id = CAST(:skill_id AS uuid))
      AND (CAST(:locality AS text) IS NULL OR lower(j.locality) = lower(CAST(:locality AS text)))
    ORDER BY j.starts_at
    LIMIT 100
    """
)


def search_workers(
    db: Session,
    *,
    latitude: float,
    longitude: float,
    search_radius_km: float,
    skill_id: UUID | None,
    category_id: UUID | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
    exclude_user_id: UUID | None,
    sample_only: bool = False,
) -> list[dict[str, Any]]:
    rows = db.execute(
        _SEARCH_WORKERS,
        {
            "lat": latitude,
            "lng": longitude,
            "search_radius_m": search_radius_km * 1000.0,
            "skill_id": skill_id,
            "category_id": category_id,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "exclude_user_id": exclude_user_id,
            "sample_only": sample_only,
        },
    ).mappings()
    return [dict(r) for r in rows]


def free_slots_for_workers(
    db: Session, worker_profile_ids: list[UUID], starts_at: datetime | None, ends_at: datetime | None
) -> list[dict[str, Any]]:
    if not worker_profile_ids:
        return []
    rows = db.execute(_FREE_SLOTS, {"ids": worker_profile_ids, "starts_at": starts_at, "ends_at": ends_at}).mappings()
    return [dict(r) for r in rows]


def nearby_open_jobs(
    db: Session, *, worker_profile_id: UUID, user_id: UUID, skill_id: UUID | None, locality: str | None
) -> list[tuple[UUID, float]]:
    rows = db.execute(
        _NEARBY_JOBS,
        {"worker_profile_id": worker_profile_id, "user_id": user_id, "skill_id": skill_id, "locality": locality},
    )
    return [(r.id, float(r.distance_m)) for r in rows]


def point_within_worker_radius(db: Session, worker_profile_id: UUID, latitude: float, longitude: float) -> float | None:
    """Distance in metres if the point lies inside the worker's service radius, else None."""
    row = db.execute(
        text(
            f"SELECT ST_Distance(ss.service_point, {_POINT}) AS d, "
            f"ST_DWithin(ss.service_point, {_POINT}, ss.radius_km * 1000) AS inside "
            "FROM worker_service_settings ss WHERE ss.worker_profile_id = :wp"
        ),
        {"lat": latitude, "lng": longitude, "wp": worker_profile_id},
    ).one_or_none()
    if row is None or not row.inside:
        return None
    return float(row.d)


def job_distance_from_worker(db: Session, job_id: UUID, worker_profile_id: UUID) -> tuple[float, bool] | None:
    row = db.execute(
        text(
            "SELECT ST_Distance(j.job_point, ss.service_point) AS d, "
            "ST_DWithin(j.job_point, ss.service_point, ss.radius_km * 1000) AS inside "
            "FROM jobs j, worker_service_settings ss WHERE j.id = :job AND ss.worker_profile_id = :wp"
        ),
        {"job": job_id, "wp": worker_profile_id},
    ).one_or_none()
    return None if row is None else (float(row.d), bool(row.inside))


def lock_worker_profile(db: Session, worker_profile_id: UUID) -> WorkerProfile | None:
    """Row-lock a worker profile to serialise booking confirmations for that worker."""
    return db.scalar(select(WorkerProfile).where(WorkerProfile.id == worker_profile_id).with_for_update().execution_options(populate_existing=True))


def lock_booking(db: Session, booking_id: UUID) -> Booking | None:
    return db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update().execution_options(populate_existing=True))


def lock_job(db: Session, job_id: UUID) -> Job | None:
    return db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))


def has_active_overlap(db: Session, worker_profile_id: UUID, starts_at: datetime, ends_at: datetime, exclude_booking_id: UUID | None = None) -> bool:
    stmt = select(Booking.id).where(
        Booking.worker_profile_id == worker_profile_id,
        Booking.status.in_(("confirmed", "in_progress")),
        Booking.starts_at < ends_at,
        Booking.ends_at > starts_at,
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
    return db.scalar(stmt.limit(1)) is not None


def slot_overlaps_active_slot(db: Session, worker_profile_id: UUID, starts_at: datetime, ends_at: datetime) -> bool:
    stmt = select(AvailabilitySlot.id).where(
        AvailabilitySlot.worker_profile_id == worker_profile_id,
        AvailabilitySlot.is_active.is_(True),
        AvailabilitySlot.starts_at < ends_at,
        AvailabilitySlot.ends_at > starts_at,
    )
    return db.scalar(stmt.limit(1)) is not None


def get_service_settings(db: Session, worker_profile_id: UUID) -> WorkerServiceSettings | None:
    return db.get(WorkerServiceSettings, worker_profile_id)
