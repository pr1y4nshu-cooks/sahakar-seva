"""configurable fee policies: versioned fee_policies table, quote pricing detail, wider ledger accounts

Revision ID: 0006_configurable_fee_policies
Revises: 0005_transparency_and_trust

Additive. Reviewed constraint changes (no safety rule is weakened):
- financial_ledger_entries.account_code: the allowed set GROWS by three simulated accounts needed for
  customer/business/platform-borne charges. Existing values stay allowed.
- financial_events.event_type: adds 'fee_policy_activated'. Existing values stay allowed.
- The 20% (2000 bps) ceiling is kept everywhere: bookings.fee_bps, settlements.fee_bps,
  price_quote_versions.fee_bps (now the effective charge rate on the service price, rounded up) and the new
  fee_policies.max_total_charge_bps. The pricing engine refuses a price that would breach a policy ceiling.
- price_quote_versions gains nullable columns (no backfill; rows are append-only). Quotes written before
  0006 keep their meaning: percentage, worker-borne, service price = customer total.
No existing booking, settlement, quote or ledger row is modified.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_configurable_fee_policies"
down_revision: Union[str, None] = "0005_transparency_and_trust"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)

OLD_ACCOUNTS = ("simulated_customer_payment_clearing", "simulated_worker_entitlement", "simulated_platform_fee_allocation")
NEW_ACCOUNTS = OLD_ACCOUNTS + (
    "simulated_business_payment_clearing", "simulated_processing_charge_allocation", "simulated_platform_promotion_expense",
)
OLD_EVENTS = (
    "quote_created", "quote_revised", "quote_accepted", "booking_confirmed", "booking_declined",
    "booking_cancelled", "booking_completed", "simulated_settlement_recorded", "dispute_opened",
    "dispute_decision_recorded", "ledger_reversal_posted",
)
NEW_EVENTS = OLD_EVENTS + ("fee_policy_activated",)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "fee_policies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("policy_id", sa.String(60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("is_example", sa.Boolean(), nullable=False),
        sa.Column("pricing_model", sa.String(30), nullable=False),
        sa.Column("max_total_charge_bps", sa.Integer(), nullable=False),
        sa.Column("definition_canonical", sa.Text(), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", TS, nullable=True),
        sa.Column("retired_at", TS, nullable=True),
        sa.Column("activation_event_id", UUID, sa.ForeignKey("financial_events.id", ondelete="RESTRICT"), nullable=True),
        sa.UniqueConstraint("policy_id", "version", name="uq_fee_policies_policy_version"),
        sa.CheckConstraint("version >= 1", name="ck_fee_policies_version"),
        sa.CheckConstraint("status IN ('draft', 'active', 'retired')", name="ck_fee_policies_status"),
        sa.CheckConstraint(
            "(scope = 'default' AND organization_id IS NULL) OR (scope = 'organization' AND organization_id IS NOT NULL)",
            name="ck_fee_policies_scope",
        ),
        sa.CheckConstraint("max_total_charge_bps BETWEEN 0 AND 2000", name="ck_fee_policies_charge_ceiling"),
        sa.CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(status = 'active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(status = 'retired' AND activated_at IS NOT NULL AND retired_at IS NOT NULL)",
            name="ck_fee_policies_lifecycle",
        ),
        sa.CheckConstraint("length(definition_hash) = 64", name="ck_fee_policies_hash"),
    )
    op.create_index("uq_fee_policies_active_default", "fee_policies", ["scope"], unique=True,
                    postgresql_where=sa.text("status = 'active' AND scope = 'default'"))
    op.create_index("uq_fee_policies_active_org", "fee_policies", ["organization_id"], unique=True,
                    postgresql_where=sa.text("status = 'active' AND scope = 'organization'"))
    op.execute(
        """
        CREATE FUNCTION fee_policies_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'fee policies cannot be deleted' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF (NEW.id, NEW.policy_id, NEW.version, NEW.scope, NEW.organization_id, NEW.label, NEW.is_example,
                NEW.pricing_model, NEW.max_total_charge_bps, NEW.definition_canonical, NEW.definition_hash, NEW.created_at)
               IS DISTINCT FROM
               (OLD.id, OLD.policy_id, OLD.version, OLD.scope, OLD.organization_id, OLD.label, OLD.is_example,
                OLD.pricing_model, OLD.max_total_charge_bps, OLD.definition_canonical, OLD.definition_hash, OLD.created_at) THEN
                RAISE EXCEPTION 'a fee policy version is immutable; create a new version' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NOT ((OLD.status = NEW.status AND OLD.activation_event_id IS NOT DISTINCT FROM NEW.activation_event_id
                     AND OLD.activated_at IS NOT DISTINCT FROM NEW.activated_at AND OLD.retired_at IS NOT DISTINCT FROM NEW.retired_at)
                    OR (OLD.status = 'draft' AND NEW.status = 'active')
                    OR (OLD.status = 'active' AND NEW.status = 'retired'
                        AND OLD.activated_at = NEW.activated_at AND OLD.activation_event_id IS NOT DISTINCT FROM NEW.activation_event_id)) THEN
                RAISE EXCEPTION 'fee policy status can only move draft -> active -> retired' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("CREATE TRIGGER trg_fee_policies_guard BEFORE UPDATE OR DELETE ON fee_policies "
               "FOR EACH ROW EXECUTE FUNCTION fee_policies_guard()")
    op.execute("CREATE TRIGGER trg_fee_policies_no_truncate BEFORE TRUNCATE ON fee_policies "
               "FOR EACH STATEMENT EXECUTE FUNCTION trust_append_only()")

    op.add_column("price_quote_versions", sa.Column("service_price_paise", sa.Integer(), nullable=True))
    op.add_column("price_quote_versions", sa.Column(
        "fee_policy_record_id", UUID, sa.ForeignKey("fee_policies.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("price_quote_versions", sa.Column("pricing_model", sa.String(30), nullable=True))
    op.add_column("price_quote_versions", sa.Column("policy_definition_hash", sa.String(64), nullable=True))
    op.add_column("price_quote_versions", sa.Column("line_items_canonical", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_price_quote_versions_service_price", "price_quote_versions",
        "service_price_paise IS NULL OR (service_price_paise > 0 AND worker_share_paise <= service_price_paise "
        "AND service_price_paise <= customer_total_paise)",
    )
    op.create_check_constraint(
        "ck_price_quote_versions_pricing_detail", "price_quote_versions",
        "(service_price_paise IS NULL AND line_items_canonical IS NULL) OR "
        "(service_price_paise IS NOT NULL AND line_items_canonical IS NOT NULL AND pricing_model IS NOT NULL)",
    )

    op.drop_constraint("ck_financial_ledger_entries_account", "financial_ledger_entries", type_="check")
    op.create_check_constraint("ck_financial_ledger_entries_account", "financial_ledger_entries", _in("account_code", NEW_ACCOUNTS))
    op.drop_constraint("ck_financial_events_type", "financial_events", type_="check")
    op.create_check_constraint("ck_financial_events_type", "financial_events", _in("event_type", NEW_EVENTS))


def downgrade() -> None:
    # Refuses (constraint violation) if rows using the new values exist, rather than deleting evidence.
    op.drop_constraint("ck_financial_events_type", "financial_events", type_="check")
    op.create_check_constraint("ck_financial_events_type", "financial_events", _in("event_type", OLD_EVENTS))
    op.drop_constraint("ck_financial_ledger_entries_account", "financial_ledger_entries", type_="check")
    op.create_check_constraint("ck_financial_ledger_entries_account", "financial_ledger_entries", _in("account_code", OLD_ACCOUNTS))
    op.drop_constraint("ck_price_quote_versions_pricing_detail", "price_quote_versions", type_="check")
    op.drop_constraint("ck_price_quote_versions_service_price", "price_quote_versions", type_="check")
    for column in ("line_items_canonical", "policy_definition_hash", "pricing_model", "fee_policy_record_id", "service_price_paise"):
        op.drop_column("price_quote_versions", column)
    op.execute("DROP TRIGGER IF EXISTS trg_fee_policies_no_truncate ON fee_policies")
    op.execute("DROP TRIGGER IF EXISTS trg_fee_policies_guard ON fee_policies")
    op.execute("DROP FUNCTION IF EXISTS fee_policies_guard()")
    op.drop_index("uq_fee_policies_active_org", table_name="fee_policies")
    op.drop_index("uq_fee_policies_active_default", table_name="fee_policies")
    op.drop_table("fee_policies")
