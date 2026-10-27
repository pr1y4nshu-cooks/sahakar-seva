"""phase 3a: service categories, skills and worker skill declarations

Revision ID: 0003_skills_and_categories
Revises: 0002_phase2_constraints

Additive only: creates three new tables. Existing users, worker_profiles, organizations
and organization_memberships are not altered. No seed data is inserted here
(see app/db/seed.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_skills_and_categories"
down_revision: Union[str, None] = "0002_phase2_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SLUG_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*$"


def upgrade() -> None:
    op.create_table(
        "service_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_service_categories_slug"),
        sa.CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="ck_service_categories_slug_format"),
        sa.CheckConstraint("length(trim(name)) >= 2", name="ck_service_categories_name_not_blank"),
    )
    op.create_index(
        "uq_service_categories_name_lower", "service_categories", [sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"], ["service_categories.id"], name="skills_category_id_fkey", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("slug", name="uq_skills_slug"),
        sa.CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="ck_skills_slug_format"),
        sa.CheckConstraint("length(trim(name)) >= 2", name="ck_skills_name_not_blank"),
    )
    op.create_index("ix_skills_category_id", "skills", ["category_id"])
    op.create_index(
        "uq_skills_category_name_lower", "skills", ["category_id", sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "worker_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("worker_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["worker_profile_id"],
            ["worker_profiles.id"],
            name="worker_skills_worker_profile_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="worker_skills_skill_id_fkey", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("worker_profile_id", "skill_id", name="uq_worker_skills_worker_profile_skill"),
    )
    op.create_index("ix_worker_skills_skill_id", "worker_skills", ["skill_id"])


def downgrade() -> None:
    op.drop_index("ix_worker_skills_skill_id", table_name="worker_skills")
    op.drop_table("worker_skills")
    op.drop_index("uq_skills_category_name_lower", table_name="skills")
    op.drop_index("ix_skills_category_id", table_name="skills")
    op.drop_table("skills")
    op.drop_index("uq_service_categories_name_lower", table_name="service_categories")
    op.drop_table("service_categories")
