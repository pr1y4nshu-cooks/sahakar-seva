"""Configurable, versioned pricing engine (fee policy format v1). Pure functions; integer paise only.

A fee policy is a list of *charge components*. Each component states:
- ``kind``: ``platform_fee`` (platform revenue), ``processing_charge`` (modeled pass-through cost), or
  ``tax`` (rejected until an approved tax model exists);
- ``bearer``: who bears it — ``customer`` (added to the customer total), ``worker`` (deducted from the
  worker's payout), ``business`` (added to the total, billed to the organization the booking is for;
  only valid for organization bookings), or ``platform`` (absorbed by the platform; processing only);
- the calculation: ``percent_bps`` of the service price (rounded half up) plus ``fixed_paise``, clamped to
  optional ``min_paise`` / ``max_paise``. Percentage, fixed and hybrid models are all this one formula.
Promotions waive named components inside a time window. The waived amount is recorded, never hidden.

Reconciliation (always enforced):
    customer_total = service_price + Σ customer/business-borne charges
    worker_payout  = service_price − Σ worker-borne charges            (≥ 0)
    customer_total − worker_payout = platform_fee + processing_charges  (party-borne charges)
Safety ceiling: Σ party-borne charges ≤ service_price × max_total_charge_bps / 10000, and
max_total_charge_bps ≤ ABSOLUTE_CHARGE_CEILING_BPS (2000, also a database CHECK). A price that would
breach it is refused, never silently clamped.

The offline verifier (scripts/verify_receipt.py) and the browser verifier re-implement ``evaluate`` and
recompute every committed quote from the policy definition committed alongside it.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.trust import crypto

POLICY_FORMAT = "sahakar-seva/fee-policy/v1"
ABSOLUTE_CHARGE_CEILING_BPS = 2000
BEARERS = ("customer", "worker", "business", "platform")
KINDS = ("platform_fee", "processing_charge", "tax")
_CODE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
MAX_PAISE = 10_000_000


class PricingError(ValueError):
    """The policy cannot price this booking (e.g. it would breach the charge ceiling)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _iso(value: str | None) -> str | None:
    if value is None:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("promotion times must include a timezone")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Component(_Strict):
    code: str
    kind: Literal["platform_fee", "processing_charge", "tax"]
    label: str = Field(..., min_length=2, max_length=80)
    bearer: Literal["customer", "worker", "business", "platform"]
    percent_bps: int = Field(0, ge=0, le=10000)
    fixed_paise: int = Field(0, ge=0, le=MAX_PAISE)
    min_paise: int | None = Field(None, ge=0, le=MAX_PAISE)
    max_paise: int | None = Field(None, ge=0, le=MAX_PAISE)
    applies_to_origins: list[Literal["direct", "job"]] = Field(default_factory=lambda: ["direct", "job"], min_length=1)
    organization_bookings: Literal["any", "only", "never"] = "any"

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not _CODE.match(v):
            raise ValueError("code must be lowercase letters, digits and underscores")
        return v

    @model_validator(mode="after")
    def _rules(self) -> "Component":
        if self.kind == "tax":
            raise ValueError("tax components need an approved legal/tax model; none is configured")
        if self.bearer == "platform" and self.kind != "processing_charge":
            raise ValueError("only processing charges can be borne by the platform")
        if self.bearer == "business" and self.organization_bookings != "only":
            raise ValueError("business-borne components must set organization_bookings='only'")
        if self.min_paise is not None and self.max_paise is not None and self.min_paise > self.max_paise:
            raise ValueError("min_paise must not exceed max_paise")
        if len(set(self.applies_to_origins)) != len(self.applies_to_origins):
            raise ValueError("duplicate origin")
        return self


class Promotion(_Strict):
    code: str
    label: str = Field(..., min_length=2, max_length=120)
    waives: list[str] = Field(..., min_length=1)
    starts_at: str | None = None
    ends_at: str | None = None
    max_service_price_paise: int | None = Field(None, gt=0, le=MAX_PAISE)
    organization_bookings: Literal["any", "only", "never"] = "any"

    _code = field_validator("code")(Component._code.__func__)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _times(cls, v: str | None) -> str | None:
        return _iso(v)

    @model_validator(mode="after")
    def _window(self) -> "Promotion":
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValueError("promotion must end after it starts")
        return self


