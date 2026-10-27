"""Phase 3A repositories: service categories, skills and worker skill declarations.

Conventions (same as the Phase 2 repositories):
- Functions take an explicit ``Session``; the request owns the session lifecycle.
- Read functions never commit.
- Each write function is one unit of work: it stages inside a SAVEPOINT and commits once;
  on failure it rolls back and raises a typed error from ``app.repositories.exceptions``.
- ``worker_profile_id`` must come from the authenticated caller's own worker profile
  (resolved server-side via ``get_worker_profile_by_user``); never from client input.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.service_taxonomy import ServiceCategory, Skill, WorkerSkill
from app.repositories.exceptions import (
    SkillInactiveError,
    SkillNotFoundError,
    WorkerSkillExistsError,
    WorkerSkillNotFoundError,
)

# --- Categories ------------------------------------------------------------------------


def list_active_categories(db: Session) -> list[ServiceCategory]:
    stmt = select(ServiceCategory).where(ServiceCategory.is_active.is_(True)).order_by(ServiceCategory.name)
    return list(db.scalars(stmt))


def get_category_by_id(db: Session, category_id: UUID) -> ServiceCategory | None:
    return db.get(ServiceCategory, category_id)


def get_category_by_slug(db: Session, slug: str) -> ServiceCategory | None:
    return db.scalar(select(ServiceCategory).where(ServiceCategory.slug == slug.strip().lower()))


# --- Skills ----------------------------------------------------------------------------


def list_active_skills(db: Session, category_id: UUID | None = None) -> list[Skill]:
    """Active skills whose category is also active, optionally filtered by category."""
    stmt = (
        select(Skill)
        .join(ServiceCategory, Skill.category_id == ServiceCategory.id)
        .where(Skill.is_active.is_(True), ServiceCategory.is_active.is_(True))
        .order_by(ServiceCategory.name, Skill.name)
    )
    if category_id is not None:
        stmt = stmt.where(Skill.category_id == category_id)
    return list(db.scalars(stmt))


def list_skills_for_category(db: Session, category_id: UUID) -> list[Skill]:
    return list_active_skills(db, category_id=category_id)


def get_skill_by_id(db: Session, skill_id: UUID) -> Skill | None:
    return db.get(Skill, skill_id)


# --- Worker skills ---------------------------------------------------------------------


def list_worker_skills(db: Session, worker_profile_id: UUID) -> list[WorkerSkill]:
    """All skills a worker has declared, including ones later deactivated by the platform.

    Callers decide whether to display or hide inactive declarations; the rows are kept so
    deactivation never silently deletes worker data.
    """
    stmt = (
        select(WorkerSkill)
        .options(joinedload(WorkerSkill.skill).joinedload(Skill.category))
        .join(Skill, WorkerSkill.skill_id == Skill.id)
        .where(WorkerSkill.worker_profile_id == worker_profile_id)
        .order_by(Skill.name)
    )
    return list(db.scalars(stmt))


def _get_worker_skill(db: Session, worker_profile_id: UUID, skill_id: UUID) -> WorkerSkill | None:
    return db.scalar(
        select(WorkerSkill).where(
            WorkerSkill.worker_profile_id == worker_profile_id, WorkerSkill.skill_id == skill_id
        )
    )


def add_worker_skill(db: Session, worker_profile_id: UUID, skill_id: UUID) -> WorkerSkill:
    """Declare an existing, active skill for a worker profile.

    Raises:
        SkillNotFoundError: skill does not exist.
        SkillInactiveError: skill or its category is inactive.
        WorkerSkillExistsError: worker already declared this skill (including a concurrent insert).
        IntegrityError: other constraint failures, e.g. a nonexistent worker_profile_id.
    """
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise SkillNotFoundError(f"Skill '{skill_id}' does not exist.")
    if not skill.is_active or not skill.category.is_active:
        raise SkillInactiveError(f"Skill '{skill_id}' is not currently available.")
    if _get_worker_skill(db, worker_profile_id, skill_id) is not None:
        raise WorkerSkillExistsError("Worker has already declared this skill.")

    worker_skill = WorkerSkill(worker_profile_id=worker_profile_id, skill_id=skill_id)
    try:
        with db.begin_nested():
            db.add(worker_skill)
            db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _get_worker_skill(db, worker_profile_id, skill_id) is not None:
            raise WorkerSkillExistsError("Worker has already declared this skill.") from exc
        raise
    db.refresh(worker_skill)
    return worker_skill


def remove_worker_skill(db: Session, worker_profile_id: UUID, skill_id: UUID) -> None:
    """Remove one of the worker's own skill declarations.

    Raises WorkerSkillNotFoundError if the worker has not declared the skill. Scoped by
    worker_profile_id, so one worker can never remove another worker's declaration.
    """
    worker_skill = _get_worker_skill(db, worker_profile_id, skill_id)
    if worker_skill is None:
        raise WorkerSkillNotFoundError("Worker has not declared this skill.")
    try:
        db.delete(worker_skill)
        db.commit()
    except Exception:
        db.rollback()
        raise
