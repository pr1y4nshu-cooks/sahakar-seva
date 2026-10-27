"""MVP marketplace routes (docs/contracts/MVP_MARKETPLACE_CONTRACT.md §10)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.v1.error_handler import ContractCompliantRoute
from app.core.config import Settings, get_settings
from app.core.dev_auth import DevAuthError, issue_dev_token
from app.core.errors import ApiError, not_found
from app.core.localities import LOCALITIES
from app.core.security import VerifiedUser, get_current_verified_user, get_token_verifier, http_bearer
from app.db.session import get_db
from app.models.user import User
from app.repositories import service_taxonomy_repository as taxonomy
from app.schemas.error import ErrorResponse
from app.schemas.marketplace import (
    ApplicationCreate,
    ApplicationRead,
    BookingCreate,
    BookingRead,
    CategoryRead,
    DevTokenRequest,
    DevTokenResponse,
    DisputeCreate,
    DisputeQueueItem,
    DisputeResolve,
    EarningsRead,
    JobCreate,
    JobRead,
    LocalityRead,
    ServiceSettingsRead,
    ServiceSettingsUpdate,
    SkillRead,
    SlotCreate,
    SlotRead,
    WorkerSearchResponse,
    WorkerSkillCreate,
    WorkerSkillRead,
)
from app.services import (
    booking_service,
    discovery_service,
    dispute_service,
    job_service,
    worker_setup_service as setup,
)
from app.services.marketplace_common import current_user
from app.services.worker_setup_service import category_dict


def errors(*codes: int) -> dict:
    """Contract error envelope for every declared code; 422 always uses it (never FastAPI's default)."""
    return {c: {"model": ErrorResponse} for c in sorted(set(codes) | {422})}


def me(verified: VerifiedUser = Depends(get_current_verified_user), db: Session = Depends(get_db)) -> User:
    return current_user(db, verified)


def optional_me(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    verifier=Depends(get_token_verifier),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials or not credentials.credentials.strip():
        return None
    return current_user(db, verifier(credentials.credentials.strip()))


R = dict(route_class=ContractCompliantRoute)

# --- public taxonomy ---------------------------------------------------------------------

public = APIRouter(tags=["taxonomy"], **R)


@public.get("/service-categories", response_model=list[CategoryRead], responses=errors(503), summary="List active service categories")
def list_categories(db: Session = Depends(get_db)):
    return [category_dict(c) for c in taxonomy.list_active_categories(db)]


@public.get("/skills", response_model=list[SkillRead], responses=errors(404, 422), summary="List active skills")
def list_skills(
    category_id: UUID | None = None,
    category: str | None = Query(default=None, max_length=80, description="Category slug"),
    db: Session = Depends(get_db),
):
    return setup.list_skills(db, category_id, category)


@public.get("/localities", response_model=list[LocalityRead], responses=errors(), summary="Curated localities for manual location selection")
def list_localities():
    return [l.__dict__ for l in LOCALITIES]


@public.get("/workers/search", response_model=WorkerSearchResponse, responses=errors(401, 422), summary="Find eligible nearby workers")
def search_workers(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=5, gt=0, le=25),
    skill_id: UUID | None = None,
    category_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(optional_me),
):
    return discovery_service.search(
        db,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        skill_id=skill_id,
        category_id=category_id,
        starts_at=starts_at,
        ends_at=ends_at,
        exclude_user_id=viewer.id if viewer else None,
    )


# --- worker onboarding -------------------------------------------------------------------

worker = APIRouter(prefix="/worker-profiles/me", tags=["worker-onboarding"], **R)


@worker.get("/skills", response_model=list[WorkerSkillRead], responses=errors(401, 404, 503))
def my_skills(user: User = Depends(me), db: Session = Depends(get_db)):
    return setup.list_my_skills(db, user)


@worker.post("/skills", response_model=WorkerSkillRead, status_code=201, responses=errors(401, 404, 409, 422, 503))
def add_skill(payload: WorkerSkillCreate, user: User = Depends(me), db: Session = Depends(get_db)):
    return setup.add_my_skill(db, user, payload.skill_id)


@worker.delete("/skills/{skill_id}", status_code=204, responses=errors(401, 404, 503))
def remove_skill(skill_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    setup.remove_my_skill(db, user, skill_id)


@worker.get("/service-settings", response_model=ServiceSettingsRead, responses=errors(401, 404, 503))
def get_service_settings(user: User = Depends(me), db: Session = Depends(get_db)):
    return setup.get_my_settings(db, user)


@worker.put("/service-settings", response_model=ServiceSettingsRead, responses=errors(401, 404, 422, 503))
def put_service_settings(payload: ServiceSettingsUpdate, user: User = Depends(me), db: Session = Depends(get_db)):
    return setup.put_my_settings(db, user, **payload.model_dump())


@worker.get("/availability", response_model=list[SlotRead], responses=errors(401, 404, 503))
def my_slots(user: User = Depends(me), db: Session = Depends(get_db)):
    return setup.list_my_slots(db, user)


@worker.post("/availability", response_model=SlotRead, status_code=201, responses=errors(401, 404, 409, 422, 503))
def add_slot(payload: SlotCreate, user: User = Depends(me), db: Session = Depends(get_db)):
    return setup.add_my_slot(db, user, payload.starts_at, payload.ends_at)


@worker.delete("/availability/{slot_id}", status_code=204, responses=errors(401, 404, 409, 503))
def remove_slot(slot_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    setup.remove_my_slot(db, user, slot_id)


# --- bookings ------------------------------------------------------------------------------

bookings = APIRouter(prefix="/bookings", tags=["bookings"], **R)


@bookings.post("", response_model=BookingRead, status_code=201, responses=errors(401, 404, 409, 422, 503))
def request_booking(payload: BookingCreate, user: User = Depends(me), db: Session = Depends(get_db)):
    return booking_service.create_direct_booking(db, user, payload)


@bookings.get("/mine", response_model=list[BookingRead], responses=errors(401, 503))
def my_bookings(role: Literal["customer", "worker"] | None = None, user: User = Depends(me), db: Session = Depends(get_db)):
    return booking_service.list_my_bookings(db, user, role)


@bookings.get("/{booking_id}", response_model=BookingRead, responses=errors(401, 404, 503))
def get_booking(booking_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    return booking_service.get_booking(db, user, booking_id)


@bookings.post("/{booking_id}/disputes", response_model=BookingRead, status_code=201, responses=errors(401, 404, 409, 422, 503))
def open_dispute(booking_id: UUID, payload: DisputeCreate, user: User = Depends(me), db: Session = Depends(get_db)):
    return dispute_service.open_dispute(db, user, booking_id, payload.description)


@bookings.post("/{booking_id}/{action}", response_model=BookingRead, responses=errors(401, 403, 404, 409, 422, 503))
def booking_action(
    booking_id: UUID,
    action: Literal["accept", "decline", "cancel", "start", "complete"],
    user: User = Depends(me),
    db: Session = Depends(get_db),
):
    return booking_service.transition(db, user, booking_id, action)


# --- jobs and applications ---------------------------------------------------------------

jobs = APIRouter(prefix="/jobs", tags=["jobs"], **R)


@jobs.post("", response_model=JobRead, status_code=201, responses=errors(401, 403, 422, 503))
def post_job(payload: JobCreate, user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.create_job(db, user, payload)


@jobs.get("/mine", response_model=list[JobRead], responses=errors(401, 503))
def my_jobs(user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.list_my_jobs(db, user)


@jobs.get("/nearby", response_model=list[JobRead], responses=errors(401, 404, 422, 503))
def nearby(
    skill_id: UUID | None = None,
    locality: str | None = Query(default=None, max_length=120),
    user: User = Depends(me),
    db: Session = Depends(get_db),
):
    return job_service.nearby_jobs(db, user, skill_id, locality)


@jobs.get("/{job_id}", response_model=JobRead, responses=errors(401, 404, 503))
def get_job(job_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.get_job(db, user, job_id)


@jobs.post("/{job_id}/cancel", response_model=JobRead, responses=errors(401, 404, 409, 503))
def cancel_job(job_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.cancel_job(db, user, job_id)


@jobs.post("/{job_id}/applications", response_model=ApplicationRead, status_code=201, responses=errors(401, 404, 409, 422, 503))
def apply(job_id: UUID, payload: ApplicationCreate, user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.apply(db, user, job_id, payload.message)


@jobs.get("/{job_id}/applications", response_model=list[ApplicationRead], responses=errors(401, 404, 503))
def job_applications(job_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.list_applications_for_job(db, user, job_id)


@jobs.post(
    "/{job_id}/applications/{application_id}/select",
    response_model=BookingRead,
    status_code=201,
    responses=errors(401, 404, 409, 422, 503),
)
def select_applicant(job_id: UUID, application_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.select_applicant(db, user, job_id, application_id)


applications = APIRouter(prefix="/applications", tags=["jobs"], **R)


@applications.get("/mine", response_model=list[ApplicationRead], responses=errors(401, 503))
def my_applications(user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.list_my_applications(db, user)


@applications.post("/{application_id}/withdraw", response_model=ApplicationRead, responses=errors(401, 404, 409, 503))
def withdraw(application_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    return job_service.withdraw(db, user, application_id)


# --- earnings and disputes ---------------------------------------------------------------

money = APIRouter(tags=["earnings"], **R)


@money.get("/earnings/mine", response_model=EarningsRead, responses=errors(401, 503))
def my_earnings(user: User = Depends(me), db: Session = Depends(get_db)):
    return booking_service.earnings(db, user)


disputes = APIRouter(prefix="/disputes", tags=["disputes"], **R)


@disputes.get("/mine", response_model=list[BookingRead], responses=errors(401, 503))
def my_disputes(user: User = Depends(me), db: Session = Depends(get_db)):
    return dispute_service.my_disputes(db, user)


@disputes.get("/reviewer-status", responses=errors(401, 503))
def reviewer_status(user: User = Depends(me), db: Session = Depends(get_db)) -> dict:
    return {"is_dispute_reviewer": dispute_service.is_reviewer(db, user)}


@disputes.get("/review-queue", response_model=list[DisputeQueueItem], responses=errors(401, 403, 503))
def review_queue(user: User = Depends(me), db: Session = Depends(get_db)):
    return dispute_service.review_queue(db, user)


@disputes.post("/{dispute_id}/resolve", response_model=DisputeQueueItem, responses=errors(401, 403, 404, 409, 422, 503))
def resolve(dispute_id: UUID, payload: DisputeResolve, user: User = Depends(me), db: Session = Depends(get_db)):
    return dispute_service.resolve(db, user, dispute_id, payload.outcome, payload.reason)


# --- local development identity ------------------------------------------------------------

dev_auth = APIRouter(prefix="/dev-auth", tags=["dev-auth (local development only)"], **R)


@dev_auth.post("/token", response_model=DevTokenResponse, status_code=status.HTTP_200_OK, responses=errors(401, 404, 422))
def dev_token(payload: DevTokenRequest, settings: Settings = Depends(get_settings)):
    if not settings.dev_auth_enabled:
        raise not_found("Not found.")
    try:
        token, expires = issue_dev_token(settings, payload.email, payload.passcode, payload.display_name)
    except DevAuthError as exc:
        raise ApiError(401, "INVALID_CREDENTIALS", str(exc)) from exc
    return {"access_token": token, "expires_at": expires}


ROUTERS = (public, worker, bookings, jobs, applications, money, disputes, dev_auth)