class PolicyDefinition(_Strict):
    format: Literal["sahakar-seva/fee-policy/v1"] = POLICY_FORMAT
    label: str = Field(..., min_length=3, max_length=160)
    description: str = Field("", max_length=2000)
    is_example: bool
    components: list[Component] = Field(default_factory=list, max_length=10)
    promotions: list[Promotion] = Field(default_factory=list, max_length=10)
    max_total_charge_bps: int = Field(..., ge=0, le=ABSOLUTE_CHARGE_CEILING_BPS)
    # Placeholder for future organization subscription plans. No billing exists; it only labels terms.
    subscription_plan_code: str | None = Field(None, max_length=60)

    @model_validator(mode="after")
    def _refs(self) -> "PolicyDefinition":
        codes = [c.code for c in self.components]
        if len(set(codes)) != len(codes):
            raise ValueError("component codes must be unique")
        if len({p.code for p in self.promotions}) != len(self.promotions):
            raise ValueError("promotion codes must be unique")
        for p in self.promotions:
            unknown = set(p.waives) - set(codes)
            if unknown:
                raise ValueError(f"promotion {p.code} waives unknown components {sorted(unknown)}")
        return self


def normalize(definition: dict[str, Any]) -> dict[str, Any]:
    """Validate and return the canonical dict form (defaults filled, times normalised)."""
    return PolicyDefinition.model_validate(definition).model_dump(mode="json")


def definition_hash(normalized: dict[str, Any]) -> str:
    return crypto.sha256_hex(b"SAHAKAR-SEVA:fee-policy:v1\x00" + crypto.canonical(normalized))


def pricing_model(normalized: dict[str, Any]) -> str:
    """Static description of how party-borne charges are calculated."""
    comps = [c for c in normalized["components"] if c["bearer"] != "platform"]
    if not comps:
        return "no_charge"
    has_pct = any(c["percent_bps"] for c in comps)
    has_fixed = any(c["fixed_paise"] or c["min_paise"] for c in comps)
    if has_pct and has_fixed:
        return "hybrid"
    return "percentage" if has_pct else "fixed"


def _applies(rule: str, for_organization: bool) -> bool:
    return rule == "any" or (rule == "only") == for_organization


def _promotion_for(normalized: dict, code: str, service: int, for_org: bool, at: str) -> dict | None:
    for p in normalized["promotions"]:
        if code not in p["waives"] or not _applies(p["organization_bookings"], for_org):
            continue
        if p["starts_at"] and at < p["starts_at"]:
            continue
        if p["ends_at"] and at >= p["ends_at"]:
            continue
        if p["max_service_price_paise"] is not None and service > p["max_service_price_paise"]:
            continue
        return p
    return None


