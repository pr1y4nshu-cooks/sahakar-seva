"""Trust-layer models (migration 0005_transparency_and_trust).

Append-only guarantees (immutability triggers, deferred ledger-balance constraint trigger, booking price
guard) are PostgreSQL-only and live in the migration. Money is integer paise. Hashes are lowercase hex.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

QUOTE_SOURCES = ("booking_request", "job_selection", "revision", "legacy_snapshot")
PARTY_ROLES = ("customer", "worker")
FINANCIAL_EVENT_TYPES = (
    "quote_created",
    "quote_revised",
    "quote_accepted",
    "booking_confirmed",
    "booking_declined",
    "booking_cancelled",
    "booking_completed",
    "simulated_settlement_recorded",
    "dispute_opened",
    "dispute_decision_recorded",
    "ledger_reversal_posted",
    "fee_policy_activated",
)
LEDGER_TRANSACTION_TYPES = ("simulated_booking_settlement", "simulated_settlement_reversal")
LEDGER_ACCOUNTS = (
    "simulated_customer_payment_clearing",
    "simulated_worker_entitlement",
    "simulated_platform_fee_allocation",
    # 0006: configurable pricing models
    "simulated_business_payment_clearing",
    "simulated_processing_charge_allocation",
    "simulated_platform_promotion_expense",
)
ANCHOR_STATUSES = (
    "LOCAL_ONLY",
    "ANCHOR_PENDING",
    "ANCHOR_SUBMITTED",
    "EXTERNALLY_ANCHORED",
    "ANCHOR_FAILED",
    "PROOF_INVALID",
)
DISPUTE_CATEGORIES = (
    "customer_total_differs",
    "worker_payout_differs",
    "unexpected_deduction",
    "payment_evidence_mismatch",
    "receipt_verification_failed",
    "other_booking_issue",
)
LEDGER_CORRECTIONS = ("none", "full_reversal")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_fk(target: str, nullable: bool = False) -> Mapped:
    return mapped_column(PGUUID(as_uuid=True), ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialEvent(Base):
    """One link of the global, append-only, SHA-256 hash chain of financial events."""

    __tablename__ = "financial_events"
    __table_args__ = (
        UniqueConstraint("sequence", name="uq_financial_events_sequence"),
        UniqueConstraint("event_hash", name="uq_financial_events_event_hash"),
        UniqueConstraint("previous_event_hash", name="uq_financial_events_previous_hash"),
        UniqueConstraint("booking_id", "booking_event_index", name="uq_financial_events_booking_index"),
        CheckConstraint("sequence > 0", name="ck_financial_events_sequence_positive"),
        CheckConstraint(_in("event_type", FINANCIAL_EVENT_TYPES), name="ck_financial_events_type"),
        CheckConstraint("hash_alg = 'sha-256'", name="ck_financial_events_hash_alg"),
        CheckConstraint(
            "length(payload_hash) = 64 AND length(previous_event_hash) = 64 AND length(event_hash) = 64",
            name="ck_financial_events_hash_lengths",
        ),
        Index("ix_financial_events_booking_id", "booking_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    sequence: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(50))
    format_version: Mapped[str] = mapped_column(String(60))
    hash_alg: Mapped[str] = mapped_column(String(20))
    booking_id: Mapped[UUID | None] = _uuid_fk("bookings.id", nullable=True)
    booking_event_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settlement_id: Mapped[UUID | None] = _uuid_fk("settlements.id", nullable=True)
    dispute_id: Mapped[UUID | None] = _uuid_fk("disputes.id", nullable=True)
    payload_canonical: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    previous_event_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class PriceQuoteVersion(Base):
    """Immutable, versioned itemised price agreement for a booking. Both parties' views read this row."""

    __tablename__ = "price_quote_versions"
    __table_args__ = (
        UniqueConstraint("booking_id", "version", name="uq_price_quote_versions_booking_version"),
        CheckConstraint("version >= 1", name="ck_price_quote_versions_version"),
        CheckConstraint(_in("source", QUOTE_SOURCES), name="ck_price_quote_versions_source"),
        CheckConstraint("currency = 'INR'", name="ck_price_quote_versions_currency"),
        CheckConstraint(
            "customer_total_paise > 0 AND worker_share_paise >= 0 AND platform_fee_paise >= 0 "
            "AND additional_charges_paise >= 0 AND tax_paise >= 0",
            name="ck_price_quote_versions_non_negative",
        ),
        CheckConstraint(
            "worker_share_paise + platform_fee_paise + additional_charges_paise + tax_paise = customer_total_paise",
            name="ck_price_quote_versions_allocation_reconciles",
        ),
        CheckConstraint("fee_bps BETWEEN 0 AND 2000 AND fee_bps <= fee_cap_bps", name="ck_price_quote_versions_fee_ceiling"),
        CheckConstraint("taxes_modeled OR tax_paise = 0", name="ck_price_quote_versions_taxes"),
        CheckConstraint(_in("initiated_by_role", PARTY_ROLES + ("system",)), name="ck_price_quote_versions_initiator"),
        Index("ix_price_quote_versions_financial_event_id", "financial_event_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = _uuid_fk("bookings.id")
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30))
    pricing_basis: Mapped[str] = mapped_column(String(60))
    currency: Mapped[str] = mapped_column(String(3))
    customer_total_paise: Mapped[int] = mapped_column(Integer)
    worker_share_paise: Mapped[int] = mapped_column(Integer)
    platform_fee_paise: Mapped[int] = mapped_column(Integer)
    additional_charges_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    tax_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    taxes_modeled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    fee_bps: Mapped[int] = mapped_column(Integer)
    fee_cap_bps: Mapped[int] = mapped_column(Integer)
    fee_policy_id: Mapped[str] = mapped_column(String(60))
    fee_policy_version: Mapped[str] = mapped_column(String(60))
    initiated_by_user_id: Mapped[UUID | None] = _uuid_fk("users.id", nullable=True)
    initiated_by_role: Mapped[str] = mapped_column(String(20))
    financial_event_id: Mapped[UUID] = _uuid_fk("financial_events.id")
    created_at: Mapped[datetime] = _created()
    # 0006: configurable pricing. NULL on quotes written before 0006 (percentage, worker-borne, service = total).
    service_price_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_policy_record_id: Mapped[UUID | None] = _uuid_fk("fee_policies.id", nullable=True)
    pricing_model: Mapped[str | None] = mapped_column(String(30), nullable=True)
    policy_definition_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    line_items_canonical: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeePolicy(Base):
    """Versioned fee policy. Definition columns are immutable (trigger); status moves draft -> active -> retired.

    At most one active policy for the default scope and one per organization. Policies are created and
    activated only by the server-side CLI (python -m app.cli.fee_policy); there is no write API.
    """

    __tablename__ = "fee_policies"
    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_fee_policies_policy_version"),
        CheckConstraint("version >= 1", name="ck_fee_policies_version"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="ck_fee_policies_status"),
        CheckConstraint(
            "(scope = 'default' AND organization_id IS NULL) OR (scope = 'organization' AND organization_id IS NOT NULL)",
            name="ck_fee_policies_scope",
        ),
        CheckConstraint("max_total_charge_bps BETWEEN 0 AND 2000", name="ck_fee_policies_charge_ceiling"),
        CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(status = 'active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(status = 'retired' AND activated_at IS NOT NULL AND retired_at IS NOT NULL)",
            name="ck_fee_policies_lifecycle",
        ),
        CheckConstraint("length(definition_hash) = 64", name="ck_fee_policies_hash"),
        Index(
            "uq_fee_policies_active_default", "scope", unique=True,
            postgresql_where=text("status = 'active' AND scope = 'default'"),
            sqlite_where=text("status = 'active' AND scope = 'default'"),
        ),
        Index(
            "uq_fee_policies_active_org", "organization_id", unique=True,
            postgresql_where=text("status = 'active' AND scope = 'organization'"),
            sqlite_where=text("status = 'active' AND scope = 'organization'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_id: Mapped[str] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(20))
    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(160))
    is_example: Mapped[bool] = mapped_column(Boolean)
    pricing_model: Mapped[str] = mapped_column(String(30))
    max_total_charge_bps: Mapped[int] = mapped_column(Integer)
    definition_canonical: Mapped[str] = mapped_column(Text)
    definition_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activation_event_id: Mapped[UUID | None] = _uuid_fk("financial_events.id", nullable=True)


class QuoteAcceptance(Base):
    """Immutable record that an authenticated party accepted one exact quote version."""

    __tablename__ = "quote_acceptances"
    __table_args__ = (
        UniqueConstraint("quote_id", "role", name="uq_quote_acceptances_quote_role"),
        CheckConstraint(_in("role", PARTY_ROLES), name="ck_quote_acceptances_role"),
        Index("ix_quote_acceptances_booking_id", "booking_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = _uuid_fk("price_quote_versions.id")
    booking_id: Mapped[UUID] = _uuid_fk("bookings.id")
    user_id: Mapped[UUID] = _uuid_fk("users.id")
    role: Mapped[str] = mapped_column(String(20))
    financial_event_id: Mapped[UUID] = _uuid_fk("financial_events.id")
    accepted_at: Mapped[datetime] = _created()


class LedgerTransaction(Base):
    """Balanced, append-only double-entry transaction (demonstration accounting; simulated money)."""

    __tablename__ = "financial_ledger_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_financial_ledger_transactions_idempotency_key"),
        UniqueConstraint("settlement_id", name="uq_financial_ledger_transactions_settlement_id"),
        UniqueConstraint("source_event_id", name="uq_financial_ledger_transactions_source_event_id"),
        UniqueConstraint("reverses_transaction_id", name="uq_financial_ledger_transactions_reverses"),
        CheckConstraint(_in("transaction_type", LEDGER_TRANSACTION_TYPES), name="ck_financial_ledger_transactions_type"),
        CheckConstraint("currency = 'INR'", name="ck_financial_ledger_transactions_currency"),
        CheckConstraint("amount_paise > 0", name="ck_financial_ledger_transactions_amount"),
        CheckConstraint("status = 'posted'", name="ck_financial_ledger_transactions_status"),
        CheckConstraint("is_simulated", name="ck_financial_ledger_transactions_simulated"),
        CheckConstraint(
            "(transaction_type = 'simulated_booking_settlement' AND settlement_id IS NOT NULL "
            "AND reverses_transaction_id IS NULL) OR "
            "(transaction_type = 'simulated_settlement_reversal' AND reverses_transaction_id IS NOT NULL)",
            name="ck_financial_ledger_transactions_refs",
        ),
        Index("ix_financial_ledger_transactions_booking_id", "booking_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = _uuid_fk("bookings.id")
    settlement_id: Mapped[UUID | None] = _uuid_fk("settlements.id", nullable=True)
    reverses_transaction_id: Mapped[UUID | None] = _uuid_fk("financial_ledger_transactions.id", nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    amount_paise: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    source_event_id: Mapped[UUID] = _uuid_fk("financial_events.id")
    status: Mapped[str] = mapped_column(String(20), server_default=text("'posted'"))
    is_simulated: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = _created()


class LedgerEntry(Base):
    __tablename__ = "financial_ledger_entries"
    __table_args__ = (
        UniqueConstraint("transaction_id", "entry_index", name="uq_financial_ledger_entries_tx_index"),
        CheckConstraint(_in("account_code", LEDGER_ACCOUNTS), name="ck_financial_ledger_entries_account"),
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_financial_ledger_entries_direction"),
        CheckConstraint("amount_paise > 0", name="ck_financial_ledger_entries_amount"),
        CheckConstraint("entry_index >= 0", name="ck_financial_ledger_entries_index"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    transaction_id: Mapped[UUID] = _uuid_fk("financial_ledger_transactions.id")
    entry_index: Mapped[int] = mapped_column(Integer)
    account_code: Mapped[str] = mapped_column(String(60))
    direction: Mapped[str] = mapped_column(String(6))
    amount_paise: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()


class AnchorCheckpoint(Base):
    """Merkle checkpoint over a contiguous range of financial events plus its external-anchor outbox state.

    The checkpoint body columns are immutable (trigger). Only the anchoring status columns may change,
    and nothing may change once the row is EXTERNALLY_ANCHORED.
    """

    __tablename__ = "anchor_checkpoints"
    __table_args__ = (
        UniqueConstraint("checkpoint_index", name="uq_anchor_checkpoints_index"),
        UniqueConstraint("first_sequence", name="uq_anchor_checkpoints_first_sequence"),
        UniqueConstraint("last_sequence", name="uq_anchor_checkpoints_last_sequence"),
        UniqueConstraint("digest", name="uq_anchor_checkpoints_digest"),
        CheckConstraint("checkpoint_index >= 1", name="ck_anchor_checkpoints_index"),
        CheckConstraint(
            "first_sequence >= 1 AND last_sequence >= first_sequence "
            "AND event_count = last_sequence - first_sequence + 1",
            name="ck_anchor_checkpoints_range",
        ),
        CheckConstraint(_in("anchor_status", ANCHOR_STATUSES), name="ck_anchor_checkpoints_status"),
        CheckConstraint(
            "anchor_status <> 'EXTERNALLY_ANCHORED' OR (tsa_response_b64 IS NOT NULL AND tsa_gen_time IS NOT NULL "
            "AND verified_at IS NOT NULL)",
            name="ck_anchor_checkpoints_anchored_evidence",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_anchor_checkpoints_attempts"),
        Index("ix_anchor_checkpoints_status_next", "anchor_status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    checkpoint_index: Mapped[int] = mapped_column(Integer)
    format_version: Mapped[str] = mapped_column(String(60))
    hash_alg: Mapped[str] = mapped_column(String(20))
    first_sequence: Mapped[int] = mapped_column(BigInteger)
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    event_count: Mapped[int] = mapped_column(Integer)
    merkle_root: Mapped[str] = mapped_column(String(64))
    last_event_hash: Mapped[str] = mapped_column(String(64))
    previous_checkpoint_digest: Mapped[str] = mapped_column(String(64))
    body_canonical: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # --- external anchoring outbox state (mutable until EXTERNALLY_ANCHORED) ---
    anchor_status: Mapped[str] = mapped_column(String(30))
    tsa_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tsa_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    request_nonce: Mapped[str | None] = mapped_column(String(40), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tsa_response_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    tsa_gen_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tsa_serial: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tsa_policy_oid: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tsa_signer_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    tsa_ca_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
