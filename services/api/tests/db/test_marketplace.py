"""MVP marketplace integration tests: real PostgreSQL/PostGIS in the isolated test DB, via the HTTP API.

Every test runs in a rolled-back transaction (tests/db/conftest.py), and the session-level leak
check covers all marketplace tables.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.marketplace import AuditEvent, Booking, PlatformReviewer, Settlement
from app.models.organization import OrganizationMembership
from app.models.user import User, WorkerProfile
from app.services.marketplace_common import FeeCapExceededError, compute_fee_split
from marketplace_helpers import HSR, KORAMANGALA, WHITEFIELD, Api, api, at  # noqa: F401


# --- Slice A: skills -----------------------------------------------------------------------


def test_public_taxonomy_lists(api: Api) -> None:
    cats = api.get("/service-categories").json()
    assert {"household-cleaning", "gardening", "furniture-assembly"} <= {c["slug"] for c in cats}
    skills = api.get("/skills", params={"category": "furniture-assembly"}).json()
    assert {s["slug"] for s in skills} == {"desk-assembly", "shelf-assembly"}
    assert api.get("/skills", params={"category": "no-such-category"}).status_code == 404
    assert len(api.get("/localities").json()) >= 5


def test_worker_skill_management_and_errors(api: Api) -> None:
    assert api.post("/worker-profiles/me/skills", None, {"skill_id": api.skill_id("desk-assembly")}).status_code == 401
    # Authenticated user without a worker profile
    r = api.post("/worker-profiles/me/skills", "nobody", {"skill_id": api.skill_id("desk-assembly")})
    assert r.status_code == 404

    api.post("/worker-profiles", "asha", {"display_name": "Asha"})
    r = api.post("/worker-profiles/me/skills", "asha", {"skill_id": api.skill_id("desk-assembly")})
    assert r.status_code == 201
    assert r.json()["is_self_declared"] is True
    assert r.json()["skill"]["slug"] == "desk-assembly"

    dup = api.post("/worker-profiles/me/skills", "asha", {"skill_id": api.skill_id("desk-assembly")})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "WORKER_SKILL_EXISTS"
    bad = api.post("/worker-profiles/me/skills", "asha", {"skill_id": str(uuid.uuid4())})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "SKILL_NOT_AVAILABLE"
    forged = api.post("/worker-profiles/me/skills", "asha", {"skill_id": api.skill_id("plant-care"), "verified": True})
    assert forged.status_code == 422  # no self-certification fields accepted

    assert [s["skill"]["slug"] for s in api.get("/worker-profiles/me/skills", "asha").json()] == ["desk-assembly"]
    assert api.delete(f"/worker-profiles/me/skills/{api.skill_id('desk-assembly')}", "asha").status_code == 204
    assert api.delete(f"/worker-profiles/me/skills/{api.skill_id('desk-assembly')}", "asha").status_code == 404


def test_cannot_modify_another_workers_skills(api: Api) -> None:
    api.make_worker("ravi", slot_hours=None)
    api.post("/worker-profiles", "mallory", {"display_name": "Mallory"})
    # Mallory's request is scoped to her own profile; Ravi's declaration is untouched.
    assert api.delete(f"/worker-profiles/me/skills/{api.skill_id('desk-assembly')}", "mallory").status_code == 404
    assert len(api.get("/worker-profiles/me/skills", "ravi").json()) == 1


# --- Slice B: location and availability ----------------------------------------------------


def test_service_settings_round_worker_location(api: Api) -> None:
    api.post("/worker-profiles", "geo", {"display_name": "Geo"})
    r = api.put(
        "/worker-profiles/me/service-settings",
        "geo",
        {"locality": "Koramangala", "latitude": 12.935271, "longitude": 77.624519, "radius_km": 5, "hourly_rate_paise": 25000},
    )
    assert r.status_code == 200
    assert (r.json()["latitude"], r.json()["longitude"]) == (12.94, 77.62)
    bad = api.put(
        "/worker-profiles/me/service-settings",
        "geo",
        {"locality": "Koramangala", "latitude": 12.9, "longitude": 77.6, "radius_km": 7, "hourly_rate_paise": 25000},
    )
    assert bad.status_code == 422


def test_availability_validation(api: Api) -> None:
    w = api.make_worker("slots")
    s, e = at(3, 11), at(3, 13)  # overlaps 10:00-12:00
    r = api.post("/worker-profiles/me/availability", "slots", {"starts_at": s.isoformat(), "ends_at": e.isoformat()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SLOT_OVERLAP"
    r = api.post("/worker-profiles/me/availability", "slots", {"starts_at": e.isoformat(), "ends_at": s.isoformat()})
    assert r.status_code == 422
    r = api.post("/worker-profiles/me/availability", "slots", {"starts_at": at(-2, 9).isoformat(), "ends_at": at(-2, 11).isoformat()})
    assert r.status_code == 422
    r = api.post("/worker-profiles/me/availability", "slots", {"starts_at": "2030-01-01T10:00:00", "ends_at": "2030-01-01T12:00:00"})
    assert r.status_code == 422  # naive datetimes rejected

    assert api.book("cust", w).status_code == 201
    r = api.delete(f"/worker-profiles/me/availability/{w['slot']['id']}", "slots")
    assert r.status_code == 409 and r.json()["error"]["code"] == "SLOT_IN_USE"


# --- Slice C: discovery --------------------------------------------------------------------


def _search(api: Api, where, *, radius=5, skill="desk-assembly", who=None, **extra):
    _loc, lat, lng = where
    params = {"latitude": lat, "longitude": lng, "radius_km": radius, "skill_id": api.skill_id(skill), **extra}
    r = api.get("/workers/search", who, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_discovery_filters_by_radius_skill_and_eligibility(api: Api, db: Session) -> None:
    near = api.make_worker("near", where=KORAMANGALA, radius_km=5)
    api.make_worker("gardener", where=KORAMANGALA, radius_km=5, skills=("plant-care",))
    restricted = api.make_worker("restricted", where=KORAMANGALA, radius_km=5)
    db.execute(text("UPDATE worker_profiles SET onboarding_status='restricted' WHERE id=:id"), {"id": restricted["profile"]["id"]})

    res = _search(api, HSR)
    names = [r["display_name"] for r in res["results"]]
    assert names == ["Near Worker"]  # skill filter excludes gardener; restricted excluded
    hit = res["results"][0]
    assert 3.0 <= hit["distance_km"] <= 5.0  # worker centre is rounded to ~1 km for privacy
    assert hit["verification_label"].startswith("Not verified")
    assert "latitude" not in hit and "longitude" not in hit  # worker coordinates never exposed
    assert hit["available_slots"][0]["price_paise"] == 60000  # 2 h x Rs 300

    # Whitefield is ~14 km away: outside the worker's 5 km service radius even with a 25 km search.
    assert _search(api, WHITEFIELD, radius=25)["total"] == 0
    # Customer search radius also applies: a 2 km search from HSR excludes a worker ~4.3 km away.
    assert _search(api, HSR, radius=2)["total"] == 0
    # Workers do not see themselves.
    assert _search(api, HSR, who="near")["total"] == 0
    assert near["profile"]["onboarding_status"] == "draft"


def test_discovery_availability_filter(api: Api) -> None:
    w = api.make_worker("avail")
    inside = {"starts_at": at(3, 10).isoformat(), "ends_at": at(3, 11).isoformat()}
    outside = {"starts_at": at(3, 14).isoformat(), "ends_at": at(3, 15).isoformat()}
    assert _search(api, HSR, **inside)["total"] == 1
    assert _search(api, HSR, **outside)["total"] == 0
    booking = api.book("c1", w).json()
    assert api.post(f"/bookings/{booking['id']}/accept", "avail").status_code == 200
    assert _search(api, HSR, **inside)["total"] == 0  # slot now taken by a confirmed booking


# --- Slice E/F: direct hire, lifecycle, settlement -----------------------------------------


def test_direct_hire_full_lifecycle_and_simulated_settlement(api: Api, db: Session) -> None:
    w = api.make_worker("kiran", rate_paise=35000)
    r = api.book("priya", w)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "requested" and b["origin"] == "direct" and b["my_role"] == "customer"
    assert b["price"] == {"price_paise": 70000, "fee_bps": 1000, "fee_paise": 7000, "payout_paise": 63000,
                          "fee_policy": b["price"]["fee_policy"]}
    assert b["address_details"]

    as_worker = api.get(f"/bookings/{b['id']}", "kiran").json()
    assert as_worker["my_role"] == "worker" and as_worker["address_details"] is None
    assert set(as_worker["allowed_actions"]) == {"accept", "decline"}

    # Unrelated users cannot see or act on the booking.
    assert api.get(f"/bookings/{b['id']}", "stranger").status_code == 404
    assert api.post(f"/bookings/{b['id']}/cancel", "stranger").status_code == 404
    # Customer cannot accept on the worker's behalf.
    assert api.post(f"/bookings/{b['id']}/accept", "priya").status_code == 403

    confirmed = api.post(f"/bookings/{b['id']}/accept", "kiran").json()
    assert confirmed["status"] == "confirmed" and confirmed["address_details"]
    assert api.post(f"/bookings/{b['id']}/complete", "priya").status_code == 409  # must start first
    assert api.post(f"/bookings/{b['id']}/start", "kiran").json()["status"] == "in_progress"
    assert api.post(f"/bookings/{b['id']}/complete", "kiran").status_code == 403  # customer confirms completion

    done = api.post(f"/bookings/{b['id']}/complete", "priya").json()
    assert done["status"] == "completed"
    s = done["settlement"]
    assert s["is_simulated"] is True and s["label"] == "SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED"
    assert s["gross_paise"] == s["fee_paise"] + s["payout_paise"] == 70000

    again = api.post(f"/bookings/{b['id']}/complete", "priya")
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_TRANSITION"
    assert db.scalar(select(func.count()).select_from(Settlement).where(Settlement.booking_id == b["id"])) == 1

    earnings = api.get("/earnings/mine", "kiran").json()
    assert earnings["totals"] == {"gross_paise": 70000, "fee_paise": 7000, "payout_paise": 63000, "count": 1, "reconciles": True}
    assert earnings["label"].startswith("SIMULATED PAYMENT")
    assert api.get("/earnings/mine", "priya").json()["totals"]["count"] == 0
    actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == uuid.UUID(b["id"]))))
    assert {"requested", "accept", "start", "complete"} <= actions


def test_booking_guards(api: Api) -> None:
    w = api.make_worker("guard", where=KORAMANGALA, radius_km=2)
    r = api.book("far", w, where=HSR)  # ~4.3 km > 2 km radius
    assert r.status_code == 422 and r.json()["error"]["code"] == "OUTSIDE_SERVICE_AREA"
    r = api.book("guard", w, where=KORAMANGALA)
    assert r.status_code == 422 and r.json()["error"]["code"] == "SELF_BOOKING"
    r = api.book("c", w, where=KORAMANGALA, skill="plant-care")
    assert r.status_code == 422 and r.json()["error"]["code"] == "SKILL_NOT_OFFERED"
    assert api.book("c", w, where=KORAMANGALA).status_code == 201
    r = api.book("c", w, where=KORAMANGALA)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_REQUEST"
    # A client cannot inject its own price.
    body = {"worker_profile_id": w["profile"]["id"], "slot_id": w["slot"]["id"], "skill_id": api.skill_id("desk-assembly"),
            "locality": "Koramangala", "latitude": 12.9352, "longitude": 77.6245, "address_details": "Somewhere 1",
            "price_paise": 1}
    assert api.post("/bookings", "c2", body).status_code == 422


def test_conflicting_bookings_cannot_both_be_confirmed(api: Api, db: Session) -> None:
    w = api.make_worker("busy")
    first = api.book("c1", w).json()
    second = api.book("c2", w).json()
    assert api.post(f"/bookings/{first['id']}/accept", "busy").status_code == 200
    r = api.post(f"/bookings/{second['id']}/accept", "busy")
    assert r.status_code == 409 and r.json()["error"]["code"] == "BOOKING_CONFLICT"
    assert api.get(f"/bookings/{second['id']}", "busy").json()["status"] == "requested"

    # Database-level guarantee independent of application checks: the exclusion constraint.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("UPDATE bookings SET status='confirmed' WHERE id=:id"), {"id": second["id"]})


def test_invalid_transitions(api: Api) -> None:
    w = api.make_worker("trans")
    b = api.book("c", w).json()
    assert api.post(f"/bookings/{b['id']}/start", "trans").status_code == 409
    assert api.post(f"/bookings/{b['id']}/decline", "trans").json()["status"] == "declined"
    assert api.post(f"/bookings/{b['id']}/accept", "trans").status_code == 409
    assert api.post(f"/bookings/{b['id']}/cancel", "c").status_code == 409
    assert api.post(f"/bookings/{b['id']}/teleport", "c").status_code == 422


# --- Slice D: jobs and applications --------------------------------------------------------


def test_job_posting_application_selection_and_confirmation(api: Api, db: Session) -> None:
    worker = api.make_worker("wj", where=KORAMANGALA, radius_km=5, slot_hours=None)
    api.make_worker("wj2", where=KORAMANGALA, radius_km=5, slot_hours=None)
    api.make_worker("noskill", where=KORAMANGALA, radius_km=5, skills=("plant-care",), slot_hours=None)
    api.make_worker("faraway", where=WHITEFIELD, radius_km=2, slot_hours=None)

    job = api.post_job("meena", where=HSR)
    assert job.status_code == 201, job.text
    job = job.json()
    assert job["is_manager"] and job["address_details"]

    nearby = api.get("/jobs/nearby", "wj").json()
    assert [j["id"] for j in nearby] == [job["id"]]
    assert nearby[0]["address_details"] is None and nearby[0]["i_declared_skill"] is True
    assert api.get("/jobs/nearby", "faraway").json() == []

    a1 = api.post(f"/jobs/{job['id']}/applications", "wj", {"message": "Can do it"})
    assert a1.status_code == 201
    dup = api.post(f"/jobs/{job['id']}/applications", "wj", {})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE_APPLICATION"
    assert api.post(f"/jobs/{job['id']}/applications", "noskill", {}).json()["error"]["code"] == "SKILL_NOT_DECLARED"
    assert api.post(f"/jobs/{job['id']}/applications", "faraway", {}).json()["error"]["code"] == "OUTSIDE_SERVICE_AREA"
    a2 = api.post(f"/jobs/{job['id']}/applications", "wj2", {}).json()

    # Only the job manager can see applications or select.
    assert api.get(f"/jobs/{job['id']}/applications", "wj").status_code == 404
    assert api.post(f"/jobs/{job['id']}/applications/{a1.json()['id']}/select", "wj").status_code == 404
    apps = api.get(f"/jobs/{job['id']}/applications", "meena").json()
    assert len(apps) == 2

    booking = api.post(f"/jobs/{job['id']}/applications/{a1.json()['id']}/select", "meena")
    assert booking.status_code == 201, booking.text
    booking = booking.json()
    assert booking["origin"] == "job" and booking["status"] == "requested" and booking["price"]["price_paise"] == 120000
    assert api.post(f"/jobs/{job['id']}/applications/{a2['id']}/select", "meena").json()["error"]["code"] == "JOB_NOT_OPEN"
    assert api.post(f"/applications/{a1.json()['id']}/withdraw", "wj").status_code == 409

    assert api.post(f"/bookings/{booking['id']}/accept", "wj").json()["status"] == "confirmed"
    statuses = {a["worker_display_name"]: a["status"] for a in api.get(f"/jobs/{job['id']}/applications", "meena").json()}
    assert statuses == {"Wj Worker": "selected", "Wj2 Worker": "rejected"}
    assert api.get(f"/jobs/{job['id']}", "meena").json()["status"] == "filled"
    assert worker["profile"]["id"] == booking["worker_profile_id"]


def test_job_decline_reopens_and_withdraw(api: Api) -> None:
    api.make_worker("dw", slot_hours=None)
    api.make_worker("dw2", slot_hours=None)
    job = api.post_job("owner").json()
    a = api.post(f"/jobs/{job['id']}/applications", "dw", {}).json()
    a2 = api.post(f"/jobs/{job['id']}/applications", "dw2", {}).json()
    assert api.post(f"/applications/{a2['id']}/withdraw", "dw2").json()["status"] == "withdrawn"
    booking = api.post(f"/jobs/{job['id']}/applications/{a['id']}/select", "owner").json()
    assert api.post(f"/bookings/{booking['id']}/decline", "dw").json()["status"] == "declined"
    assert api.get(f"/jobs/{job['id']}", "owner").json()["status"] == "open"
    assert api.post(f"/jobs/{job['id']}/cancel", "dw").status_code == 404
    assert api.post(f"/jobs/{job['id']}/cancel", "owner").json()["status"] == "cancelled"


def test_organization_job_permissions(api: Api, db: Session) -> None:
    api.make_worker("orgw", slot_hours=None)
    org = api.post("/organizations", "boss", {"name": "Green Coop", "organization_type": "cooperative"}).json()
    job = api.post_job("boss", org_id=org["id"])
    assert job.status_code == 201 and job.json()["organization_name"] == "Green Coop"
    job = job.json()

    outsider = api.post_job("outsider", org_id=org["id"])
    assert outsider.status_code == 403 and outsider.json()["error"]["code"] == "FORBIDDEN"

    # A plain 'member' cannot manage the organization's jobs; an 'admin' can.
    api.get("/users/me", "member1")
    api.get("/users/me", "admin1")
    for name, role in (("member1", "member"), ("admin1", "admin")):
        user = db.scalar(select(User).where(User.email == f"{name}@marketplace.test"))
        db.add(OrganizationMembership(organization_id=uuid.UUID(org["id"]), user_id=user.id, membership_role=role))
    db.flush()

    a = api.post(f"/jobs/{job['id']}/applications", "orgw", {}).json()
    assert api.get(f"/jobs/{job['id']}/applications", "outsider").status_code == 404
    assert api.get(f"/jobs/{job['id']}/applications", "member1").status_code == 404
    assert len(api.get(f"/jobs/{job['id']}/applications", "admin1").json()) == 1
    assert api.post(f"/jobs/{job['id']}/applications/{a['id']}/select", "admin1").status_code == 201


# --- Slice F: fee policy -------------------------------------------------------------------


def test_fee_cap_and_rounding() -> None:
    assert compute_fee_split(70000, 1000, 1500) == (1000, 7000, 63000)
    assert compute_fee_split(15, 1000, 1500) == (1000, 2, 13)  # 1.5 paise rounds half-up
    with pytest.raises(FeeCapExceededError):
        compute_fee_split(10000, 1600, 1500)
    with pytest.raises(FeeCapExceededError):
        compute_fee_split(10000, 2100, 2500)  # absolute ceiling
    with pytest.raises(ValueError):
        Settings(platform_fee_bps=1600, platform_fee_cap_bps=1500)
    with pytest.raises(ValueError):
        Settings(platform_fee_cap_bps=2500)


def test_database_rejects_bad_money_and_mutating_settlements(api: Api, db: Session) -> None:
    w = api.make_worker("money")
    b = api.book("payer", w).json()
    with pytest.raises(IntegrityError):  # fee above the 2000 bps ceiling
        with db.begin_nested():
            db.execute(text("UPDATE bookings SET fee_bps=2500 WHERE id=:id"), {"id": b["id"]})
    with pytest.raises(IntegrityError):  # breakdown must reconcile
        with db.begin_nested():
            db.execute(text("UPDATE bookings SET fee_paise=fee_paise+1 WHERE id=:id"), {"id": b["id"]})

    api.post(f"/bookings/{b['id']}/accept", "money")
    api.post(f"/bookings/{b['id']}/start", "money")
    api.post(f"/bookings/{b['id']}/complete", "payer")
    with pytest.raises(DBAPIError, match="immutable"):
        with db.begin_nested():
            db.execute(text("UPDATE settlements SET payout_paise=payout_paise+100 WHERE booking_id=:id"), {"id": b["id"]})
    with pytest.raises(IntegrityError):  # duplicate financial record for the same booking
        with db.begin_nested():
            db.add(Settlement(booking_id=uuid.UUID(b["id"]), gross_paise=1, fee_bps=0, fee_paise=0, payout_paise=1))
            db.flush()


# --- Slice G: disputes ---------------------------------------------------------------------


def _completed_booking(api: Api, worker: str, customer: str) -> dict:
    w = api.make_worker(worker)
    b = api.book(customer, w).json()
    api.post(f"/bookings/{b['id']}/accept", worker)
    api.post(f"/bookings/{b['id']}/start", worker)
    api.post(f"/bookings/{b['id']}/complete", customer)
    return b


def _grant(db: Session, api: Api, name: str) -> None:
    api.get("/users/me", name)
    user = db.scalar(select(User).where(User.email == f"{name}@marketplace.test"))
    db.add(PlatformReviewer(user_id=user.id, note="test"))
    db.flush()


def test_dispute_requires_independent_authorised_reviewer(api: Api, db: Session) -> None:
    b = _completed_booking(api, "dwk", "dcu")
    assert api.post(f"/bookings/{b['id']}/disputes", "stranger", {"description": "Not my booking at all"}).status_code == 404
    r = api.post(f"/bookings/{b['id']}/disputes", "dcu", {"description": "Desk was left wobbly and unfinished"})
    assert r.status_code == 201 and r.json()["status"] == "disputed"
    assert r.json()["dispute"]["status"] == "open"
    again = api.post(f"/bookings/{b['id']}/disputes", "dwk", {"description": "Customer changed the scope"})
    assert again.status_code == 409

    assert api.get("/disputes/review-queue", "dcu").status_code == 403
    dispute_id = r.json()["dispute"]["id"]
    body = {"outcome": "resolved_for_customer", "reason": "Photos confirm the desk was incomplete."}
    assert api.post(f"/disputes/{dispute_id}/resolve", "dcu", body).status_code == 403  # not a reviewer

    _grant(db, api, "dwk")  # the worker is a reviewer, but a party to this booking
    assert api.post(f"/disputes/{dispute_id}/resolve", "dwk", body).status_code == 403

    _grant(db, api, "rev")
    queue = api.get("/disputes/review-queue", "rev").json()
    assert queue[0]["can_resolve"] is True and "address_details" not in queue[0]
    resolved = api.post(f"/disputes/{dispute_id}/resolve", "rev", body)
    assert resolved.status_code == 200
    assert resolved.json()["outcome"] == "resolved_for_customer" and resolved.json()["resolution_reason"]
    assert api.post(f"/disputes/{dispute_id}/resolve", "rev", body).status_code == 409

    # No automated sanction: the worker's status is untouched.
    profile = db.scalar(select(WorkerProfile).join(User).where(User.email == "dwk@marketplace.test"))
    assert profile.onboarding_status == "draft"
    seen = api.get(f"/bookings/{b['id']}", "dwk").json()["dispute"]
    assert seen["outcome"] == "resolved_for_customer"
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "dispute")) == 2
    assert db.scalar(select(func.count()).select_from(Booking).where(Booking.status == "disputed")) >= 1