def evaluated_at(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evaluate(normalized: dict[str, Any], service_price_paise: int, origin: str, for_organization: bool, at: str) -> dict[str, Any]:
    """Price one booking. ``at`` is an evaluated_at() string (it is committed to the quote)."""
    if not isinstance(service_price_paise, int) or not 0 < service_price_paise <= MAX_PAISE:
        raise PricingError("INVALID_PRICE", "The service price must be a positive whole number of paise.")
    lines = []
    for c in normalized["components"]:
        if origin not in c["applies_to_origins"] or not _applies(c["organization_bookings"], for_organization):
            continue
        computed = (service_price_paise * c["percent_bps"] + 5000) // 10000 + c["fixed_paise"]
        if c["min_paise"] is not None:
            computed = max(computed, c["min_paise"])
        if c["max_paise"] is not None:
            computed = min(computed, c["max_paise"])
        promo = _promotion_for(normalized, c["code"], service_price_paise, for_organization, at)
        lines.append({
            "code": c["code"], "kind": c["kind"], "label": c["label"], "bearer": c["bearer"],
            "percent_bps": c["percent_bps"], "fixed_paise": c["fixed_paise"],
            "min_paise": c["min_paise"], "max_paise": c["max_paise"],
            "computed_paise": computed, "amount_paise": 0 if promo else computed,
            "waived_by": promo["code"] if promo else None,
        })
    by = lambda bearers: sum(l["amount_paise"] for l in lines if l["bearer"] in bearers)  # noqa: E731
    customer_borne, business_borne, worker_borne = by(("customer",)), by(("business",)), by(("worker",))
    platform_borne = by(("platform",))
    party_charges = customer_borne + business_borne + worker_borne
    ceiling = normalized["max_total_charge_bps"]
    if party_charges * 10000 > service_price_paise * ceiling:
        raise PricingError(
            "CHARGE_CEILING_EXCEEDED",
            f"Charges of {party_charges} paise would exceed this policy's {ceiling / 100:g}% ceiling for a "
            f"{service_price_paise} paise service. Choose a higher service price.",
        )
    if worker_borne > service_price_paise:
        raise PricingError("CHARGE_CEILING_EXCEEDED", "Worker-borne charges cannot exceed the service price.")
    party = [l for l in lines if l["bearer"] != "platform"]
    return {
        "service_price_paise": service_price_paise,
        "customer_total_paise": service_price_paise + customer_borne + business_borne,
        "worker_payout_paise": service_price_paise - worker_borne,
        "platform_fee_paise": sum(l["amount_paise"] for l in party if l["kind"] == "platform_fee"),
        "processing_charge_paise": sum(l["amount_paise"] for l in party if l["kind"] == "processing_charge"),
        "tax_paise": 0,
        "customer_borne_paise": customer_borne,
        "business_borne_paise": business_borne,
        "worker_borne_paise": worker_borne,
        "platform_borne_paise": platform_borne,
        "waived_paise": sum(l["computed_paise"] for l in lines if l["waived_by"]),
        "effective_charge_bps": -(-party_charges * 10000 // service_price_paise),
        "max_total_charge_bps": ceiling,
        "lines": lines,
    }


def ledger_entries(ev: dict[str, Any]) -> list[dict[str, Any]]:
    """Balanced simulated postings for an evaluated price (also used for legacy snapshots)."""
    customer_part = ev["customer_total_paise"] - ev["business_borne_paise"]
    entries = [{"account": "simulated_customer_payment_clearing", "direction": "debit", "amount_paise": customer_part}]
    if ev["business_borne_paise"]:
        entries.append({"account": "simulated_business_payment_clearing", "direction": "debit", "amount_paise": ev["business_borne_paise"]})
    if ev["platform_borne_paise"]:
        entries.append({"account": "simulated_platform_promotion_expense", "direction": "debit", "amount_paise": ev["platform_borne_paise"]})
    if ev["worker_payout_paise"]:
        entries.append({"account": "simulated_worker_entitlement", "direction": "credit", "amount_paise": ev["worker_payout_paise"]})
    if ev["platform_fee_paise"]:
        entries.append({"account": "simulated_platform_fee_allocation", "direction": "credit", "amount_paise": ev["platform_fee_paise"]})
    processing = ev["processing_charge_paise"] + ev["platform_borne_paise"]
    if processing:
        entries.append({"account": "simulated_processing_charge_allocation", "direction": "credit", "amount_paise": processing})
    return [e for e in entries if e["amount_paise"] > 0]


def describe_component(c: dict[str, Any]) -> str:
    parts = []
    if c["percent_bps"]:
        parts.append(f"{c['percent_bps'] / 100:g}% of the service price")
    if c["fixed_paise"]:
        parts.append(f"₹{c['fixed_paise'] / 100:g} fixed")
    text = " + ".join(parts) or "₹0"
    if c["min_paise"] is not None:
        text += f", at least ₹{c['min_paise'] / 100:g}"
    if c["max_paise"] is not None:
        text += f", at most ₹{c['max_paise'] / 100:g}"
    who = {"customer": "added to the customer total", "worker": "deducted from the worker's payout",
           "business": "added to the total and billed to the organization", "platform": "absorbed by the platform"}[c["bearer"]]
    return f"{text}; {who}"


def example_definition(percent_bps: int, cap_bps: int) -> dict[str, Any]:
    """Illustrative pilot example used only to bootstrap local development and tests. Not official pricing."""
    return normalize({
        "label": f"Illustrative pilot example — {percent_bps / 100:g}% worker-borne platform fee (NOT final pricing)",
        "description": "Example policy for local demos and tests. Final commercial pricing has not been decided.",
        "is_example": True,
        "components": [{"code": "platform_service_fee", "kind": "platform_fee", "label": "Platform service fee",
                        "bearer": "worker", "percent_bps": percent_bps}],
        "max_total_charge_bps": cap_bps,
    })
