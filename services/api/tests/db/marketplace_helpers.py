"""Shared fixtures/helpers for marketplace integration tests (isolated TEST_DATABASE_URL only)."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import VerifiedUser, get_token_verifier
from app.db.seed import seed_service_taxonomy
from app.main import app
from app.models.service_taxonomy import Skill

# Public neighbourhood centroids (app/core/localities.py)
KORAMANGALA = ("Koramangala", 12.9352, 77.6245)
HSR = ("HSR Layout", 12.9116, 77.6474)  # ~4.3 km from the rounded Koramangala worker centre
WHITEFIELD = ("Whitefield", 12.9698, 77.7500)  # ~14 km from Koramangala


def _verifier(token: str) -> VerifiedUser:
    # Test tokens look like "u:<name>"; anything else is rejected like an invalid token.
    from app.core.security import InvalidTokenException

    if not token.startswith("u:"):
        raise InvalidTokenException()
    name = token[2:]
    return VerifiedUser(sub=f"test|{name}", email=f"{name}@marketplace.test", display_name_hint=name.title())


class Api:
    def __init__(self, client: TestClient, skills: dict[str, Skill]):
        self.c = client
        self.skills = skills

    @staticmethod
    def h(name: str) -> dict[str, str]:
        return {"Authorization": f"Bearer u:{name}"}

    def get(self, path: str, who: str | None = None, **kw):
        return self.c.get(f"/api/v1{path}", headers=self.h(who) if who else {}, **kw)

    def post(self, path: str, who: str | None = None, json: dict | None = None):
        return self.c.post(f"/api/v1{path}", headers=self.h(who) if who else {}, json=json if json is not None else {})

    def put(self, path: str, who: str, json: dict):
        return self.c.put(f"/api/v1{path}", headers=self.h(who), json=json)

    def delete(self, path: str, who: str):
        return self.c.delete(f"/api/v1{path}", headers=self.h(who))

    def skill_id(self, slug: str) -> str:
        return str(self.skills[slug].id)

    def make_worker(
        self,
        name: str,
        *,
        where=KORAMANGALA,
        radius_km: int = 5,
        rate_paise: int = 30000,
        skills=("desk-assembly",),
        slot_hours: tuple[int, int] | None = (10, 12),
        day: int = 3,
    ) -> dict:
        assert self.post("/worker-profiles", name, {"display_name": f"{name.title()} Worker"}).status_code == 201
        for slug in skills:
            assert self.post("/worker-profiles/me/skills", name, {"skill_id": self.skill_id(slug)}).status_code == 201
        locality, lat, lng = where
        r = self.put(
            "/worker-profiles/me/service-settings",
            name,
            {"locality": locality, "latitude": lat, "longitude": lng, "radius_km": radius_km, "hourly_rate_paise": rate_paise},
        )
        assert r.status_code == 200, r.text
        slot = None
        if slot_hours:
            s, e = at(day, slot_hours[0]), at(day, slot_hours[1])
            r = self.post("/worker-profiles/me/availability", name, {"starts_at": s.isoformat(), "ends_at": e.isoformat()})
            assert r.status_code == 201, r.text
            slot = r.json()
        profile = self.get("/worker-profiles/me", name).json()
        return {"profile": profile, "slot": slot}

    def book(self, customer: str, worker: dict, *, where=HSR, skill="desk-assembly", slot_id: str | None = None):
        locality, lat, lng = where
        return self.post(
            "/bookings",
            customer,
            {
                "worker_profile_id": worker["profile"]["id"],
                "slot_id": slot_id or worker["slot"]["id"],
                "skill_id": self.skill_id(skill),
                "locality": locality,
                "latitude": lat,
                "longitude": lng,
                "address_details": "Flat 4B, Example Residency, 5th Cross",
                "customer_notes": "Two IKEA desks",
            },
        )

    def post_job(self, customer: str, *, where=HSR, skill="desk-assembly", day: int = 4, hour: int = 9, budget: int = 120000, org_id=None):
        locality, lat, lng = where
        body = {
            "skill_id": self.skill_id(skill),
            "title": "Assemble a study desk",
            "description": "Need one flat-pack desk assembled, tools available at home.",
            "locality": locality,
            "latitude": lat,
            "longitude": lng,
            "address_details": "House 12, 3rd Main, Sector 2",
            "starts_at": at(day, hour).isoformat(),
            "duration_minutes": 120,
            "budget_paise": budget,
        }
        if org_id:
            body["organization_id"] = org_id
        return self.post("/jobs", customer, body)


def at(day: int, hour: int) -> datetime:
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return (base + timedelta(days=day)).replace(hour=hour)


@pytest.fixture
def api(db: Session) -> Generator[Api, None, None]:
    seed_service_taxonomy(db)
    skills = {s.slug: s for s in db.query(Skill).all()}
    app.dependency_overrides[get_token_verifier] = lambda: _verifier
    try:
        with TestClient(app) as client:
            yield Api(client, skills)
    finally:
        app.dependency_overrides.pop(get_token_verifier, None)
