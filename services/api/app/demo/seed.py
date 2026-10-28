"""Demo seeding engine.

Rules this module follows (and tests/db/test_demo_seed.py checks):
- Every entity is created through the normal application services, so quotes, acceptances, ledger transactions
  and hash-chained events are genuine. Nothing financial is inserted directly.
- The booking state machine is driven with its real actions (accept/start/complete/cancel/decline/dispute).
- Past appointments exist because the service-layer clock is shifted *only while a past slot/job is created*;
  all later transitions, constraints and triggers run unmodified. Event/ledger/checkpoint timestamps stay real
  (seed time) and are never backdated.
- Idempotent: every created row is registered in ``demo_seed_records`` under a stable seed key; if a
  registration is missing (crash between a service commit and its registration) natural-key reconciliation
  adopts the existing row instead of creating a duplicate.
- Real data is never modified: only rows registered (or created) by this module are touched, and new rows only
  use @demo.sahakar.test identities.
"""

from __future__ import annotations

import importlib
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.localities import LOCALITIES
from app.core.security import VerifiedUser
from app.demo import dataset as ds
from app.models.demo import DemoSeedRecord
from app.models.marketplace import (
    AvailabilitySlot,
    Booking,
    Dispute,
    Job,
    JobApplication,
    PlatformReviewer,
    Settlement,
    WorkerServiceSettings,
    AuditEvent,
)
from app.models.organization import Organization, OrganizationMembership
from app.models.service_taxonomy import Skill, WorkerSkill
from app.models.trust import AnchorCheckpoint, FeePolicy, FinancialEvent, LedgerTransaction, PriceQuoteVersion
from app.models.user import User, WorkerProfile
from app.schemas.marketplace import BookingCreate, JobCreate
from app.services import booking_service, dispute_service, job_service, trust_service, worker_setup_service
from app.services import fee_policy_service as fps
from app.services.organization_service import OrganizationService
from app.services.user_service import UserService
from app.services.worker_service import WorkerService
from app.cli import grant_reviewer

IST = timezone(timedelta(hours=5, minutes=30))
LOCALITY = {l.name: l for l in LOCALITIES}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db"}  # "db" is the docker-compose service name
CLOCK_MODULES = (
    "app.services.marketplace_common",
    "app.services.worker_setup_service",
    "app.services.booking_service",
    "app.services.job_service",
    "app.services.dispute_service",
)


# --- safety ----------------------------------------------------------------------------------


class SeedSafetyError(RuntimeError):
    """The environment is not provably the intended local development database."""


@dataclass
class SafetyReport:
    host: str
    port: int | None
    database: str
    app_env: str


def check_safety(database_url: str, app_env: str, allow_database: str | None = None) -> SafetyReport:
    """Fail closed unless this is APP_ENV=development against a local, non-test, non-Supabase PostgreSQL."""
    if (app_env or "").strip().lower() != "development":
        raise SeedSafetyError(f"APP_ENV is '{app_env}', not 'development'. Refusing to seed.")
    try:
        url = make_url(database_url)
    except Exception as exc:  # noqa: BLE001
        raise SeedSafetyError("DATABASE_URL could not be parsed. Refusing to seed.") from exc
    if not url.drivername.startswith("postgresql"):
        raise SeedSafetyError(f"Database driver '{url.drivername}' is not PostgreSQL. Refusing to seed.")
    host = (url.host or "").lower()
    database = url.database or ""
    if "supabase" in host or "pooler" in host or "amazonaws" in host or "neon.tech" in host:
        raise SeedSafetyError(f"Database host '{host}' looks like a managed/remote database. Refusing to seed.")
    if host not in LOCAL_HOSTS:
        raise SeedSafetyError(f"Database host '{host}' is not local (allowed: {', '.join(sorted(LOCAL_HOSTS))}). Refusing to seed.")
    if "test" in database.lower():
        raise SeedSafetyError(f"Database '{database}' looks like the isolated test database. Dev seeds never run there.")
    expected = allow_database or "sahakar_seva"
    if database != expected:
        raise SeedSafetyError(f"Database '{database}' is not the intended development database '{expected}' "
                              f"(pass --allow-database {database} only if you are sure).")
    return SafetyReport(host=host, port=url.port, database=database, app_env=app_env)


