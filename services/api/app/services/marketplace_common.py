"""Shared marketplace helpers: geography, pricing, audit, identity resolution."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.core.config import ABSOLUTE_FEE_CEILING_BPS, get_settings
from app.core.errors import ApiError, unprocessable
from app.core.security import VerifiedUser
from app.models.marketplace import AuditEvent, Geography
from app.models.organization import OrganizationMembership
from app.models.user import User, WorkerProfile
from app.repositories.worker_repository import get_worker_profile_by_user
from app.services.user_service import UserService

WORKER_CENTRE_DECIMALS = 2  # ~1.1 km: protects workers' residential privacy
JOB_POINT_DECIMALS = 3  # ~110 m: enough for radius matching; exact address stays private


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def geo_point(latitude: float, longitude: float):
    """SQL expression for a geography(Point,4326). Note PostGIS order is (longitude, latitude)."""
    return cast(func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326), Geography())


def round_coord(value: float, decimals: int) -> float:
    return round(float(value), decimals)


def distance_km(meters: float | None) -> float | None:
    return None if meters is None else round(float(meters) / 1000.0, 1)


# --- pricing (integer paise only) ------------------------------------------------------


class FeeCapExceededError(ApiError):
    def __init__(self, fee_bps: int, cap_bps: int):
        super().__init__(422, "FEE_CAP_EXCEEDED", f"Platform fee {fee_bps} bps exceeds the configured cap of {cap_bps} bps.")


def compute_fee_split(price_paise: int, fee_bps: int | None = None, cap_bps: int | None = None) -> tuple[int, int, int]:
    """Return (fee_bps, fee_paise, payout_paise). Rounds the fee half-up to the nearest paisa."""
    settings = get_settings()
    fee_bps = settings.platform_fee_bps if fee_bps is None else fee_bps
    cap_bps = settings.platform_fee_cap_bps if cap_bps is None else cap_bps
    if price_paise <= 0:
        raise unprocessable("INVALID_PRICE", "Price must be a positive number of paise.")
    if fee_bps < 0 or fee_bps > cap_bps or fee_bps > ABSOLUTE_FEE_CEILING_BPS:
        raise FeeCapExceededError(fee_bps, min(cap_bps, ABSOLUTE_FEE_CEILING_BPS))
    fee_paise = (price_paise * fee_bps + 5000) // 10000
    return fee_bps, fee_paise, price_paise - fee_paise


def price_for_slot(hourly_rate_paise: int, starts_at: datetime, ends_at: datetime) -> int:
    minutes = int((ends_at - starts_at).total_seconds() // 60)
    return hourly_rate_paise * minutes // 60


# --- audit -----------------------------------------------------------------------------


def audit(db: Session, entity_type: str, entity_id: UUID, actor: UUID | None, action: str, details: dict[str, Any] | None = None) -> None:
    db.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, actor_user_id=actor, action=action, details=details))


# --- identity --------------------------------------------------------------------------


def current_user(db: Session, verified: VerifiedUser) -> User:
    return UserService.get_or_sync_user(db, verified)


def require_worker_profile(db: Session, user: User) -> WorkerProfile:
    profile = get_worker_profile_by_user(db, user.id)
    if profile is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Create a worker profile first (Earn page).")
    return profile


def managed_organization_ids(db: Session, user_id: UUID) -> list[UUID]:
    """Organizations where the user may act on behalf of the organization (owner/admin)."""
    return list(
        db.scalars(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.membership_role.in_(("owner", "admin")),
            )
        )
    )


def verification_label(onboarding_status: str) -> str:
    return "Platform approved" if onboarding_status == "approved" else "Not verified — self-declared profile"
