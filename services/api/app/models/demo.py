"""Provenance of synthetic demonstration data (migration 0007). See app/demo/."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEMO_ENTITY_TYPES = ("user", "worker_profile", "organization", "fee_policy", "slot", "job", "application", "booking", "dispute")


class DemoSeedRecord(Base):
    __tablename__ = "demo_seed_records"
    __table_args__ = (
        UniqueConstraint("seed_key", name="uq_demo_seed_records_seed_key"),
        UniqueConstraint("entity_type", "entity_id", name="uq_demo_seed_records_entity"),
        UniqueConstraint("showcase_key", name="uq_demo_seed_records_showcase_key"),
        CheckConstraint("entity_type IN (" + ", ".join(repr(t) for t in DEMO_ENTITY_TYPES) + ")", name="ck_demo_seed_records_entity_type"),
        CheckConstraint("showcase_key IS NULL OR entity_type = 'booking'", name="ck_demo_seed_records_showcase_booking_only"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset: Mapped[str] = mapped_column(String(60))
    dataset_version: Mapped[int] = mapped_column(Integer)
    seed_key: Mapped[str] = mapped_column(String(160))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    showcase_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