def assert_runtime_target(db: Session, report: SafetyReport) -> None:
    """Prove the live connection really is the database named in the URL and that migrations are current."""
    current = db.execute(text("SELECT current_database()")).scalar_one()
    if current != report.database:
        raise SeedSafetyError(f"Connected database '{current}' differs from DATABASE_URL '{report.database}'.")
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.db.testing import alembic_config

    head = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://unused/unused_test")).get_current_head()
    applied = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if applied != head:
        raise SeedSafetyError(f"Database migration is '{applied}', expected head '{head}'. Run: alembic upgrade head.")


# --- helpers ---------------------------------------------------------------------------------


@contextmanager
def service_clock(now: datetime):
    """Shift the service layer's notion of 'now' while a PAST slot/job is created (see module docstring)."""
    saved = []
    for name in CLOCK_MODULES:
        mod = importlib.import_module(name)
        if hasattr(mod, "utcnow"):
            saved.append((mod, mod.utcnow))
            mod.utcnow = lambda n=now: n
    try:
        yield
    finally:
        for mod, fn in saved:
            mod.utcnow = fn


def today_ist() -> datetime:
    return datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)


def at_ist(day: int, hh: int, mm: int = 0) -> datetime:
    return (today_ist() + timedelta(days=day)).replace(hour=hh, minute=mm)


@dataclass
class Ctx:
    db: Session
    created: Counter = field(default_factory=Counter)
    existing: Counter = field(default_factory=Counter)
    skipped: list[str] = field(default_factory=list)
    users: dict[str, User] = field(default_factory=dict)
    skills: dict[str, Skill] = field(default_factory=dict)
    orgs: dict[str, Organization] = field(default_factory=dict)
    workers: dict[str, WorkerProfile] = field(default_factory=dict)
    bookings: dict[str, Booking] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    dispute_ids: dict[str, UUID] = field(default_factory=dict)

    def key(self, name: str) -> str:
        return f"{ds.DATASET}:{name}"


def _lookup(ctx: Ctx, seed_key: str) -> UUID | None:
    return ctx.db.scalar(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.seed_key == ctx.key(seed_key)))


def _register(ctx: Ctx, seed_key: str, etype: str, entity_id: UUID, showcase: str | None = None) -> None:
    if ctx.db.scalar(select(DemoSeedRecord.id).where(DemoSeedRecord.seed_key == ctx.key(seed_key))):
        return
    if ctx.db.scalar(select(DemoSeedRecord.id).where(DemoSeedRecord.entity_type == etype, DemoSeedRecord.entity_id == entity_id)):
        return
    ctx.db.add(DemoSeedRecord(dataset=ds.DATASET, dataset_version=ds.DATASET_VERSION, seed_key=ctx.key(seed_key),
                              entity_type=etype, entity_id=entity_id, showcase_key=showcase))
    ctx.db.commit()


def _done(ctx: Ctx, etype: str, created: bool) -> None:
    (ctx.created if created else ctx.existing)[etype] += 1


# --- steps -----------------------------------------------------------------------------------


def ensure_user(ctx: Ctx, local: str, name: str) -> User:
    addr = ds.email(local)
    existed = ctx.db.scalar(select(User.id).where(func.lower(User.email) == addr)) is not None
    user = UserService.get_or_sync_user(ctx.db, VerifiedUser(sub=f"dev|{addr}", email=addr, display_name_hint=name))
    _register(ctx, f"user:{local}", "user", user.id)
    if local not in ctx.users:
        _done(ctx, "user", not existed)
    ctx.users[local] = user
    return user


