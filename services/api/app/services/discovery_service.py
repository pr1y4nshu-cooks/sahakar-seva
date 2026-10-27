"""Deterministic, explainable worker discovery. No AI, no opaque ranking: results are filtered by
declared skill, service-radius coverage, search radius, eligibility and (optionally) availability,
then ordered by distance."""

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import unprocessable
from app.models.service_taxonomy import ServiceCategory, Skill, WorkerSkill
from app.repositories import marketplace_repository as mrepo
from app.services.marketplace_common import distance_km, price_for_slot, verification_label
from app.services.worker_setup_service import skill_dict

MAX_SEARCH_RADIUS_KM = 25


def search(
    db: Session,
    *,
    latitude: float,
    longitude: float,
    radius_km: float,
    skill_id: UUID | None,
    category_id: UUID | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
    exclude_user_id: UUID | None,
) -> dict:
    if skill_id is None and category_id is None:
        raise unprocessable("SEARCH_CRITERIA_REQUIRED", "Choose a service category or a skill.")
    if not 0 < radius_km <= MAX_SEARCH_RADIUS_KM:
        raise unprocessable("INVALID_RADIUS", f"Search radius must be between 1 and {MAX_SEARCH_RADIUS_KM} km.")
    if (starts_at is None) != (ends_at is None):
        raise unprocessable("INVALID_TIME_RANGE", "Provide both start and end time, or neither.")
    if starts_at is not None and ends_at <= starts_at:
        raise unprocessable("INVALID_TIME_RANGE", "End time must be after start time.")

    rows = mrepo.search_workers(
        db,
        latitude=latitude,
        longitude=longitude,
        search_radius_km=radius_km,
        skill_id=skill_id,
        category_id=category_id,
        starts_at=starts_at,
        ends_at=ends_at,
        exclude_user_id=exclude_user_id,
    )
    ids = [r["worker_profile_id"] for r in rows]

    skills_by_worker: dict[UUID, list[dict]] = defaultdict(list)
    if ids:
        declared = db.scalars(
            select(WorkerSkill)
            .options(joinedload(WorkerSkill.skill).joinedload(Skill.category))
            .join(Skill, Skill.id == WorkerSkill.skill_id)
            .join(ServiceCategory, ServiceCategory.id == Skill.category_id)
            .where(WorkerSkill.worker_profile_id.in_(ids), Skill.is_active.is_(True), ServiceCategory.is_active.is_(True))
            .order_by(Skill.name)
        )
        for ws in declared:
            skills_by_worker[ws.worker_profile_id].append(skill_dict(ws.skill))

    slots_by_worker: dict[UUID, list[dict]] = defaultdict(list)
    rates = {r["worker_profile_id"]: r["hourly_rate_paise"] for r in rows}
    for slot in mrepo.free_slots_for_workers(db, ids, starts_at, ends_at):
        wid = slot["worker_profile_id"]
        if len(slots_by_worker[wid]) < 6:
            slots_by_worker[wid].append(
                {
                    "id": slot["id"],
                    "starts_at": slot["starts_at"],
                    "ends_at": slot["ends_at"],
                    "price_paise": price_for_slot(rates[wid], slot["starts_at"], slot["ends_at"]),
                }
            )

    results = []
    for r in rows:
        wid = r["worker_profile_id"]
        dist = distance_km(r["distance_m"])
        matched = [s["name"] for s in skills_by_worker[wid] if skill_id is None or s["id"] == skill_id]
        reasons = [
            f"Declares {', '.join(matched)} (self-declared)" if matched else "Declares a skill in this category (self-declared)",
            f"About {dist} km away; serves up to {r['radius_km']} km from {r['locality']}",
        ]
        if starts_at is not None:
            reasons.append("Has a free slot covering your requested time")
        results.append(
            {
                "worker_profile_id": wid,
                "display_name": r["display_name"],
                "bio": r["bio"],
                "locality": r["locality"],
                "distance_km": dist,
                "service_radius_km": r["radius_km"],
                "hourly_rate_paise": r["hourly_rate_paise"],
                "onboarding_status": r["onboarding_status"],
                "verification_label": verification_label(r["onboarding_status"]),
                "skills": skills_by_worker[wid],
                "available_slots": slots_by_worker[wid],
                "match_reasons": reasons,
            }
        )
    return {
        "results": results,
        "total": len(results),
        "criteria": {
            "skill_id": str(skill_id) if skill_id else None,
            "category_id": str(category_id) if category_id else None,
            "radius_km": radius_km,
            "time_filter": starts_at is not None,
            "ordering": "distance ascending",
        },
    }
