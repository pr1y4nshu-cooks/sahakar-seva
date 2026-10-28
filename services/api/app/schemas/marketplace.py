"""MVP marketplace request/response schemas (docs/contracts/MVP_MARKETPLACE_CONTRACT.md)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

RadiusKm = Literal[2, 5, 10, 15, 25]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _trimmed(v: str | None) -> str | None:
    return v.strip() if isinstance(v, str) else v


# --- taxonomy ------------------------------------------------------------------------------


class CategoryRead(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None = None


class SkillRead(BaseModel):
    id: UUID
    category_id: UUID
    slug: str
    name: str
    description: str | None = None
    is_active: bool = True


class WorkerSkillRead(BaseModel):
    skill: SkillRead
    category: CategoryRead
    declared_at: datetime
    is_self_declared: Literal[True] = True


class WorkerSkillCreate(_Strict):
    skill_id: UUID


class LocalityRead(BaseModel):
    slug: str
    name: str
    city: str
    latitude: float
    longitude: float


# --- worker setup --------------------------------------------------------------------------


class _Location(_Strict):
    locality: str = Field(..., min_length=2, max_length=120)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

    _trim = field_validator("locality")(_trimmed)


class ServiceSettingsUpdate(_Location):
    radius_km: RadiusKm
    hourly_rate_paise: int = Field(..., ge=1000, le=1_000_000)


class ServiceSettingsRead(BaseModel):
    locality: str
    latitude: float
    longitude: float
    radius_km: int
    hourly_rate_paise: int
    privacy_note: str = "Your service centre is rounded to about 1 km. Customers only see your locality and distance."
    updated_at: datetime


class SlotCreate(_Strict):
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class SlotRead(BaseModel):
    id: UUID
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    booking_status: str | None = None  # status of an active booking holding this slot, if any


# --- discovery -----------------------------------------------------------------------------


class AvailableSlotRead(BaseModel):
    id: UUID
    starts_at: datetime
    ends_at: datetime
    price_paise: int


class WorkerSearchResult(BaseModel):
    worker_profile_id: UUID
    display_name: str
    bio: str | None = None
    locality: str
    distance_km: float
    service_radius_km: int
    hourly_rate_paise: int
    onboarding_status: str
    verification_label: str
    skills: list[SkillRead]
    skills_are_self_declared: Literal[True] = True
    available_slots: list[AvailableSlotRead]
    match_reasons: list[str]


class WorkerSearchResponse(BaseModel):
    results: list[WorkerSearchResult]
    total: int
    criteria: dict


# --- bookings ------------------------------------------------------------------------------


class BookingCreate(_Location):
    worker_profile_id: UUID
    slot_id: UUID
    skill_id: UUID
    address_details: str = Field(..., min_length=5, max_length=500)
    customer_notes: str | None = Field(default=None, max_length=500)
    # 0005: optional link to an earlier completed booking with the same worker ("book again").
    repeat_of_booking_id: UUID | None = None


class PriceBreakdown(BaseModel):
    price_paise: int
    fee_bps: int
    fee_paise: int
    payout_paise: int
    fee_policy: str


class SettlementRead(BaseModel):
    id: UUID
    gross_paise: int
    fee_bps: int
    fee_paise: int
    payout_paise: int
    status: str
    is_simulated: bool
    label: str
    created_at: datetime


class DisputeSummary(BaseModel):
    id: UUID
    status: str
    description: str
    outcome: str | None = None
    resolution_reason: str | None = None
    resolved_at: datetime | None = None
    opened_by_me: bool
    category: str | None = None
    related_quote_version: int | None = None
    related_ledger_transaction_id: UUID | None = None
    related_receipt_event_hash: str | None = None
    ledger_correction: str | None = None


class AgreementSummary(BaseModel):
    """The single authoritative price agreement both parties see (current quote version)."""

    model_config = ConfigDict(extra="allow")

    evidence_level: Literal["versioned", "legacy_snapshot", "legacy"]
    service_price_paise: int
    pricing_model: str | None = None
    policy_definition_hash: str | None = None
    is_example_policy: bool | None = None
    policy_label: str | None = None
    line_items: list[dict] = []
    processing_note: str | None = None
    note: str | None = None
    quote_id: UUID | None = None
    quote_version: int | None = None
    source: str | None = None
    versions: int
    customer_total_paise: int
    worker_share_paise: int
    platform_fee_paise: int
    additional_charges_paise: int
    tax_paise: int
    taxes_modeled: bool
    fee_bps: int
    fee_policy_id: str | None = None
    fee_policy_version: str | None = None
    currency: str
    created_at: datetime | None = None
    customer_accepted_at: datetime | None = None
    worker_accepted_at: datetime | None = None
    awaiting_acceptance_from: Literal["customer", "worker"] | None = None
    matches_booking_snapshot: bool
    tax_note: str
    additional_charges_note: str


class AnchorSummary(BaseModel):
    status: str | None = None
    label: str
    checkpoint_index: int | None = None
    tsa_gen_time: datetime | None = None
    events_externally_anchored: int
    events_total: int


class EvidenceSummary(BaseModel):
    payment_evidence: str
    payment_evidence_status: Literal["SIMULATED"]
    ledger_status: Literal["posted", "reversed", "legacy_not_posted", "not_applicable_yet"]
    ledger_transaction_id: UUID | None = None
    ledger_balanced: bool | None = None
    reversal_transaction_id: UUID | None = None
    event_count: int
    latest_event_hash: str | None = None
    anchor: AnchorSummary


class BookingRead(BaseModel):
    id: UUID
    origin: Literal["direct", "job"]
    status: str
    my_role: Literal["customer", "worker"]
    job_id: UUID | None = None
    skill: SkillRead
    worker_profile_id: UUID
    worker_display_name: str
    worker_verification_label: str
    customer_display_name: str
    starts_at: datetime
    ends_at: datetime
    locality: str
    address_details: str | None = None
    address_hidden_reason: str | None = None
    customer_notes: str | None = None
    price: PriceBreakdown
    settlement: SettlementRead | None = None
    dispute: DisputeSummary | None = None
    allowed_actions: list[str]
    agreement_actions: list[str] = []
    agreement: AgreementSummary | None = None
    evidence: EvidenceSummary | None = None
    repeat_of_booking_id: UUID | None = None
    is_synthetic_demo: bool = False
    created_at: datetime
    updated_at: datetime


class BookingActionBody(_Strict):
    quote_version: int | None = Field(default=None, ge=1)


class QuoteRevisionCreate(_Strict):
    # The proposed SERVICE price; the booking's fee policy computes charges, customer total and payout.
    service_price_paise: int = Field(..., ge=5000, le=10_000_000)


class PricingPreviewRequest(_Strict):
    service_price_paise: int = Field(..., ge=1, le=10_000_000)
    origin: Literal["direct", "job"] = "direct"
    organization_id: UUID | None = None


class PricingSimulateRequest(_Strict):
    definition: dict
    sample_service_prices_paise: list[int] = Field(default_factory=list, max_length=50)
    origin: Literal["direct", "job"] = "direct"
    for_organization: bool = False
    include_recorded_bookings: bool = False


class DisputeCreate(_Strict):
    description: str = Field(..., min_length=10, max_length=2000)
    category: Literal[
        "customer_total_differs",
        "worker_payout_differs",
        "unexpected_deduction",
        "payment_evidence_mismatch",
        "receipt_verification_failed",
        "other_booking_issue",
    ] | None = None
    receipt_event_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    _trim = field_validator("description")(_trimmed)


class EarningsRead(BaseModel):
    label: str
    fee_policy: str
    totals: dict
    ledger_totals: dict | None = None
    settlements: list[dict]


# --- jobs ----------------------------------------------------------------------------------


class JobCreate(_Location):
    skill_id: UUID
    title: str = Field(..., min_length=5, max_length=120)
    description: str = Field(..., min_length=10, max_length=2000)
    address_details: str = Field(..., min_length=5, max_length=500)
    starts_at: AwareDatetime
    duration_minutes: int = Field(..., ge=30, le=720)
    budget_paise: int = Field(..., ge=5000, le=10_000_000)
    organization_id: UUID | None = None

    _trim = field_validator("title", "description", "address_details")(_trimmed)


class JobRead(BaseModel):
    id: UUID
    title: str
    description: str
    skill: SkillRead
    locality: str
    starts_at: datetime
    ends_at: datetime
    budget_paise: int
    status: str
    organization_id: UUID | None = None
    organization_name: str | None = None
    distance_km: float | None = None
    is_manager: bool = False
    address_details: str | None = None  # managers only
    application_count: int | None = None  # managers only
    my_application_status: str | None = None  # workers only
    i_declared_skill: bool | None = None  # workers only
    booking_id: UUID | None = None
    is_synthetic_demo: bool = False
    created_at: datetime


class ApplicationCreate(_Strict):
    message: str | None = Field(default=None, max_length=500)


class ApplicationRead(BaseModel):
    id: UUID
    job_id: UUID
    job_title: str
    job_starts_at: datetime
    job_locality: str
    job_budget_paise: int
    status: str
    message: str | None = None
    worker_profile_id: UUID
    worker_display_name: str
    worker_verification_label: str
    worker_distance_km: float | None = None
    booking_id: UUID | None = None
    created_at: datetime


# --- disputes ------------------------------------------------------------------------------


class DisputeResolve(_Strict):
    outcome: Literal["resolved_for_customer", "resolved_for_worker", "no_fault"]
    reason: str = Field(..., min_length=10, max_length=2000)
    ledger_correction: Literal["none", "full_reversal"] = "none"

    _trim = field_validator("reason")(_trimmed)


class DisputeQueueItem(BaseModel):
    id: UUID
    booking_id: UUID
    status: str
    description: str
    opened_by_role: Literal["customer", "worker"]
    category: str | None = None
    related_quote_version: int | None = None
    related_ledger_transaction_id: UUID | None = None
    related_receipt_event_hash: str | None = None
    ledger_correction: str | None = None
    has_simulated_settlement: bool = False
    booking_status: str
    skill_name: str
    locality: str
    starts_at: datetime
    price_paise: int
    customer_display_name: str
    worker_display_name: str
    can_resolve: bool
    outcome: str | None = None
    resolution_reason: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


# --- dev auth ------------------------------------------------------------------------------


class DevTokenRequest(_Strict):
    email: str = Field(..., min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    passcode: str = Field(..., min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    mode: Literal["local-development"] = "local-development"
    warning: str = "Local development identity. Not production authentication."


class OkResponse(BaseModel):
    ok: bool = True