def ensure_skills(ctx: Ctx) -> None:
    for s in ctx.db.scalars(select(Skill).where(Skill.slug.in_(ds.SERVICE_SLUGS))):
        ctx.skills[s.slug] = s
    missing = set(ds.SERVICE_SLUGS) - set(ctx.skills)
    if missing:
        raise SeedSafetyError(f"Service taxonomy is not seeded (missing {sorted(missing)}). Run: python -m app.db.seed")


def ensure_default_policy(ctx: Ctx) -> FeePolicy:
    fp = fps.active_policy(ctx.db)
    if fp is None:
        fp = fps.bootstrap_example(ctx.db, get_settings())
        ctx.db.commit()
        ctx.created["fee_policy(default example)"] += 1
    return fp


def ensure_worker(ctx: Ctx, spec: ds.WorkerSpec) -> WorkerProfile:
    user = ensure_user(ctx, spec.local, spec.name)
    profile = WorkerService.get_by_user_id(ctx.db, user.id)
    created = False
    if profile is None:
        profile = WorkerService.create_worker_profile(ctx.db, user.id, spec.name, spec.bio)
        created = True
    _register(ctx, f"worker:{spec.local}", "worker_profile", profile.id)
    _done(ctx, "worker_profile", created)
    for slug in spec.skills:
        try:
            worker_setup_service.add_my_skill(ctx.db, user, ctx.skills[slug].id)
        except ApiError as exc:
            if exc.detail["error"]["code"] != "WORKER_SKILL_EXISTS":
                raise
    if ctx.db.get(WorkerServiceSettings, profile.id) is None:
        loc = LOCALITY[spec.locality]
        worker_setup_service.put_my_settings(ctx.db, user, locality=loc.name, latitude=loc.latitude, longitude=loc.longitude,
                                             radius_km=spec.radius_km, hourly_rate_paise=spec.rate_rupees * 100)
    if spec.restricted and profile.onboarding_status != "restricted":
        profile.onboarding_status = "restricted"  # operator action for a limited test case; no API can do this
        ctx.db.commit()
    ctx.workers[spec.local] = profile
    return profile


def _slot(ctx: Ctx, worker_local: str, key: str, start: datetime, hours: float) -> AvailabilitySlot | None:
    profile, user = ctx.workers[worker_local], ctx.users[worker_local]
    end = start + timedelta(hours=hours)
    existing = ctx.db.scalar(select(AvailabilitySlot).where(AvailabilitySlot.worker_profile_id == profile.id, AvailabilitySlot.starts_at == start))
    if existing is not None:
        _register(ctx, key, "slot", existing.id)
        _done(ctx, "slot", False)
        return existing
    try:
        if start <= datetime.now(timezone.utc):
            with service_clock(start - timedelta(days=1)):
                view = worker_setup_service.add_my_slot(ctx.db, user, start, end)
        else:
            view = worker_setup_service.add_my_slot(ctx.db, user, start, end)
    except ApiError as exc:
        if exc.detail["error"]["code"] == "SLOT_OVERLAP":
            ctx.skipped.append(f"slot {key}: overlaps an existing slot")
            return None
        raise
    slot = ctx.db.get(AvailabilitySlot, view["id"])
    _register(ctx, key, "slot", slot.id)
    _done(ctx, "slot", True)
    return slot


def ensure_worker_slots(ctx: Ctx, spec: ds.WorkerSpec) -> None:
    """Future availability from the worker's pattern; keyed by date so a later re-run tops up new days."""
    for i, (day, hh, mm, hours) in enumerate(ds.PATTERNS[spec.pattern]):
        start = at_ist(day, hh, mm)
        _slot(ctx, spec.local, f"slot:{spec.local}:{start.date().isoformat()}:{hh:02d}{mm:02d}", start, hours)


