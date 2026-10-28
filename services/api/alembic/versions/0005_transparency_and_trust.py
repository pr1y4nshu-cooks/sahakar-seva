"""transparency and trust: versioned quotes, acceptances, append-only ledger, hash-chained financial
events, Merkle checkpoints with RFC 3161 anchoring state, repeat-booking and dispute-evidence columns

Revision ID: 0005_transparency_and_trust
Revises: 0004_marketplace_core

Additive only. Creates new tables and adds nullable columns. No existing row is modified or backfilled:
bookings and settlements created before this revision stay as they are and are shown as legacy records
(no quote acceptance, ledger or hash-chain evidence is claimed for them).

PostgreSQL-only protections created here:
- immutability triggers (no UPDATE/DELETE) on financial_events, price_quote_versions, quote_acceptances,
  financial_ledger_transactions, financial_ledger_entries;
- a DEFERRABLE INITIALLY DEFERRED constraint trigger that rejects any ledger transaction whose entries do
  not balance (sum of debits = sum of credits = transaction amount, at least 2 entries) at COMMIT;
- an anchor_checkpoints guard: body columns are immutable, rows cannot be deleted, and an
  EXTERNALLY_ANCHORED row cannot change at all;
- a bookings price guard: price columns can change only while the booking is still 'requested'
  (a new quote version is written in the same transaction by the application).
Triggers stop application code and accidental edits. They do not stop a database superuser, who can
disable triggers; external RFC 3161 timestamps exist for that case.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_transparency_and_trust"
down_revision: Union[str, None] = "0004_marketplace_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)

EVENT_TYPES = (
    "quote_created", "quote_revised", "quote_accepted", "booking_confirmed", "booking_declined",
    "booking_cancelled", "booking_completed", "simulated_settlement_recorded", "dispute_opened",
    "dispute_decision_recorded", "ledger_reversal_posted",
)
ANCHOR_STATUSES = ("LOCAL_ONLY", "ANCHOR_PENDING", "ANCHOR_SUBMITTED", "EXTERNALLY_ANCHORED", "ANCHOR_FAILED", "PROOF_INVALID")
ACCOUNTS = ("simulated_customer_payment_clearing", "simulated_worker_entitlement", "simulated_platform_fee_allocation")
DISPUTE_CATEGORIES = (
    "customer_total_differs", "worker_payout_differs", "unexpected_deduction", "payment_evidence_mismatch",
    "receipt_verification_failed", "other_booking_issue",
)
IMMUTABLE_TABLES = (
    "financial_events", "price_quote_versions", "quote_acceptances",
    "financial_ledger_transactions", "financial_ledger_entries",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _fk(target: str) -> sa.ForeignKey:
    return sa.ForeignKey(target, ondelete="RESTRICT")


def _created() -> sa.Column:
    return sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "financial_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("format_version", sa.String(60), nullable=False),
        sa.Column("hash_alg", sa.String(20), nullable=False),
        sa.Column("booking_id", UUID, _fk("bookings.id"), nullable=True),
        sa.Column("booking_event_index", sa.Integer(), nullable=True),
        sa.Column("settlement_id", UUID, _fk("settlements.id"), nullable=True),
        sa.Column("dispute_id", UUID, _fk("disputes.id"), nullable=True),
        sa.Column("payload_canonical", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("previous_event_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        _created(),
        sa.UniqueConstraint("sequence", name="uq_financial_events_sequence"),
        sa.UniqueConstraint("event_hash", name="uq_financial_events_event_hash"),
        sa.UniqueConstraint("previous_event_hash", name="uq_financial_events_previous_hash"),
        sa.UniqueConstraint("booking_id", "booking_event_index", name="uq_financial_events_booking_index"),
        sa.CheckConstraint("sequence > 0", name="ck_financial_events_sequence_positive"),
        sa.CheckConstraint(_in("event_type", EVENT_TYPES), name="ck_financial_events_type"),
        sa.CheckConstraint("hash_alg = 'sha-256'", name="ck_financial_events_hash_alg"),
        sa.CheckConstraint(
            "length(payload_hash) = 64 AND length(previous_event_hash) = 64 AND length(event_hash) = 64",
            name="ck_financial_events_hash_lengths",
        ),
    )
    op.create_index("ix_financial_events_booking_id", "financial_events", ["booking_id"])

    op.create_table(
        "price_quote_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("booking_id", UUID, _fk("bookings.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("pricing_basis", sa.String(60), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("customer_total_paise", sa.Integer(), nullable=False),
        sa.Column("worker_share_paise", sa.Integer(), nullable=False),
        sa.Column("platform_fee_paise", sa.Integer(), nullable=False),
        sa.Column("additional_charges_paise", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tax_paise", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("taxes_modeled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fee_bps", sa.Integer(), nullable=False),
        sa.Column("fee_cap_bps", sa.Integer(), nullable=False),
        sa.Column("fee_policy_id", sa.String(60), nullable=False),
        sa.Column("fee_policy_version", sa.String(60), nullable=False),
        sa.Column("initiated_by_user_id", UUID, _fk("users.id"), nullable=True),
        sa.Column("initiated_by_role", sa.String(20), nullable=False),
        sa.Column("financial_event_id", UUID, _fk("financial_events.id"), nullable=False),
        _created(),
        sa.UniqueConstraint("booking_id", "version", name="uq_price_quote_versions_booking_version"),
        sa.CheckConstraint("version >= 1", name="ck_price_quote_versions_version"),
        sa.CheckConstraint(
            _in("source", ("booking_request", "job_selection", "revision", "legacy_snapshot")),
            name="ck_price_quote_versions_source",
        ),
        sa.CheckConstraint("currency = 'INR'", name="ck_price_quote_versions_currency"),
        sa.CheckConstraint(
            "customer_total_paise > 0 AND worker_share_paise >= 0 AND platform_fee_paise >= 0 "
            "AND additional_charges_paise >= 0 AND tax_paise >= 0",
            name="ck_price_quote_versions_non_negative",
        ),
        sa.CheckConstraint(
            "worker_share_paise + platform_fee_paise + additional_charges_paise + tax_paise = customer_total_paise",
            name="ck_price_quote_versions_allocation_reconciles",
        ),
        sa.CheckConstraint("fee_bps BETWEEN 0 AND 2000 AND fee_bps <= fee_cap_bps", name="ck_price_quote_versions_fee_ceiling"),
        sa.CheckConstraint("taxes_modeled OR tax_paise = 0", name="ck_price_quote_versions_taxes"),
        sa.CheckConstraint(_in("initiated_by_role", ("customer", "worker", "system")), name="ck_price_quote_versions_initiator"),
    )
    op.create_index("ix_price_quote_versions_financial_event_id", "price_quote_versions", ["financial_event_id"])

    op.create_table(
        "quote_acceptances",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("quote_id", UUID, _fk("price_quote_versions.id"), nullable=False),
        sa.Column("booking_id", UUID, _fk("bookings.id"), nullable=False),
        sa.Column("user_id", UUID, _fk("users.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("financial_event_id", UUID, _fk("financial_events.id"), nullable=False),
        sa.Column("accepted_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("quote_id", "role", name="uq_quote_acceptances_quote_role"),
        sa.CheckConstraint("role IN ('customer', 'worker')", name="ck_quote_acceptances_role"),
    )
    op.create_index("ix_quote_acceptances_booking_id", "quote_acceptances", ["booking_id"])

    op.create_table(
        "financial_ledger_transactions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("booking_id", UUID, _fk("bookings.id"), nullable=False),
        sa.Column("settlement_id", UUID, _fk("settlements.id"), nullable=True),
        sa.Column("reverses_transaction_id", UUID, _fk("financial_ledger_transactions.id"), nullable=True),
        sa.Column("transaction_type", sa.String(40), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("source_event_id", UUID, _fk("financial_events.id"), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'posted'"), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), server_default=sa.true(), nullable=False),
        _created(),
        sa.UniqueConstraint("idempotency_key", name="uq_financial_ledger_transactions_idempotency_key"),
        sa.UniqueConstraint("settlement_id", name="uq_financial_ledger_transactions_settlement_id"),
        sa.UniqueConstraint("source_event_id", name="uq_financial_ledger_transactions_source_event_id"),
        sa.UniqueConstraint("reverses_transaction_id", name="uq_financial_ledger_transactions_reverses"),
        sa.CheckConstraint(
            "transaction_type IN ('simulated_booking_settlement', 'simulated_settlement_reversal')",
            name="ck_financial_ledger_transactions_type",
        ),
        sa.CheckConstraint("currency = 'INR'", name="ck_financial_ledger_transactions_currency"),
        sa.CheckConstraint("amount_paise > 0", name="ck_financial_ledger_transactions_amount"),
        sa.CheckConstraint("status = 'posted'", name="ck_financial_ledger_transactions_status"),
        sa.CheckConstraint("is_simulated", name="ck_financial_ledger_transactions_simulated"),
        sa.CheckConstraint(
            "(transaction_type = 'simulated_booking_settlement' AND settlement_id IS NOT NULL "
            "AND reverses_transaction_id IS NULL) OR "
            "(transaction_type = 'simulated_settlement_reversal' AND reverses_transaction_id IS NOT NULL)",
            name="ck_financial_ledger_transactions_refs",
        ),
    )
    op.create_index("ix_financial_ledger_transactions_booking_id", "financial_ledger_transactions", ["booking_id"])

    op.create_table(
        "financial_ledger_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("transaction_id", UUID, _fk("financial_ledger_transactions.id"), nullable=False),
        sa.Column("entry_index", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(60), nullable=False),
        sa.Column("direction", sa.String(6), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        _created(),
        sa.UniqueConstraint("transaction_id", "entry_index", name="uq_financial_ledger_entries_tx_index"),
        sa.CheckConstraint(_in("account_code", ACCOUNTS), name="ck_financial_ledger_entries_account"),
        sa.CheckConstraint("direction IN ('debit', 'credit')", name="ck_financial_ledger_entries_direction"),
        sa.CheckConstraint("amount_paise > 0", name="ck_financial_ledger_entries_amount"),
        sa.CheckConstraint("entry_index >= 0", name="ck_financial_ledger_entries_index"),
    )

    op.create_table(
        "anchor_checkpoints",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("checkpoint_index", sa.Integer(), nullable=False),
        sa.Column("format_version", sa.String(60), nullable=False),
        sa.Column("hash_alg", sa.String(20), nullable=False),
        sa.Column("first_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("merkle_root", sa.String(64), nullable=False),
        sa.Column("last_event_hash", sa.String(64), nullable=False),
        sa.Column("previous_checkpoint_digest", sa.String(64), nullable=False),
        sa.Column("body_canonical", sa.Text(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("anchor_status", sa.String(30), nullable=False),
        sa.Column("tsa_name", sa.String(120), nullable=True),
        sa.Column("tsa_url", sa.String(300), nullable=True),
        sa.Column("request_nonce", sa.String(40), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", TS, nullable=True),
        sa.Column("submitted_at", TS, nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("tsa_response_b64", sa.Text(), nullable=True),
        sa.Column("tsa_gen_time", TS, nullable=True),
        sa.Column("tsa_serial", sa.String(80), nullable=True),
        sa.Column("tsa_policy_oid", sa.String(80), nullable=True),
        sa.Column("tsa_signer_subject", sa.Text(), nullable=True),
        sa.Column("tsa_ca_fingerprint", sa.String(64), nullable=True),
        sa.Column("verified_at", TS, nullable=True),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("checkpoint_index", name="uq_anchor_checkpoints_index"),
        sa.UniqueConstraint("first_sequence", name="uq_anchor_checkpoints_first_sequence"),
        sa.UniqueConstraint("last_sequence", name="uq_anchor_checkpoints_last_sequence"),
        sa.UniqueConstraint("digest", name="uq_anchor_checkpoints_digest"),
        sa.CheckConstraint("checkpoint_index >= 1", name="ck_anchor_checkpoints_index"),
        sa.CheckConstraint(
            "first_sequence >= 1 AND last_sequence >= first_sequence "
            "AND event_count = last_sequence - first_sequence + 1",
            name="ck_anchor_checkpoints_range",
        ),
        sa.CheckConstraint(_in("anchor_status", ANCHOR_STATUSES), name="ck_anchor_checkpoints_status"),
        sa.CheckConstraint(
            "anchor_status <> 'EXTERNALLY_ANCHORED' OR (tsa_response_b64 IS NOT NULL AND tsa_gen_time IS NOT NULL "
            "AND verified_at IS NOT NULL)",
            name="ck_anchor_checkpoints_anchored_evidence",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_anchor_checkpoints_attempts"),
    )
    op.create_index("ix_anchor_checkpoints_status_next", "anchor_checkpoints", ["anchor_status", "next_attempt_at"])

    # --- additive columns on existing tables (nullable; existing rows untouched) ---
    op.add_column("bookings", sa.Column("repeat_of_booking_id", UUID, _fk("bookings.id"), nullable=True))
    op.add_column("disputes", sa.Column("category", sa.String(40), nullable=True))
    op.add_column("disputes", sa.Column("related_quote_version", sa.Integer(), nullable=True))
    op.add_column(
        "disputes",
        sa.Column("related_ledger_transaction_id", UUID, _fk("financial_ledger_transactions.id"), nullable=True),
    )
    op.add_column("disputes", sa.Column("related_receipt_event_hash", sa.String(64), nullable=True))
    op.add_column("disputes", sa.Column("ledger_correction", sa.String(20), nullable=True))
    op.create_check_constraint(
        "ck_disputes_category", "disputes", "category IS NULL OR " + _in("category", DISPUTE_CATEGORIES)
    )
    op.create_check_constraint(
        "ck_disputes_ledger_correction", "disputes", "ledger_correction IS NULL OR ledger_correction IN ('none', 'full_reversal')"
    )

    # --- append-only protections ---
    op.execute(
        """
        CREATE FUNCTION trust_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION trust_append_only()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION trust_append_only()"
        )

    # One checking function; thin per-table wrappers pass the transaction id (PL/pgSQL resolves NEW.<field>
    # per table, so a single trigger function cannot reference columns that only one table has).
    op.execute(
        """
        CREATE FUNCTION ledger_assert_balanced(tx_id uuid) RETURNS void LANGUAGE plpgsql AS $$
        DECLARE
            tx_amount integer;
            debits bigint;
            credits bigint;
            n integer;
        BEGIN
            SELECT amount_paise INTO tx_amount FROM financial_ledger_transactions WHERE id = tx_id;
            SELECT COALESCE(SUM(amount_paise) FILTER (WHERE direction = 'debit'), 0),
                   COALESCE(SUM(amount_paise) FILTER (WHERE direction = 'credit'), 0),
                   count(*)
              INTO debits, credits, n
              FROM financial_ledger_entries WHERE transaction_id = tx_id;
            IF tx_amount IS NULL OR n < 2 OR debits <> credits OR debits <> tx_amount THEN
                RAISE EXCEPTION 'ledger transaction % is not balanced (debits %, credits %, amount %, entries %)',
                    tx_id, debits, credits, tx_amount, n USING ERRCODE = 'check_violation';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledger_transaction_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM ledger_assert_balanced(NEW.id);
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledger_entry_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM ledger_assert_balanced(NEW.transaction_id);
            RETURN NULL;
        END;
        $$
        """
    )
    for table, fn in (("financial_ledger_transactions", "ledger_transaction_balanced"), ("financial_ledger_entries", "ledger_entry_balanced")):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER trg_{table}_balanced AFTER INSERT ON {table} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {fn}()"
        )

    op.execute(
        """
        CREATE FUNCTION anchor_checkpoints_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'anchor_checkpoints rows cannot be deleted' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF OLD.anchor_status = 'EXTERNALLY_ANCHORED' THEN
                RAISE EXCEPTION 'an externally anchored checkpoint is final' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF (NEW.id, NEW.checkpoint_index, NEW.format_version, NEW.hash_alg, NEW.first_sequence, NEW.last_sequence,
                NEW.event_count, NEW.merkle_root, NEW.last_event_hash, NEW.previous_checkpoint_digest,
                NEW.body_canonical, NEW.digest, NEW.created_at)
               IS DISTINCT FROM
               (OLD.id, OLD.checkpoint_index, OLD.format_version, OLD.hash_alg, OLD.first_sequence, OLD.last_sequence,
                OLD.event_count, OLD.merkle_root, OLD.last_event_hash, OLD.previous_checkpoint_digest,
                OLD.body_canonical, OLD.digest, OLD.created_at) THEN
                RAISE EXCEPTION 'checkpoint body is immutable' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_anchor_checkpoints_guard BEFORE UPDATE OR DELETE ON anchor_checkpoints "
        "FOR EACH ROW EXECUTE FUNCTION anchor_checkpoints_guard()"
    )
    op.execute(
        "CREATE TRIGGER trg_anchor_checkpoints_no_truncate BEFORE TRUNCATE ON anchor_checkpoints "
        "FOR EACH STATEMENT EXECUTE FUNCTION trust_append_only()"
    )

    op.execute(
        """
        CREATE FUNCTION bookings_price_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.price_paise, NEW.fee_bps, NEW.fee_paise, NEW.payout_paise)
               IS DISTINCT FROM (OLD.price_paise, OLD.fee_bps, OLD.fee_paise, OLD.payout_paise)
               AND OLD.status <> 'requested' THEN
                RAISE EXCEPTION 'the agreed price of a % booking cannot be changed', OLD.status
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_bookings_price_guard BEFORE UPDATE ON bookings "
        "FOR EACH ROW EXECUTE FUNCTION bookings_price_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bookings_price_guard ON bookings")
    op.execute("DROP FUNCTION IF EXISTS bookings_price_guard()")
    op.drop_constraint("ck_disputes_ledger_correction", "disputes", type_="check")
    op.drop_constraint("ck_disputes_category", "disputes", type_="check")
    for column in ("ledger_correction", "related_receipt_event_hash", "related_ledger_transaction_id",
                   "related_quote_version", "category"):
        op.drop_column("disputes", column)
    op.drop_column("bookings", "repeat_of_booking_id")
    op.drop_index("ix_anchor_checkpoints_status_next", table_name="anchor_checkpoints")
    op.drop_table("anchor_checkpoints")
    op.drop_table("financial_ledger_entries")
    op.drop_index("ix_financial_ledger_transactions_booking_id", table_name="financial_ledger_transactions")
    op.drop_table("financial_ledger_transactions")
    op.drop_index("ix_quote_acceptances_booking_id", table_name="quote_acceptances")
    op.drop_table("quote_acceptances")
    op.drop_index("ix_price_quote_versions_financial_event_id", table_name="price_quote_versions")
    op.drop_table("price_quote_versions")
    op.drop_index("ix_financial_events_booking_id", table_name="financial_events")
    op.drop_table("financial_events")
    op.execute("DROP FUNCTION IF EXISTS anchor_checkpoints_guard()")
    op.execute("DROP FUNCTION IF EXISTS ledger_transaction_balanced()")
    op.execute("DROP FUNCTION IF EXISTS ledger_entry_balanced()")
    op.execute("DROP FUNCTION IF EXISTS ledger_assert_balanced(uuid)")
    op.execute("DROP FUNCTION IF EXISTS trust_append_only()")
