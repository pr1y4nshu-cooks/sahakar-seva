"""Pricing engine unit tests (no database). All rates and amounts are ILLUSTRATIVE test inputs, not pricing."""

import importlib.util
import itertools

import pytest
from pydantic import ValidationError

from app.trust import pricing
from verifier_path import verifier_path

AT = "2026-11-01T10:00:00Z"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_receipt_pricing", verifier_path())
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


verifier = _load_verifier()


def policy(*components, ceiling=2000, promotions=()):
    return pricing.normalize({"label": "Test policy (example)", "is_example": True, "max_total_charge_bps": ceiling,
                              "components": list(components), "promotions": list(promotions)})


def comp(code="fee", kind="platform_fee", bearer="worker", **kw):
    return {"code": code, "kind": kind, "label": code.title(), "bearer": bearer, **kw}


def balanced(ev):
    entries = pricing.ledger_entries(ev)
    debit = sum(e["amount_paise"] for e in entries if e["direction"] == "debit")
    credit = sum(e["amount_paise"] for e in entries if e["direction"] == "credit")
    return debit == credit and all(e["amount_paise"] > 0 for e in entries)


def test_percentage_worker_borne_example() -> None:
    ev = pricing.evaluate(policy(comp(percent_bps=1000), ceiling=1500), 50000, "direct", False, AT)
    assert (ev["customer_total_paise"], ev["worker_payout_paise"], ev["platform_fee_paise"]) == (50000, 45000, 5000)
    ev = pricing.evaluate(policy(comp(percent_bps=1000), ceiling=1500), 70000, "job", False, AT)
    assert (ev["customer_total_paise"], ev["worker_payout_paise"], ev["platform_fee_paise"]) == (70000, 63000, 7000)


def test_fixed_customer_borne_fee_is_added_on_top() -> None:
    p = policy(comp("booking_fee", bearer="customer", fixed_paise=2500))
    assert pricing.pricing_model(p) == "fixed"
    ev = pricing.evaluate(p, 50000, "direct", False, AT)
    assert (ev["service_price_paise"], ev["customer_total_paise"], ev["worker_payout_paise"], ev["platform_fee_paise"]) == (50000, 52500, 50000, 2500)


def test_hybrid_with_min_and_max() -> None:
    p = policy(comp(percent_bps=500, fixed_paise=1000, min_paise=2000, max_paise=6000))
    assert pricing.pricing_model(p) == "hybrid"
    assert pricing.evaluate(p, 10000, "direct", False, AT)["platform_fee_paise"] == 2000      # 500+1000 -> min 2000
    assert pricing.evaluate(p, 50000, "direct", False, AT)["platform_fee_paise"] == 3500      # 2500+1000
    assert pricing.evaluate(p, 200000, "direct", False, AT)["platform_fee_paise"] == 6000     # 11000 -> max 6000


def test_split_bearers_and_processing_charge() -> None:
    p = policy(comp("wfee", bearer="worker", percent_bps=500), comp("cfee", bearer="customer", percent_bps=300),
               comp("proc", kind="processing_charge", bearer="customer", percent_bps=200))
    ev = pricing.evaluate(p, 100000, "direct", False, AT)
    assert ev["customer_total_paise"] == 105000 and ev["worker_payout_paise"] == 95000
    assert ev["platform_fee_paise"] == 8000 and ev["processing_charge_paise"] == 2000
    assert ev["customer_total_paise"] - ev["worker_payout_paise"] == ev["platform_fee_paise"] + ev["processing_charge_paise"]


def test_business_borne_applies_only_to_organization_bookings() -> None:
    p = policy(comp("biz", bearer="business", fixed_paise=3000, organization_bookings="only"))
    assert pricing.evaluate(p, 50000, "job", False, AT)["customer_total_paise"] == 50000
    ev = pricing.evaluate(p, 50000, "job", True, AT)
    assert ev["customer_total_paise"] == 53000 and ev["business_borne_paise"] == 3000
    accounts = {e["account"]: e["amount_paise"] for e in pricing.ledger_entries(ev)}
    assert accounts["simulated_business_payment_clearing"] == 3000 and accounts["simulated_customer_payment_clearing"] == 50000


def test_platform_absorbed_processing_does_not_change_either_party() -> None:
    p = policy(comp(percent_bps=1000), comp("proc", kind="processing_charge", bearer="platform", percent_bps=200))
    ev = pricing.evaluate(p, 50000, "direct", False, AT)
    assert (ev["customer_total_paise"], ev["worker_payout_paise"], ev["platform_borne_paise"]) == (50000, 45000, 1000)
    accounts = {e["account"]: e["amount_paise"] for e in pricing.ledger_entries(ev)}
    assert accounts["simulated_platform_promotion_expense"] == 1000 and accounts["simulated_processing_charge_allocation"] == 1000


