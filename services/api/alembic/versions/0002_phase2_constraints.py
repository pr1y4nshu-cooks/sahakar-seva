"""add phase 2 check constraints

Revision ID: 0002_phase2_constraints
Revises: 0001_foundation
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_phase2_constraints"
down_revision: Union[str, None] = "0001_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_worker_profiles_onboarding_status",
        "worker_profiles",
        "onboarding_status IN ('draft', 'pending_review', 'approved', 'restricted')",
    )
    op.create_check_constraint(
        "ck_organizations_organization_type",
        "organizations",
        "organization_type IN ('business', 'cooperative')",
    )
    op.create_check_constraint(
        "ck_organization_memberships_role",
        "organization_memberships",
        "membership_role IN ('owner', 'admin', 'member')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organization_memberships_role", "organization_memberships", type_="check")
    op.drop_constraint("ck_organizations_organization_type", "organizations", type_="check")
    op.drop_constraint("ck_worker_profiles_onboarding_status", "worker_profiles", type_="check")