def ensure_org(ctx: Ctx, spec: ds.OrgSpec) -> Organization:
    owner = ctx.users[spec.owner]
    org_id = _lookup(ctx, f"org:{spec.slug}")
    org = ctx.db.get(Organization, org_id) if org_id else None
    created = False
    if org is None:
        org = ctx.db.scalar(select(Organization).join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
                            .where(Organization.name == spec.name, OrganizationMembership.user_id == owner.id))
    if org is None:
        view = OrganizationService.create_organization_with_owner(ctx.db, owner.id, spec.name, spec.org_type)
        org = ctx.db.get(Organization, view["id"])
        created = True
    _register(ctx, f"org:{spec.slug}", "organization", org.id)
    _done(ctx, "organization", created)
    for roles, members in (("admin", spec.admins), ("member", spec.members)):
        for local in members:
            uid = ctx.users[local].id
            if ctx.db.scalar(select(OrganizationMembership.id).where(OrganizationMembership.organization_id == org.id, OrganizationMembership.user_id == uid)) is None:
                ctx.db.add(OrganizationMembership(organization_id=org.id, user_id=uid, membership_role=roles))
                ctx.db.commit()
    if spec.policy is not None and _lookup(ctx, f"policy:{spec.slug}") is None:
        active = fps.active_policy(ctx.db, org.id)
        if active is None or active.organization_id != org.id:
            fp = fps.create_version(ctx.db, spec.policy, spec.policy_id, organization_id=org.id, note="Demo example for the judge demonstration. Not official pricing.")
            fps.activate(ctx.db, fp)
            ctx.db.commit()
            _register(ctx, f"policy:{spec.slug}", "fee_policy", fp.id)
            _done(ctx, "fee_policy", True)
        else:
            _register(ctx, f"policy:{spec.slug}", "fee_policy", active.id)
            _done(ctx, "fee_policy", False)
    ctx.orgs[spec.slug] = org
    return org


def _booking_payload(worker_local: str, skill_slug: str, locality: str, unit: str, ctx: Ctx, slot_id: UUID, repeat_of: UUID | None = None) -> BookingCreate:
    loc = LOCALITY[locality]
    return BookingCreate(
        worker_profile_id=ctx.workers[worker_local].id, slot_id=slot_id, skill_id=ctx.skills[skill_slug].id,
        locality=loc.name, latitude=loc.latitude, longitude=loc.longitude,
        address_details=ds.SYNTHETIC_ADDRESS.format(unit=unit, locality=loc.name),
        customer_notes="Synthetic demo booking.", repeat_of_booking_id=repeat_of)


def _audit_seed(ctx: Ctx, booking: Booking, seed_key: str) -> None:
    if ctx.db.scalar(select(AuditEvent.id).where(AuditEvent.entity_type == "booking", AuditEvent.entity_id == booking.id, AuditEvent.action == "demo_seeded")):
        return
    ctx.db.add(AuditEvent(entity_type="booking", entity_id=booking.id, actor_user_id=None, action="demo_seeded", details={
        "synthetic_demo": True, "dataset": ds.DATASET, "seed_key": ctx.key(seed_key),
        "note": "Quote acceptances and state transitions on this booking were performed by the demo seed script on behalf of synthetic personas. No human accepted this agreement.",
    }))
    ctx.db.commit()


def advance(ctx: Ctx, booking_id: UUID, customer: User, worker: User, target: str) -> Booking:
    """Drive a booking to ``target`` using only the real transitions; safe to call repeatedly."""
    order = ["requested", "confirmed", "in_progress", "completed"]
    b = ctx.db.get(Booking, booking_id)

    def act(user: User, action: str, qv: int | None = None):
        booking_service.transition(ctx.db, user, booking_id, action, qv)
        ctx.db.refresh(b)

    if target in order:
        while order.index(b.status) < order.index(target):
            nxt = {"requested": ("accept", worker, 1), "confirmed": ("start", worker, None), "in_progress": ("complete", customer, None)}[b.status]
            act(nxt[1], nxt[0], nxt[2])
    elif target == "cancelled":
        if b.status == "requested":
            act(worker, "accept", 1)
        if b.status == "confirmed":
            act(customer, "cancel")
    elif target == "declined":
        if b.status == "requested":
            act(worker, "decline")
    elif target == "disputed":
        while b.status in order[:3]:
            nxt = {"requested": ("accept", worker, 1), "confirmed": ("start", worker, None), "in_progress": ("complete", customer, None)}[b.status]
            act(nxt[1], nxt[0], nxt[2])
    return b


