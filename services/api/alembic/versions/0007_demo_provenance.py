"""demo provenance: demo_seed_records maps stable seed keys to synthetic demonstration entities

Revision ID: 0007_demo_provenance
Revises: 0006_configurable_fee_policies

Additive: one new table, no existing row is read or modified. It lets the demo seeder (a) prove which rows are
synthetic and (b) be idempotent (a seed key is registered at most once). It carries no financial meaning; the
ledger, events and quotes of demo bookings are produced by the normal application code.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_demo_provenance"
down_revision: Union[str, None] = "0006_configurable_fee_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENTITY_TYPES = ("user", "worker_profile", "organization", "fee_policy", "slot", "job", "application", "booking", "dispute")


def upgrade() -> None:
    op.create_table(
        "demo_seed_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset", sa.String(60), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("seed_key", sa.String(160), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("showcase_key", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("seed_key", name="uq_demo_seed_records_seed_key"),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_demo_seed_records_entity"),
        sa.UniqueConstraint("showcase_key", name="uq_demo_seed_records_showcase_key"),
        sa.CheckConstraint("entity_type IN (" + ", ".join(repr(t) for t in ENTITY_TYPES) + ")", name="ck_demo_seed_records_entity_type"),
        sa.CheckConstraint("showcase_key IS NULL OR entity_type = 'booking'", name="ck_demo_seed_records_showcase_booking_only"),
    )


def downgrade() -> None:
    op.drop_table("demo_seed_records")