def test_promotional_waiver_is_recorded_not_hidden() -> None:
    promo = {"code": "launch", "label": "Launch waiver", "waives": ["fee"], "starts_at": "2026-10-01T00:00:00Z",
             "ends_at": "2026-12-01T00:00:00Z", "max_service_price_paise": 100000}
    p = policy(comp(percent_bps=1000), promotions=[promo])
    inside = pricing.evaluate(p, 50000, "direct", False, AT)
    assert inside["platform_fee_paise"] == 0 and inside["waived_paise"] == 5000 and inside["lines"][0]["waived_by"] == "launch"
    assert pricing.evaluate(p, 50000, "direct", False, "2026-12-01T00:00:00Z")["platform_fee_paise"] == 5000  # window end exclusive
    assert pricing.evaluate(p, 150000, "direct", False, AT)["platform_fee_paise"] == 15000  # above the promo price limit
    assert balanced(inside)


def test_ceiling_refuses_rather_than_clamps() -> None:
    p = policy(comp(fixed_paise=3000), ceiling=1000)
    assert pricing.evaluate(p, 30000, "direct", False, AT)["platform_fee_paise"] == 3000
    with pytest.raises(pricing.PricingError) as exc:
        pricing.evaluate(p, 29999, "direct", False, AT)
    assert exc.value.code == "CHARGE_CEILING_EXCEEDED"


@pytest.mark.parametrize("bad", [
    {"max_total_charge_bps": 2001},                                                       # above the absolute ceiling
    {"components": [comp(kind="tax", bearer="customer", percent_bps=1800)]},              # no tax model
    {"components": [comp(bearer="platform", percent_bps=100)]},                           # platform can't bear its own fee
    {"components": [comp(bearer="business", fixed_paise=1)]},                             # business needs org-only
    {"components": [comp(min_paise=10, max_paise=5)]},
    {"components": [comp(percent_bps=-1)]},
    {"components": [comp(), comp()]},                                                      # duplicate codes
    {"components": [comp()], "promotions": [{"code": "promo", "label": "Promo", "waives": ["nope"]}]},
    {"components": [comp()], "unknown_field": 1},
])
def test_invalid_policies_rejected(bad) -> None:
    base = {"label": "Test policy", "is_example": True, "max_total_charge_bps": 1500, "components": [comp(percent_bps=100)]}
    with pytest.raises((ValidationError, ValueError)):
        pricing.normalize(base | bad)


def test_definition_hash_is_stable_and_sensitive() -> None:
    a = policy(comp(percent_bps=1000))
    assert pricing.definition_hash(a) == pricing.definition_hash(pricing.normalize(a))
    assert pricing.definition_hash(a) != pricing.definition_hash(policy(comp(percent_bps=1001)))
    assert pricing.definition_hash(a) == verifier.policy_hash(a)


POLICIES = [
    policy(comp(percent_bps=1000), ceiling=1500),
    policy(comp("booking_fee", bearer="customer", fixed_paise=2500)),
    policy(comp(percent_bps=500, fixed_paise=1000, min_paise=2000, max_paise=6000)),
    policy(comp("wfee", percent_bps=700), comp("cfee", bearer="customer", fixed_paise=500),
           comp("biz", bearer="business", fixed_paise=700, organization_bookings="only"),
           comp("proc", kind="processing_charge", bearer="platform", percent_bps=150),
           promotions=[{"code": "early", "label": "Early", "waives": ["cfee"], "ends_at": "2026-11-15T00:00:00Z"}]),
]


@pytest.mark.parametrize("p,price,origin,org", list(itertools.product(POLICIES, [10000, 33333, 50000, 999999], ["direct", "job"], [False, True])))
def test_independent_verifier_engine_agrees_and_every_model_balances(p, price, origin, org) -> None:
    try:
        ev = pricing.evaluate(p, price, origin, org, AT)
    except pricing.PricingError:
        assert not verifier.evaluate_policy(p, price, origin, org, AT)["within_ceiling"]
        return
    v = verifier.evaluate_policy(p, price, origin, org, AT)
    assert v["lines"] == ev["lines"]
    assert (v["customer_total_paise"], v["worker_share_paise"], v["platform_fee_paise"], v["additional_charges_paise"], v["fee_bps"]) == (
        ev["customer_total_paise"], ev["worker_payout_paise"], ev["platform_fee_paise"], ev["processing_charge_paise"], ev["effective_charge_bps"])
    assert ev["effective_charge_bps"] <= p["max_total_charge_bps"] <= 2000
    assert ev["customer_total_paise"] - ev["worker_payout_paise"] == ev["platform_fee_paise"] + ev["processing_charge_paise"]
    assert balanced(ev)