def ensure_direct(ctx: Ctx, spec: ds.DirectSpec) -> Booking:
    seed_key = f"booking:direct:{spec.key}"
    worker_user, customer = ctx.users[spec.worker], ctx.users[spec.customer]
    bid = _lookup(ctx, seed_key)
    created = False
    if bid is None:
        if spec.slot is None:  # in progress "now": a slot that started an hour ago
            start = datetime.now(IST).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            hours = 3.0
        else:
            start, hours = at_ist(spec.slot.day, spec.slot.hh, spec.slot.mm), spec.slot.hours
        slot = _slot(ctx, spec.worker, f"slot:{spec.worker}:booking:{spec.key}", start, hours)
        if slot is None:
            raise SeedSafetyError(f"cannot create slot for booking {spec.key}")
        bid = ctx.db.scalar(select(Booking.id).where(Booking.slot_id == slot.id, Booking.customer_user_id == customer.id))
        if bid is None:
            repeat_of = ctx.bookings[spec.repeat_of].id if spec.repeat_of else None
            payload = _booking_payload(spec.worker, spec.skill, spec.locality, spec.unit, ctx, slot.id, repeat_of)
            if start <= datetime.now(timezone.utc):
                with service_clock(start - timedelta(days=1)):
                    view = booking_service.create_direct_booking(ctx.db, customer, payload)
            else:
                view = booking_service.create_direct_booking(ctx.db, customer, payload)
            bid = view["id"]
            created = True
    _register(ctx, seed_key, "booking", bid, spec.showcase)
    _done(ctx, "booking", created)
    b = advance(ctx, bid, customer, worker_user, spec.target)
    if spec.target == "disputed":
        b = _ensure_dispute(ctx, spec, b, customer)
    _audit_seed(ctx, b, seed_key)
    ctx.bookings[spec.key] = b
    return b


def _ensure_dispute(ctx: Ctx, spec: ds.DirectSpec, b: Booking, customer: User) -> Booking:
    d = ctx.db.scalar(select(Dispute).where(Dispute.booking_id == b.id))
    if d is None:
        dispute_service.open_dispute(ctx.db, customer, b.id, spec.dispute_text, spec.dispute_category)
        d = ctx.db.scalar(select(Dispute).where(Dispute.booking_id == b.id))
        _done(ctx, "dispute", True)
    else:
        _done(ctx, "dispute", False)
    _register(ctx, f"dispute:{spec.key}", "dispute", d.id)
    if spec.resolve_with_reversal and d.status == "open":
        reviewer = ctx.users["reviewer"]
        dispute_service.resolve(ctx.db, reviewer, d.id, "resolved_for_customer",
                                "Demo decision: the recorded simulated settlement is reversed with a new reversing entry. The original entries are kept.",
                                "full_reversal")
    ctx.db.refresh(b)
    return b


