"""MVP marketplace models (migration 0004_marketplace_core).

PostgreSQL-only guarantees that the SQLite API-test schema cannot express (geography types are
emitted as plain columns there, exclusion constraints and triggers) live in the migration; see
docs/contracts/MVP_MARKETPLACE_CONTRACT.md. Money is always integer paise.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.db.base import Base

ALLOWED_RADII_KM = (2, 5, 10, 15, 25)
ACTIVE_BOOKING_STATUSES = ("requested", "confirmed", "in_progress")
BOOKING_STATUSES = ("requested", "confirmed", "in_progress", "completed", "cancelled", "declined", "disputed")
SIMULATED_PAYMENT_LABEL = "SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED"


class Geography(UserDefinedType):
    """PostGIS geography(Point, 4326). Distances on this type are in metres."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "geography(Point,4326)"


# SQLite (API unit tests) cannot parse the PostGIS type name; it stores the column as TEXT there.
GEOGRAPHY_POINT = Geography().with_variant(Text(), "sqlite")


def _in(column: str, values: tuple) -> str:
    return f"{column} IN ({', '.join(repr(v) if isinstance(v, str) else str(v) for v in values)})"


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkerServiceSettings(Base):
    """Where a worker offers services (approximate centre, rounded server-side) and their rate."""

    __tablename__ = "worker_service_settings"
    __table_args__ = (
        CheckConstraint(_in("radius_km", ALLOWED_RADII_KM), name="ck_worker_service_settings_radius"),
        CheckConstraint("hourly_rate_paise BETWEEN 1000 AND 1000000", name="ck_worker_service_settings_rate"),
        CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_worker_service_settings_coords"),
        Index("ix_worker_service_settings_point", "service_point", postgresql_using="gist"),
    )

    worker_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("worker_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    locality: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    radius_km: Mapped[int] = mapped_column(Integer)
    hourly_rate_paise: Mapped[int] = mapped_column(Integer)
    service_point: Mapped[Any] = mapped_column(GEOGRAPHY_POINT, deferred=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_availability_slots_time_order"),
        Index("ix_availability_slots_worker_starts", "worker_profile_id", "starts_at"),
    )

    id: Mapped[UUID] = _uuid_pk()
    worker_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("worker_profiles.id", ondelete="CASCADE")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = _created()


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", ("open", "filled", "cancelled")), name="ck_jobs_status"),
        CheckConstraint("ends_at > starts_at", name="ck_jobs_time_order"),
        CheckConstraint("budget_paise BETWEEN 5000 AND 10000000", name="ck_jobs_budget"),
        CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_jobs_coords"),
        Index("ix_jobs_point", "job_point", postgresql_using="gist"),
        Index("ix_jobs_status_starts", "status", "starts_at"),
        Index("ix_jobs_customer_user_id", "customer_user_id"),
        Index("ix_jobs_organization_id", "organization_id"),
    )

    id: Mapped[UUID] = _uuid_pk()
    customer_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    skill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    locality: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    job_point: Mapped[Any] = mapped_column(GEOGRAPHY_POINT, deferred=True)
    address_details: Mapped[str] = mapped_column(Text)  # private: owner + booked worker only
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    budget_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default=text("'open'"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    skill = relationship("Skill")


class JobApplication(Base):
    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("job_id", "worker_profile_id", name="uq_job_applications_job_worker"),
        CheckConstraint(_in("status", ("applied", "selected", "rejected", "withdrawn")), name="ck_job_applications_status"),
        Index("ix_job_applications_worker_profile_id", "worker_profile_id"),
    )

    id: Mapped[UUID] = _uuid_pk()
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    worker_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("worker_profiles.id", ondelete="CASCADE")
    )
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="applied", server_default=text("'applied'"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    job: Mapped[Job] = relationship()


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(_in("status", BOOKING_STATUSES), name="ck_bookings_status"),
        CheckConstraint(_in("origin", ("direct", "job")), name="ck_bookings_origin"),
        CheckConstraint(
            "(origin = 'direct' AND slot_id IS NOT NULL AND job_id IS NULL) OR "
            "(origin = 'job' AND job_id IS NOT NULL AND application_id IS NOT NULL)",
            name="ck_bookings_origin_refs",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_bookings_time_order"),
        CheckConstraint("price_paise > 0", name="ck_bookings_price_positive"),
        CheckConstraint("fee_bps BETWEEN 0 AND 2000", name="ck_bookings_fee_ceiling"),
        CheckConstraint("fee_paise >= 0 AND payout_paise >= 0 AND fee_paise + payout_paise = price_paise", name="ck_bookings_fee_reconciles"),
        Index("ix_bookings_worker_profile_id", "worker_profile_id"),
        Index("ix_bookings_customer_user_id", "customer_user_id"),
        Index(
            "uq_bookings_active_job",
            "job_id",
            unique=True,
            postgresql_where=text("status IN ('requested', 'confirmed', 'in_progress')"),
            sqlite_where=text("status IN ('requested', 'confirmed', 'in_progress')"),
        ),
    )

    id: Mapped[UUID] = _uuid_pk()
    customer_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    worker_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("worker_profiles.id", ondelete="RESTRICT")
    )
    origin: Mapped[str] = mapped_column(String(10))
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"))
    application_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="RESTRICT")
    )
    slot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("availability_slots.id", ondelete="RESTRICT")
    )
    skill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locality: Mapped[str] = mapped_column(String(120))
    address_details: Mapped[str] = mapped_column(Text)
    customer_notes: Mapped[str | None] = mapped_column(Text)
    price_paise: Mapped[int] = mapped_column(Integer)
    fee_bps: Mapped[int] = mapped_column(Integer)
    fee_paise: Mapped[int] = mapped_column(Integer)
    payout_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="requested", server_default=text("'requested'"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    skill = relationship("Skill")
    worker_profile = relationship("WorkerProfile")
    customer = relationship("User")


class Settlement(Base):
    """Immutable simulated settlement (UPDATE/DELETE blocked by a database trigger)."""

    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_settlements_booking_id"),
        CheckConstraint("is_simulated", name="ck_settlements_simulated_only"),
        CheckConstraint("status = 'simulated_settled'", name="ck_settlements_status"),
        CheckConstraint("fee_bps BETWEEN 0 AND 2000", name="ck_settlements_fee_ceiling"),
        CheckConstraint(
            "gross_paise > 0 AND fee_paise >= 0 AND payout_paise >= 0 AND fee_paise + payout_paise = gross_paise",
            name="ck_settlements_reconciles",
        ),
    )

    id: Mapped[UUID] = _uuid_pk()
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bookings.id", ondelete="RESTRICT"))
    gross_paise: Mapped[int] = mapped_column(Integer)
    fee_bps: Mapped[int] = mapped_column(Integer)
    fee_paise: Mapped[int] = mapped_column(Integer)
    payout_paise: Mapped[int] = mapped_column(Integer)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    status: Mapped[str] = mapped_column(String(30), default="simulated_settled", server_default=text("'simulated_settled'"))
    created_at: Mapped[datetime] = _created()


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_disputes_booking_id"),
        CheckConstraint(_in("status", ("open", "resolved")), name="ck_disputes_status"),
        CheckConstraint(
            "outcome IS NULL OR " + _in("outcome", ("resolved_for_customer", "resolved_for_worker", "no_fault")),
            name="ck_disputes_outcome",
        ),
        CheckConstraint(
            "(status = 'open' AND outcome IS NULL AND reviewer_user_id IS NULL AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND outcome IS NOT NULL AND resolution_reason IS NOT NULL "
            "AND reviewer_user_id IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_disputes_resolution_complete",
        ),
        CheckConstraint("reviewer_user_id IS NULL OR reviewer_user_id <> opened_by_user_id", name="ck_disputes_not_self_reviewed"),
        CheckConstraint("length(trim(description)) >= 10", name="ck_disputes_description"),
        Index("ix_disputes_status", "status"),
    )

    id: Mapped[UUID] = _uuid_pk()
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bookings.id", ondelete="RESTRICT"))
    opened_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default=text("'open'"))
    reviewer_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    outcome: Mapped[str | None] = mapped_column(String(30))
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()

    booking: Mapped[Booking] = relationship()


class PlatformReviewer(Base):
    """Users allowed to resolve disputes. Granted only by the server-side CLI."""

    __tablename__ = "platform_reviewers"

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    note: Mapped[str | None] = mapped_column(Text)
    granted_at: Mapped[datetime] = _created()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity", "entity_type", "entity_id"),)

    id: Mapped[UUID] = _uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60))
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = _created()
