"""Fee policy lifecycle and resolution.

Policies are written only from the server side (``python -m app.cli.fee_policy``). Activation retires the
previous active policy of the same scope and is committed to the tamper-evident event chain. Bookings
resolve the policy once, when their quote is created; a later policy change never re-prices them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.organization import Organization
from app.models.trust import FeePolicy
from app.trust import crypto, pricing
from app.trust.chain import append_event, iso

EXAMPLE_POLICY_ID = "illustrative-pilot-example"


class NoActivePolicyError(ApiError):
    def __init__(self) -> None:
        super().__init__(503, "NO_ACTIVE_FEE_POLICY", "No fee policy is active, so bookings cannot be priced. "
                                                      "An operator must activate one (python -m app.cli.fee_policy).")


def definition(fp: FeePolicy) -> dict:
    return json.loads(fp.definition_canonical)


def create_version(db: Session, raw_definition: dict, policy_id: str, *, organization_id: UUID | None = None,
                   note: str | None = None) -> FeePolicy:
    normalized = pricing.normalize(raw_definition)
    if organization_id is not None and db.get(Organization, organization_id) is None:
        raise ValueError("organization not found")
    latest = db.scalar(select(func.max(FeePolicy.version)).where(FeePolicy.policy_id == policy_id)) or 0
    fp = FeePolicy(
        policy_id=policy_id, version=latest + 1, scope="organization" if organization_id else "default",
        organization_id=organization_id, label=normalized["label"], is_example=normalized["is_example"],
        pricing_model=pricing.pricing_model(normalized), max_total_charge_bps=normalized["max_total_charge_bps"],
        definition_canonical=crypto.canonical(normalized).decode("utf-8"),
        definition_hash=pricing.definition_hash(normalized), status="draft", note=note,
    )
    db.add(fp)
    db.flush()
    return fp


def activate(db: Session, fp: FeePolicy) -> FeePolicy:
    if fp.status != "draft":
        raise ValueError(f"only a draft can be activated (this one is {fp.status})")
    now = datetime.now(timezone.utc)
    current = db.scalar(
        select(FeePolicy).where(
            FeePolicy.status == "active", FeePolicy.scope == fp.scope,
            FeePolicy.organization_id.is_(None) if fp.organization_id is None else FeePolicy.organization_id == fp.organization_id,
        ).with_for_update()
    )
    if current is not None:
        current.status, current.retired_at = "retired", now
        db.flush()
    event = append_event(
        db, event_type="fee_policy_activated", booking_id=None, actor_role="system", actor_user_id=None,
        data={
            "fee_policy_record_id": str(fp.id), "policy_id": fp.policy_id, "version": fp.version, "scope": fp.scope,
            "organization_id": str(fp.organization_id) if fp.organization_id else None,
            "definition_hash": fp.definition_hash, "is_example": fp.is_example,
            "replaces": {"policy_id": current.policy_id, "version": current.version} if current else None,
            "activated_at": iso(now),
        },
    )
    fp.status, fp.activated_at, fp.activation_event_id = "active", now, event.id
    db.flush()
    return fp


def active_policy(db: Session, organization_id: UUID | None = None) -> FeePolicy | None:
    if organization_id is not None:
        org = db.scalar(select(FeePolicy).where(FeePolicy.status == "active", FeePolicy.organization_id == organization_id))
        if org is not None:
            return org
    return db.scalar(select(FeePolicy).where(FeePolicy.status == "active", FeePolicy.scope == "default"))


def require_active(db: Session, organization_id: UUID | None = None) -> FeePolicy:
    fp = active_policy(db, organization_id)
    if fp is None:
        raise NoActivePolicyError()
    return fp


def bootstrap_example(db: Session, settings: Settings) -> FeePolicy | None:
    """Local development/tests only: activate the illustrative example if no default policy is active.

    Uses PLATFORM_FEE_BPS / PLATFORM_FEE_CAP_BPS as *example* inputs. Never replaces an active policy.
    """
    if active_policy(db) is not None:
        return None
    fp = create_version(db, pricing.example_definition(settings.platform_fee_bps, settings.platform_fee_cap_bps),
                        EXAMPLE_POLICY_ID, note="Bootstrapped illustrative example for local development. Not official pricing.")
    return activate(db, fp)


def evaluate(fp: FeePolicy, service_price_paise: int, origin: str, for_organization: bool, at: datetime | None = None) -> dict:
    when = pricing.evaluated_at(at or datetime.now(timezone.utc))
    try:
        result = pricing.evaluate(definition(fp), service_price_paise, origin, for_organization, when)
    except pricing.PricingError as exc:
        raise ApiError(422, exc.code, str(exc)) from exc
    return result | {"evaluated_at": when}


def policy_view(fp: FeePolicy) -> dict:
    d = definition(fp)
    return {
        "fee_policy_record_id": fp.id, "policy_id": fp.policy_id, "version": fp.version, "scope": fp.scope,
        "label": fp.label, "description": d["description"], "is_example": fp.is_example, "status": fp.status,
        "pricing_model": fp.pricing_model, "max_total_charge_bps": fp.max_total_charge_bps,
        "absolute_ceiling_bps": pricing.ABSOLUTE_CHARGE_CEILING_BPS,
        "definition_hash": fp.definition_hash, "definition": d,
        "components": [c | {"description": pricing.describe_component(c)} for c in d["components"]],
        "promotions": d["promotions"], "subscription_plan_code": d["subscription_plan_code"],
        "activated_at": fp.activated_at, "retired_at": fp.retired_at,
    }