def ensure_job(ctx: Ctx, spec: ds.JobSpec) -> Job:
    seed_key = f"job:{spec.slug}"
    poster = ctx.users[spec.poster]
    org = ctx.orgs[spec.org] if spec.org else None
    loc = LOCALITY[spec.locality]
    start = at_ist(spec.day, spec.hh, spec.mm)
    jid = _lookup(ctx, seed_key)
    if jid is None:
        jid = ctx.db.scalar(select(Job.id).where(Job.customer_user_id == poster.id, Job.title == spec.title))
    created = jid is None
    if created:
        payload = JobCreate(skill_id=ctx.skills[spec.skill].id, title=spec.title, description=spec.description, locality=loc.name,
                            latitude=loc.latitude, longitude=loc.longitude, address_details=ds.SYNTHETIC_ADDRESS.format(unit="Site entrance", locality=loc.name),
                            starts_at=start, duration_minutes=int(spec.hours * 60), budget_paise=spec.budget_rupees * 100,
                            organization_id=org.id if org else None)
        with service_clock(min(datetime.now(timezone.utc), start - timedelta(days=1))):
            jid = job_service.create_job(ctx.db, poster, payload)["id"]
    _register(ctx, seed_key, "job", jid)
    _done(ctx, "job", created)
    job = ctx.db.get(Job, jid)
    ctx.jobs[spec.slug] = job
    # applications (through the real eligibility rules)
    for local in spec.applicants:
        a = ctx.db.scalar(select(JobApplication).where(JobApplication.job_id == job.id, JobApplication.worker_profile_id == ctx.workers[local].id))
        is_new = a is None
        if is_new:
            try:
                with service_clock(min(datetime.now(timezone.utc), start - timedelta(days=1))):
                    view = job_service.apply(ctx.db, ctx.users[local], job.id, f"Demo application from {ctx.users[local].display_name}.")
                a = ctx.db.get(JobApplication, view["id"])
            except ApiError as exc:
                ctx.skipped.append(f"application {local}->{spec.slug}: {exc.detail['error']['code']}")
                continue
        _register(ctx, f"application:{spec.slug}:{local}", "application", a.id)
        _done(ctx, "application", is_new)
    # outcome
    if spec.outcome == "cancelled":
        if job.status == "open":
            job_service.cancel_job(ctx.db, poster, job.id)
    elif spec.outcome in ("requested", "confirmed", "completed"):
        bk = ctx.db.scalar(select(Booking).where(Booking.job_id == job.id).order_by(Booking.created_at.desc()))
        created_b = bk is None
        if bk is None:
            a = ctx.db.scalar(select(JobApplication).where(JobApplication.job_id == job.id, JobApplication.worker_profile_id == ctx.workers[spec.selected].id))
            if a is None:
                raise SeedSafetyError(f"job {spec.slug}: selected applicant {spec.selected} has no application (see skipped: {ctx.skipped[-3:]})")
            job_service.select_applicant(ctx.db, poster, job.id, a.id)
            bk = ctx.db.scalar(select(Booking).where(Booking.job_id == job.id).order_by(Booking.created_at.desc()))
        _register(ctx, f"booking:job:{spec.slug}", "booking", bk.id, spec.showcase)
        _done(ctx, "booking", created_b)
        target = {"requested": "requested", "confirmed": "confirmed", "completed": "completed"}[spec.outcome]
        bk = advance(ctx, bk.id, ctx.users[spec.poster], ctx.users[spec.selected], target)
        _audit_seed(ctx, bk, f"booking:job:{spec.slug}")
        ctx.bookings[f"job:{spec.slug}"] = bk
    ctx.db.refresh(job)
    return job


def run_seed(db: Session) -> Ctx:
    """Create/complete the whole dataset. Re-running is a no-op apart from topping up future availability."""
    ctx = Ctx(db=db)
    ensure_skills(ctx)
    ensure_default_policy(ctx)
    for p in ds.PERSONAS:
        ensure_user(ctx, p.local, p.name)
    if grant_reviewer.grant(db, ctx.users["reviewer"], "demo reviewer (judge demonstration)"):
        ctx.created["reviewer_grant"] += 1
    for w in ds.WORKERS:
        ensure_worker(ctx, w)
    for w in ds.WORKERS:
        ensure_worker_slots(ctx, w)
    for o in ds.ORGS:
        ensure_org(ctx, o)
    for spec in ds.DIRECT:           # DIRECT is ordered so a repeat's source booking comes first
        ensure_direct(ctx, spec)
    for spec in ds.JOBS:
        ensure_job(ctx, spec)
    db.commit()
    return ctx


# --- read-only reporting ----------------------------------------------------------------------


