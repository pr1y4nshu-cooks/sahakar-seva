"""mvp marketplace core: service settings, availability, jobs, applications, bookings, settlements, disputes

Revision ID: 0004_marketplace_core
Revises: 0003_skills_and_categories

Additive only: creates new tables. Existing Phase 2 / 3A tables and rows are not altered.
PostgreSQL-specific guarantees created here (not expressible in the SQLite test schema):
- exclusion constraints preventing overlapping active slots and overlapping active bookings per worker
  (requires btree_gist for uuid equality inside a GiST index);
- a trigger making simulated settlements immutable.
See docs/contracts/MVP_MARKETPLACE_CONTRACT.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType


class Geography(UserDefinedType):
    """Frozen copy for this migration: PostGIS geography(Point, 4326), distances in metres."""

    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "geography(Point,4326)"


revision: str = "0004_marketplace_core"
down_revision: Union[str, None] = "0003_skills_and_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, TS, server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public")

    op.create_table(
        "worker_service_settings",
        sa.Column("worker_profile_id", UUID, sa.ForeignKey("worker_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("locality", sa.String(120), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("radius_km", sa.Integer(), nullable=False),
        sa.Column("hourly_rate_paise", sa.Integer(), nullable=False),
        sa.Column("service_point", Geography(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("radius_km IN (2, 5, 10, 15, 25)", name="ck_worker_service_settings_radius"),
        sa.CheckConstraint("hourly_rate_paise BETWEEN 1000 AND 1000000", name="ck_worker_service_settings_rate"),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_worker_service_settings_coords"
        ),
    )
    op.create_index("ix_worker_service_settings_point", "worker_service_settings", ["service_point"], postgresql_using="gist")

    op.create_table(
        "availability_slots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("worker_profile_id", UUID, sa.ForeignKey("worker_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_at", TS, nullable=False),
        sa.Column("ends_at", TS, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _ts("created_at"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_availability_slots_time_order"),
    )
    op.create_index("ix_availability_slots_worker_starts", "availability_slots", ["worker_profile_id", "starts_at"])
    op.execute(
        "ALTER TABLE availability_slots ADD CONSTRAINT ex_availability_slots_no_overlap "
        "EXCLUDE USING gist (worker_profile_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE (is_active)"
    )

    op.create_table(
        "jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("customer_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("skill_id", UUID, sa.ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("locality", sa.String(120), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("job_point", Geography(), nullable=False),
        sa.Column("address_details", sa.Text(), nullable=False),
        sa.Column("starts_at", TS, nullable=False),
        sa.Column("ends_at", TS, nullable=False),
        sa.Column("budget_paise", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'open'"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("status IN ('open', 'filled', 'cancelled')", name="ck_jobs_status"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_jobs_time_order"),
        sa.CheckConstraint("budget_paise BETWEEN 5000 AND 10000000", name="ck_jobs_budget"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_jobs_coords"),
    )
    op.create_index("ix_jobs_point", "jobs", ["job_point"], postgresql_using="gist")
    op.create_index("ix_jobs_status_starts", "jobs", ["status", "starts_at"])
    op.create_index("ix_jobs_customer_user_id", "jobs", ["customer_user_id"])
    op.create_index("ix_jobs_organization_id", "jobs", ["organization_id"])

    op.create_table(
        "job_applications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("worker_profile_id", UUID, sa.ForeignKey("worker_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'applied'"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("job_id", "worker_profile_id", name="uq_job_applications_job_worker"),
        sa.CheckConstraint("status IN ('applied', 'selected', 'rejected', 'withdrawn')", name="ck_job_applications_status"),
    )
    op.create_index("ix_job_applications_worker_profile_id", "job_applications", ["worker_profile_id"])

    op.create_table(
        "bookings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("customer_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("worker_profile_id", UUID, sa.ForeignKey("worker_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("application_id", UUID, sa.ForeignKey("job_applications.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("slot_id", UUID, sa.ForeignKey("availability_slots.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("skill_id", UUID, sa.ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("starts_at", TS, nullable=False),
        sa.Column("ends_at", TS, nullable=False),
        sa.Column("locality", sa.String(120), nullable=False),
        sa.Column("address_details", sa.Text(), nullable=False),
        sa.Column("customer_notes", sa.Text(), nullable=True),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("fee_bps", sa.Integer(), nullable=False),
        sa.Column("fee_paise", sa.Integer(), nullable=False),
        sa.Column("payout_paise", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'requested'"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "status IN ('requested', 'confirmed', 'in_progress', 'completed', 'cancelled', 'declined', 'disputed')",
            name="ck_bookings_status",
        ),
        sa.CheckConstraint("origin IN ('direct', 'job')", name="ck_bookings_origin"),
        sa.CheckConstraint(
            "(origin = 'direct' AND slot_id IS NOT NULL AND job_id IS NULL) OR "
            "(origin = 'job' AND job_id IS NOT NULL AND application_id IS NOT NULL)",
            name="ck_bookings_origin_refs",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_bookings_time_order"),
        sa.CheckConstraint("price_paise > 0", name="ck_bookings_price_positive"),
        sa.CheckConstraint("fee_bps BETWEEN 0 AND 2000", name="ck_bookings_fee_ceiling"),
        sa.CheckConstraint(
            "fee_paise >= 0 AND payout_paise >= 0 AND fee_paise + payout_paise = price_paise",
            name="ck_bookings_fee_reconciles",
        ),
    )
    op.create_index("ix_bookings_worker_profile_id", "bookings", ["worker_profile_id"])
    op.create_index("ix_bookings_customer_user_id", "bookings", ["customer_user_id"])
    op.create_index(
        "uq_bookings_active_job",
        "bookings",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('requested', 'confirmed', 'in_progress')"),
    )
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT ex_bookings_worker_no_overlap "
        "EXCLUDE USING gist (worker_profile_id WITH =, tstzrange(starts_at, ends_at) WITH &&) "
        "WHERE (status IN ('confirmed', 'in_progress'))"
    )

    op.create_table(
        "settlements",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("booking_id", UUID, sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("gross_paise", sa.Integer(), nullable=False),
        sa.Column("fee_bps", sa.Integer(), nullable=False),
        sa.Column("fee_paise", sa.Integer(), nullable=False),
        sa.Column("payout_paise", sa.Integer(), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'simulated_settled'"), nullable=False),
        _ts("created_at"),
        sa.UniqueConstraint("booking_id", name="uq_settlements_booking_id"),
        sa.CheckConstraint("is_simulated", name="ck_settlements_simulated_only"),
        sa.CheckConstraint("status = 'simulated_settled'", name="ck_settlements_status"),
        sa.CheckConstraint("fee_bps BETWEEN 0 AND 2000", name="ck_settlements_fee_ceiling"),
        sa.CheckConstraint(
            "gross_paise > 0 AND fee_paise >= 0 AND payout_paise >= 0 AND fee_paise + payout_paise = gross_paise",
            name="ck_settlements_reconciles",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION settlements_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'settlements are immutable (simulated settlement audit record)';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_settlements_immutable BEFORE UPDATE OR DELETE ON settlements "
        "FOR EACH ROW EXECUTE FUNCTION settlements_immutable()"
    )

    op.create_table(
        "disputes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("booking_id", UUID, sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("opened_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("reviewer_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("outcome", sa.String(30), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", TS, nullable=True),
        _ts("created_at"),
        sa.UniqueConstraint("booking_id", name="uq_disputes_booking_id"),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_disputes_status"),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('resolved_for_customer', 'resolved_for_worker', 'no_fault')",
            name="ck_disputes_outcome",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND outcome IS NULL AND reviewer_user_id IS NULL AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND outcome IS NOT NULL AND resolution_reason IS NOT NULL "
            "AND reviewer_user_id IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_disputes_resolution_complete",
        ),
        sa.CheckConstraint(
            "reviewer_user_id IS NULL OR reviewer_user_id <> opened_by_user_id", name="ck_disputes_not_self_reviewed"
        ),
        sa.CheckConstraint("length(trim(description)) >= 10", name="ck_disputes_description"),
    )
    op.create_index("ix_disputes_status", "disputes", ["status"])

    op.create_table(
        "platform_reviewers",
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("granted_at"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("platform_reviewers")
    op.drop_index("ix_disputes_status", table_name="disputes")
    op.drop_table("disputes")
    op.execute("DROP TRIGGER IF EXISTS trg_settlements_immutable ON settlements")
    op.execute("DROP FUNCTION IF EXISTS settlements_immutable()")
    op.drop_table("settlements")
    op.drop_table("bookings")
    op.drop_table("job_applications")
    op.drop_table("jobs")
    op.drop_table("availability_slots")
    op.drop_table("worker_service_settings")
    # btree_gist is left installed: it is harmless and may be used by other objects.
