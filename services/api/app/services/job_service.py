"""Job posting and applications (MVP_MARKETPLACE_CONTRACT §7). Selecting an applicant creates a
``requested`` booking that the worker must confirm through the shared booking lifecycle."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import conflict, forbidden, not_found, unprocessable
from app.models.marketplace import ACTIVE_BOOKING_STATUSES, Booking, Job, JobApplication
from app.models.organization import Organization
from app.models.service_taxonomy import Skill
from app.models.user import User, WorkerProfile
from app.repositories import marketplace_repository as mrepo
from app.repositories import service_taxonomy_repository as taxonomy
from app.repositories.worker_repository import get_worker_profile_by_user
from app.services import booking_service, demo_service
from app.services.marketplace_common import (
    JOB_POINT_DECIMALS,
    audit,
    distance_km,
    geo_point,
    managed_organization_ids,
    require_worker_profile,
    round_coord,
    utcnow,
    verification_label,
)
from app.services.worker_setup_service import ensure_discoverable, skill_dict, worker_declares_skill


def _is_manager(db: Session, job: Job, user: User) -> bool:
    if job.customer_user_id == user.id:
        return True
    return job.organization_id is not None and job.organization_id in managed_organization_ids(db, user.id)


def _active_booking_id(db: Session, job_id: UUID) -> UUID | None:
    return db.scalar(
        select(Booking.id).where(Booking.job_id == job_id, Booking.status.in_(ACTIVE_BOOKING_STATUSES + ("completed", "disputed")))
        .order_by(Booking.created_at.desc()).limit(1)
    )


def job_view(db: Session, job: Job, user: User | None, *, distance_m: float | None = None, worker: WorkerProfile | None = None) -> dict:
    manager = user is not None and _is_manager(db, job, user)
    org_name = db.scalar(select(Organization.name).where(Organization.id == job.organization_id)) if job.organization_id else None
    view = {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "skill": skill_dict(job.skill),
        "locality": job.locality,
        "starts_at": job.starts_at,
        "ends_at": job.ends_at,
        "budget_paise": job.budget_paise,
        "status": job.status,
        "organization_id": job.organization_id,
        "organization_name": org_name,
        "distance_km": distance_km(distance_m),
        "is_manager": manager,
        "created_at": job.created_at,
        "booking_id": None,
        "is_synthetic_demo": demo_service.is_demo(db, "job", job.id),
    }
    if manager:
        view["address_details"] = job.address_details
        view["application_count"] = db.scalar(
            select(func.count()).select_from(JobApplication).where(JobApplication.job_id == job.id)
        )
        view["booking_id"] = _active_booking_id(db, job.id)
    if worker is not None:
        view["my_application_status"] = db.scalar(
            select(JobApplication.status).where(JobApplication.job_id == job.id, JobApplication.worker_profile_id == worker.id)
        )
        view["i_declared_skill"] = worker_declares_skill(db, worker.id, job.skill_id)
    return view


def _load_job(db: Session, job_id: UUID) -> Job | None:
    return db.scalar(select(Job).options(joinedload(Job.skill).joinedload(Skill.category)).where(Job.id == job_id))


def create_job(db: Session, user: User, payload) -> dict:
    skill = taxonomy.get_skill_by_id(db, payload.skill_id)
    if skill is None or not skill.is_active or not skill.category.is_active:
        raise unprocessable("SKILL_NOT_AVAILABLE", "That skill does not exist or is not currently offered.")
    if payload.organization_id is not None and payload.organization_id not in managed_organization_ids(db, user.id):
        raise forbidden("Only an owner or admin of that organization can post jobs for it.")
    if payload.starts_at <= utcnow() + timedelta(minutes=30):
        raise unprocessable("INVALID_TIME_RANGE", "The job must start at least 30 minutes from now.")
    lat = round_coord(payload.latitude, JOB_POINT_DECIMALS)
    lng = round_coord(payload.longitude, JOB_POINT_DECIMALS)
    job = Job(
        customer_user_id=user.id,
        organization_id=payload.organization_id,
        skill_id=skill.id,
        title=payload.title,
        description=payload.description,
        locality=payload.locality,
        latitude=lat,
        longitude=lng,
        job_point=geo_point(lat, lng),
        address_details=payload.address_details,
        starts_at=payload.starts_at,
        ends_at=payload.starts_at + timedelta(minutes=payload.duration_minutes),
        budget_paise=payload.budget_paise,
        status="open",
    )
    db.add(job)
    db.flush()
    audit(db, "job", job.id, user.id, "posted", {"budget_paise": payload.budget_paise, "organization_id": str(payload.organization_id) if payload.organization_id else None})
    db.commit()
    return job_view(db, _load_job(db, job.id), user)


def list_my_jobs(db: Session, user: User) -> list[dict]:
    org_ids = managed_organization_ids(db, user.id)
    cond = Job.customer_user_id == user.id
    if org_ids:
        cond = cond | Job.organization_id.in_(org_ids)
    jobs = db.scalars(select(Job).options(joinedload(Job.skill).joinedload(Skill.category)).where(cond).order_by(Job.starts_at.desc()))
    return [job_view(db, j, user) for j in jobs]


def get_job(db: Session, user: User, job_id: UUID) -> dict:
    job = _load_job(db, job_id)
    if job is None:
        raise not_found("Job not found.")
    worker = get_worker_profile_by_user(db, user.id)
    if not _is_manager(db, job, user):
        if job.status != "open":
            applied = worker is not None and db.scalar(
                select(JobApplication.id).where(JobApplication.job_id == job.id, JobApplication.worker_profile_id == worker.id)
            )
            if not applied:
                raise not_found("Job not found.")
    dist = None
    if worker is not None:
        d = mrepo.job_distance_from_worker(db, job.id, worker.id)
        dist = d[0] if d else None
    return job_view(db, job, user, distance_m=dist, worker=worker)


def nearby_jobs(db: Session, user: User, skill_id: UUID | None, locality: str | None) -> list[dict]:
    worker = require_worker_profile(db, user)
    if mrepo.get_service_settings(db, worker.id) is None:
        raise unprocessable("SERVICE_AREA_REQUIRED", "Set your service area on the Earn page to see nearby jobs.")
    rows = mrepo.nearby_open_jobs(db, worker_profile_id=worker.id, user_id=user.id, skill_id=skill_id, locality=locality)
    result = []
    for job_id, dist in rows:
        result.append(job_view(db, _load_job(db, job_id), user, distance_m=dist, worker=worker))
    return result


def cancel_job(db: Session, user: User, job_id: UUID) -> dict:
    job = mrepo.lock_job(db, job_id)
    if job is None or not _is_manager(db, job, user):
        raise not_found("Job not found.")
    if job.status != "open":
        raise conflict("INVALID_TRANSITION", f"Only open jobs can be cancelled (this job is '{job.status}').")
    job.status = "cancelled"
    for app_row in db.scalars(select(JobApplication).where(JobApplication.job_id == job.id, JobApplication.status == "applied")):
        app_row.status = "rejected"
    audit(db, "job", job.id, user.id, "cancelled")
    db.commit()
    return job_view(db, _load_job(db, job_id), user)


# --- applications -----------------------------------------------------------------------


def _application_view(db: Session, a: JobApplication, worker: WorkerProfile, distance_m: float | None = None) -> dict:
    booking_id = db.scalar(select(Booking.id).where(Booking.application_id == a.id).order_by(Booking.created_at.desc()).limit(1))
    return {
        "id": a.id,
        "job_id": a.job_id,
        "job_title": a.job.title,
        "job_starts_at": a.job.starts_at,
        "job_locality": a.job.locality,
        "job_budget_paise": a.job.budget_paise,
        "status": a.status,
        "message": a.message,
        "worker_profile_id": worker.id,
        "worker_display_name": worker.display_name,
        "worker_verification_label": verification_label(worker.onboarding_status),
        "worker_distance_km": distance_km(distance_m),
        "booking_id": booking_id,
        "created_at": a.created_at,
    }


def apply(db: Session, user: User, job_id: UUID, message: str | None) -> dict:
    worker = require_worker_profile(db, user)
    ensure_discoverable(db, worker.id, worker.onboarding_status)
    job = db.get(Job, job_id)
    if job is None:
        raise not_found("Job not found.")
    if job.customer_user_id == user.id or _is_manager(db, job, user):
        raise unprocessable("OWN_JOB", "You cannot apply to a job you manage.")
    if job.status != "open" or job.starts_at <= utcnow():
        raise conflict("JOB_NOT_OPEN", "This job is no longer accepting applications.")
    if not worker_declares_skill(db, worker.id, job.skill_id):
        raise unprocessable("SKILL_NOT_DECLARED", "Declare the required skill on your Earn page before applying.")
    distance = mrepo.job_distance_from_worker(db, job.id, worker.id)
    if distance is None or not distance[1]:
        raise unprocessable("OUTSIDE_SERVICE_AREA", "This job is outside your service radius.")
    application = JobApplication(job_id=job.id, worker_profile_id=worker.id, message=(message or "").strip() or None, status="applied")
    try:
        with db.begin_nested():
            db.add(application)
            db.flush()
        audit(db, "job_application", application.id, user.id, "applied", {"job_id": str(job.id)})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("DUPLICATE_APPLICATION", "You have already applied to this job.") from exc
    db.refresh(application)
    return _application_view(db, application, worker, distance[0])


def list_my_applications(db: Session, user: User) -> list[dict]:
    worker = get_worker_profile_by_user(db, user.id)
    if worker is None:
        return []
    apps = db.scalars(
        select(JobApplication).options(joinedload(JobApplication.job))
        .where(JobApplication.worker_profile_id == worker.id).order_by(JobApplication.created_at.desc())
    )
    return [_application_view(db, a, worker) for a in apps]


def withdraw(db: Session, user: User, application_id: UUID) -> dict:
    worker = require_worker_profile(db, user)
    a = db.get(JobApplication, application_id)
    if a is None or a.worker_profile_id != worker.id:
        raise not_found("Application not found.")
    if a.status != "applied":
        raise conflict("INVALID_TRANSITION", f"Only pending applications can be withdrawn (this one is '{a.status}'). Decline the booking instead.")
    a.status = "withdrawn"
    audit(db, "job_application", a.id, user.id, "withdrawn")
    db.commit()
    db.refresh(a)
    return _application_view(db, a, worker)


def list_applications_for_job(db: Session, user: User, job_id: UUID) -> list[dict]:
    job = db.get(Job, job_id)
    if job is None or not _is_manager(db, job, user):
        raise not_found("Job not found.")
    apps = db.scalars(
        select(JobApplication).options(joinedload(JobApplication.job))
        .where(JobApplication.job_id == job.id).order_by(JobApplication.created_at)
    )
    out = []
    for a in apps:
        worker = db.get(WorkerProfile, a.worker_profile_id)
        d = mrepo.job_distance_from_worker(db, job.id, worker.id)
        out.append(_application_view(db, a, worker, d[0] if d else None))
    return out


def select_applicant(db: Session, user: User, job_id: UUID, application_id: UUID) -> dict:
    job = mrepo.lock_job(db, job_id)
    if job is None or not _is_manager(db, job, user):
        raise not_found("Job not found.")
    if job.status != "open":
        raise conflict("JOB_NOT_OPEN", f"This job is '{job.status}', so an applicant cannot be selected.")
    application = db.get(JobApplication, application_id)
    if application is None or application.job_id != job.id:
        raise not_found("Application not found.")
    if application.status != "applied":
        raise conflict("INVALID_TRANSITION", f"This application is '{application.status}'.")
    worker = db.get(WorkerProfile, application.worker_profile_id)
    if worker.user_id == job.customer_user_id:
        raise unprocessable("SELF_BOOKING", "A job owner cannot be selected for their own job.")
    ensure_discoverable(db, worker.id, worker.onboarding_status)
    try:
        with db.begin_nested():
            booking = booking_service.create_job_booking(db, job, application, user)
            application.status = "selected"
            job.status = "filled"
            audit(db, "job_application", application.id, user.id, "selected", {"booking_id": str(booking.id)})
            db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("JOB_ALREADY_BOOKED", "This job already has an active booking.") from exc
    return booking_service.get_booking(db, db.get(User, job.customer_user_id), booking.id) | {"my_role": "customer"}