def expected_counts() -> dict[str, int]:
    filled = [j for j in ds.JOBS if j.outcome in ("requested", "confirmed", "completed")]
    return {
        "user": len(ds.PERSONAS) + len(ds.WORKERS), "worker_profile": len(ds.WORKERS), "organization": len(ds.ORGS),
        "fee_policy": sum(1 for o in ds.ORGS if o.policy), "job": len(ds.JOBS),
        "application": sum(len(j.applicants) for j in ds.JOBS), "booking": len(ds.DIRECT) + len(filled),
        "dispute": sum(1 for d in ds.DIRECT if d.target == "disputed"),
    }


def registered_counts(db: Session) -> Counter:
    try:
        rows = db.execute(select(DemoSeedRecord.entity_type, func.count()).where(DemoSeedRecord.dataset == ds.DATASET).group_by(DemoSeedRecord.entity_type)).all()
    except Exception:  # table missing => nothing registered (dry-run before migration 0007)
        db.rollback()
        return Counter()
    return Counter({k: v for k, v in rows})


def plan(db: Session) -> list[str]:
    reg, exp = registered_counts(db), expected_counts()
    lines = [f"{k:15s} registered {reg.get(k, 0):3d} / expected {v:3d} -> would create {max(v - reg.get(k, 0), 0)}" for k, v in exp.items()]
    lines.append(f"{'slot':15s} registered {reg.get('slot', 0):3d} (future availability is topped up per day; past/in-progress slots are created per booking)")
    return lines


def _demo_ids(db: Session, etype: str) -> set[UUID]:
    return set(db.scalars(select(DemoSeedRecord.entity_id).where(DemoSeedRecord.entity_type == etype)))


def non_demo_counts(db: Session) -> dict[str, int]:
    """Rows NOT created by this seeder. Must be identical before and after --apply."""
    out = {}
    for name, model, etype in (("users", User, "user"), ("worker_profiles", WorkerProfile, "worker_profile"), ("organizations", Organization, "organization"),
                               ("jobs", Job, "job"), ("bookings", Booking, "booking"), ("disputes", Dispute, "dispute"),
                               ("job_applications", JobApplication, "application"), ("availability_slots", AvailabilitySlot, "slot")):
        total = db.scalar(select(func.count()).select_from(model)) or 0
        out[name] = total - len(_demo_ids(db, etype) & set(db.scalars(select(model.id))))
    out["settlements"] = (db.scalar(select(func.count()).select_from(Settlement)) or 0) - (db.scalar(
        select(func.count()).select_from(Settlement).where(Settlement.booking_id.in_(_demo_ids(db, "booking")))) or 0)
    return out


def status(db: Session) -> dict:
    reg = registered_counts(db)
    booking_ids = _demo_ids(db, "booking")
    by_status = Counter(db.scalars(select(Booking.status).where(Booking.id.in_(booking_ids)))) if booking_ids else Counter()
    settlements = db.scalar(select(func.count()).select_from(Settlement).where(Settlement.booking_id.in_(booking_ids))) if booking_ids else 0
    txs = db.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.booking_id.in_(booking_ids))) if booking_ids else 0
    events = list(db.scalars(select(FinancialEvent.sequence).where(FinancialEvent.booking_id.in_(booking_ids)))) if booking_ids else []
    anchors: Counter = Counter()
    for seq in events:
        cp = db.scalar(select(AnchorCheckpoint.anchor_status).where(AnchorCheckpoint.first_sequence <= seq, AnchorCheckpoint.last_sequence >= seq))
        anchors[cp or "NOT_YET_CHECKPOINTED"] += 1
    open_jobs = db.scalar(select(func.count()).select_from(Job).where(Job.id.in_(_demo_ids(db, "job")), Job.status == "open", Job.starts_at > func.now())) or 0
    return {
        "registered": dict(reg), "expected": expected_counts(), "bookings_by_status": dict(by_status),
        "completed_simulated_settlements": settlements, "ledger_transactions": txs, "demo_financial_events": len(events),
        "event_anchor_state": dict(anchors), "open_future_demo_jobs": open_jobs,
        "complete": all(reg.get(k, 0) >= v for k, v in expected_counts().items()),
    }
