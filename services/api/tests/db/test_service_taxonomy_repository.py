"""Phase 3A Tasks D/E/F: service taxonomy constraints, repositories and seed."""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.seed import SEED_CATEGORIES, seed_service_taxonomy
from app.models.service_taxonomy import ServiceCategory, Skill, WorkerSkill
from app.models.user import User, WorkerProfile
from app.repositories import service_taxonomy_repository as repo
from app.repositories.exceptions import (
    SkillInactiveError,
    SkillNotFoundError,
    WorkerSkillExistsError,
    WorkerSkillNotFoundError,
)
from app.repositories.user_repository import get_or_create_user_from_verified_identity
from app.repositories.worker_repository import create_worker_profile_for_user


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _category(db: Session, slug: str | None = None, name: str | None = None, active: bool = True) -> ServiceCategory:
    tag = _uid()
    cat = ServiceCategory(slug=slug or f"cat-{tag}", name=name or f"Category {tag}", is_active=active)
    db.add(cat)
    db.flush()
    return cat


def _skill(db: Session, category: ServiceCategory, slug: str | None = None, name: str | None = None, active: bool = True) -> Skill:
    tag = _uid()
    skill = Skill(category_id=category.id, slug=slug or f"skill-{tag}", name=name or f"Skill {tag}", is_active=active)
    db.add(skill)
    db.flush()
    return skill


def _worker(db: Session) -> WorkerProfile:
    tag = _uid()
    user = get_or_create_user_from_verified_identity(
        db, subject=f"sub-{tag}", email=f"w-{tag}@taxonomy.test", display_name_hint="Worker"
    )
    return create_worker_profile_for_user(db, user_id=user.id, display_name="Taxonomy Worker")


def _expect_integrity_error(db: Session, obj) -> None:
    db.add(obj)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# 1-2. Category creation, uniqueness, slug constraints ---------------------------------


def test_category_created_with_defaults(db: Session) -> None:
    cat = _category(db, slug="window-cleaning", name="Window Cleaning")
    db.refresh(cat)
    assert isinstance(cat.id, uuid.UUID)
    assert cat.is_active is True
    assert cat.created_at is not None and cat.updated_at is not None
    assert repo.get_category_by_id(db, cat.id).slug == "window-cleaning"
    assert repo.get_category_by_slug(db, "  WINDOW-CLEANING ").id == cat.id


def test_category_slug_is_unique(db: Session) -> None:
    _category(db, slug="dup-slug", name="First Name")
    _expect_integrity_error(db, ServiceCategory(slug="dup-slug", name="Second Name"))


def test_category_name_is_unique_case_insensitive(db: Session) -> None:
    _category(db, slug="laundry", name="Laundry")
    _expect_integrity_error(db, ServiceCategory(slug="laundry-2", name="LAUNDRY"))


@pytest.mark.parametrize("bad_slug", ["Has-Upper", "has space", "trailing-", "-leading", "double--dash", "under_score", ""])
def test_category_slug_format_enforced(db: Session, bad_slug: str) -> None:
    _expect_integrity_error(db, ServiceCategory(slug=bad_slug, name=f"Name {_uid()}"))


def test_category_blank_name_rejected(db: Session) -> None:
    _expect_integrity_error(db, ServiceCategory(slug=f"blank-{_uid()}", name="   "))


# 3-4. Skills and categories -----------------------------------------------------------


def test_skill_belongs_to_category(db: Session) -> None:
    cat = _category(db)
    skill = _skill(db, cat, slug=f"deep-clean-{_uid()}")
    assert skill.category.id == cat.id
    assert skill in cat.skills
    assert repo.get_skill_by_id(db, skill.id).category_id == cat.id


def test_skill_name_unique_within_category_but_allowed_across_categories(db: Session) -> None:
    cat_a, cat_b = _category(db), _category(db)
    _skill(db, cat_a, name="Polishing")
    _skill(db, cat_b, name="Polishing")  # same name, different category: allowed
    _expect_integrity_error(db, Skill(category_id=cat_a.id, slug=f"pol-{_uid()}", name="polishing"))


def test_skill_slug_globally_unique_and_formatted(db: Session) -> None:
    cat_a, cat_b = _category(db), _category(db)
    _skill(db, cat_a, slug="shared-slug")
    _expect_integrity_error(db, Skill(category_id=cat_b.id, slug="shared-slug", name=f"X {_uid()}"))
    cat_c = _category(db)
    _expect_integrity_error(db, Skill(category_id=cat_c.id, slug="Bad Slug", name=f"Y {_uid()}"))


def test_filter_active_skills_by_category(db: Session) -> None:
    cat_a, cat_b = _category(db), _category(db)
    a1, a2 = _skill(db, cat_a), _skill(db, cat_a)
    a_inactive = _skill(db, cat_a, active=False)
    b1 = _skill(db, cat_b)

    in_a = {s.id for s in repo.list_skills_for_category(db, cat_a.id)}
    assert in_a == {a1.id, a2.id}
    assert a_inactive.id not in in_a
    assert {s.id for s in repo.list_active_skills(db, category_id=cat_b.id)} == {b1.id}
    all_active = {s.id for s in repo.list_active_skills(db)}
    assert {a1.id, a2.id, b1.id} <= all_active and a_inactive.id not in all_active


def test_list_active_categories_excludes_inactive_and_hides_their_skills(db: Session) -> None:
    active, inactive = _category(db), _category(db, active=False)
    hidden = _skill(db, inactive)
    ids = {c.id for c in repo.list_active_categories(db)}
    assert active.id in ids and inactive.id not in ids
    assert hidden.id not in {s.id for s in repo.list_active_skills(db)}


# 5-6. Worker skill declarations -------------------------------------------------------


def test_worker_declares_multiple_skills(db: Session) -> None:
    worker = _worker(db)
    cat_a, cat_b = _category(db), _category(db)
    s1, s2, s3 = _skill(db, cat_a), _skill(db, cat_a), _skill(db, cat_b)
    for s in (s1, s2, s3):
        ws = repo.add_worker_skill(db, worker.id, s.id)
        assert ws.worker_profile_id == worker.id and ws.created_at is not None
    declared = repo.list_worker_skills(db, worker.id)
    assert {ws.skill_id for ws in declared} == {s1.id, s2.id, s3.id}
    assert all(ws.skill.category is not None for ws in declared)
    # Declaring skills never changes the worker's onboarding status (no implied verification).
    db.refresh(worker)
    assert worker.onboarding_status == "draft"
    assert not hasattr(WorkerSkill, "verified") and not hasattr(WorkerSkill, "status")


def test_duplicate_worker_skill_rejected_by_repository_and_database(db: Session) -> None:
    worker = _worker(db)
    skill = _skill(db, _category(db))
    repo.add_worker_skill(db, worker.id, skill.id)
    with pytest.raises(WorkerSkillExistsError):
        repo.add_worker_skill(db, worker.id, skill.id)
    _expect_integrity_error(db, WorkerSkill(worker_profile_id=worker.id, skill_id=skill.id))
    count = db.scalar(select(func.count()).select_from(WorkerSkill).where(WorkerSkill.worker_profile_id == worker.id))
    assert count == 1


def test_worker_skills_are_isolated_per_worker(db: Session) -> None:
    w1, w2 = _worker(db), _worker(db)
    skill = _skill(db, _category(db))
    repo.add_worker_skill(db, w1.id, skill.id)
    assert repo.list_worker_skills(db, w2.id) == []
    with pytest.raises(WorkerSkillNotFoundError):
        repo.remove_worker_skill(db, w2.id, skill.id)  # w2 cannot remove w1's declaration
    assert len(repo.list_worker_skills(db, w1.id)) == 1


def test_remove_worker_skill(db: Session) -> None:
    worker = _worker(db)
    keep, drop = _skill(db, _category(db)), _skill(db, _category(db))
    repo.add_worker_skill(db, worker.id, keep.id)
    repo.add_worker_skill(db, worker.id, drop.id)
    repo.remove_worker_skill(db, worker.id, drop.id)
    assert {ws.skill_id for ws in repo.list_worker_skills(db, worker.id)} == {keep.id}
    assert db.get(Skill, drop.id) is not None  # removing a declaration never deletes the skill
    with pytest.raises(WorkerSkillNotFoundError):
        repo.remove_worker_skill(db, worker.id, drop.id)


# 7. Nonexistent references ------------------------------------------------------------


def test_nonexistent_references_rejected(db: Session) -> None:
    worker = _worker(db)
    with pytest.raises(SkillNotFoundError):
        repo.add_worker_skill(db, worker.id, uuid.uuid4())
    _expect_integrity_error(db, Skill(category_id=uuid.uuid4(), slug=f"orphan-{_uid()}", name="Orphan Skill"))
    skill = _skill(db, _category(db))
    with pytest.raises(IntegrityError):
        repo.add_worker_skill(db, uuid.uuid4(), skill.id)  # nonexistent worker profile


# 8. Inactive skills -------------------------------------------------------------------


def test_cannot_declare_inactive_skill_or_skill_in_inactive_category(db: Session) -> None:
    worker = _worker(db)
    inactive_skill = _skill(db, _category(db), active=False)
    with pytest.raises(SkillInactiveError):
        repo.add_worker_skill(db, worker.id, inactive_skill.id)
    skill_in_inactive_cat = _skill(db, _category(db, active=False))
    with pytest.raises(SkillInactiveError):
        repo.add_worker_skill(db, worker.id, skill_in_inactive_cat.id)
    assert repo.list_worker_skills(db, worker.id) == []


def test_deactivating_skill_preserves_existing_declarations(db: Session) -> None:
    worker = _worker(db)
    skill = _skill(db, _category(db))
    repo.add_worker_skill(db, worker.id, skill.id)
    skill.is_active = False
    db.flush()
    declared = repo.list_worker_skills(db, worker.id)
    assert [ws.skill_id for ws in declared] == [skill.id]
    assert declared[0].skill.is_active is False  # caller can see it is no longer offered
    assert skill.id not in {s.id for s in repo.list_active_skills(db)}
    repo.remove_worker_skill(db, worker.id, skill.id)  # worker can still withdraw it


# 9. Deletion semantics ----------------------------------------------------------------


def test_hard_deleting_declared_skill_or_its_category_is_blocked(db: Session) -> None:
    worker = _worker(db)
    cat = _category(db)
    skill = _skill(db, cat)
    repo.add_worker_skill(db, worker.id, skill.id)
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM skills WHERE id = :id"), {"id": skill.id})
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM service_categories WHERE id = :id"), {"id": cat.id})
    db.rollback()
    assert len(repo.list_worker_skills(db, worker.id)) == 1


def test_deleting_worker_profile_cascades_only_its_declarations(db: Session) -> None:
    w_gone, w_stays = _worker(db), _worker(db)
    skill = _skill(db, _category(db))
    repo.add_worker_skill(db, w_gone.id, skill.id)
    repo.add_worker_skill(db, w_stays.id, skill.id)
    gone_id, stays_id = w_gone.id, w_stays.id
    db.execute(text("DELETE FROM worker_profiles WHERE id = :id"), {"id": gone_id})
    db.expire_all()
    assert repo.list_worker_skills(db, gone_id) == []
    assert len(repo.list_worker_skills(db, stays_id)) == 1
    assert db.get(Skill, skill.id) is not None


# 11. Transaction behaviour ------------------------------------------------------------


def test_failed_add_rolls_back_without_losing_prior_work(db: Session) -> None:
    worker = _worker(db)
    skill = _skill(db, _category(db))
    repo.add_worker_skill(db, worker.id, skill.id)
    with pytest.raises(IntegrityError):
        repo.add_worker_skill(db, uuid.uuid4(), skill.id)
    # Session remains usable and the earlier committed declaration is intact.
    assert [ws.skill_id for ws in repo.list_worker_skills(db, worker.id)] == [skill.id]


def test_reads_do_not_commit(db: Session) -> None:
    pending = ServiceCategory(slug=f"pending-{_uid()}", name=f"Pending {_uid()}")
    db.add(pending)
    db.flush()
    repo.list_active_categories(db)
    repo.list_active_skills(db)
    db.rollback()  # nothing committed by the reads, so the pending row disappears
    assert db.scalar(select(ServiceCategory).where(ServiceCategory.slug == pending.slug)) is None


# Seed ---------------------------------------------------------------------------------


def test_seed_is_idempotent_and_does_not_touch_user_data(db: Session) -> None:
    users_before = db.scalar(select(func.count()).select_from(User))
    first = seed_service_taxonomy(db)
    second = seed_service_taxonomy(db)

    expected_categories = {c.slug for c in SEED_CATEGORIES}
    expected_skills = {s.slug for c in SEED_CATEGORIES for s in c.skills}
    assert set(first.categories_created) == expected_categories
    assert set(first.skills_created) == expected_skills
    assert second.categories_created == [] and second.skills_created == []

    for cat_seed in SEED_CATEGORIES:
        cat = repo.get_category_by_slug(db, cat_seed.slug)
        assert cat is not None and cat.name == cat_seed.name
        assert {s.slug for s in repo.list_skills_for_category(db, cat.id)} == {s.slug for s in cat_seed.skills}
    assert db.scalar(select(func.count()).select_from(ServiceCategory).where(ServiceCategory.slug.in_(expected_categories))) == 3
    assert db.scalar(select(func.count()).select_from(Skill).where(Skill.slug.in_(expected_skills))) == 6
    assert db.scalar(select(func.count()).select_from(User)) == users_before
    assert db.scalar(select(func.count()).select_from(WorkerSkill)) == 0


def test_seed_does_not_reactivate_or_overwrite_existing_rows(db: Session) -> None:
    seed_service_taxonomy(db)
    cat = repo.get_category_by_slug(db, "gardening")
    cat.is_active = False
    cat.description = "Edited by platform"
    db.commit()
    seed_service_taxonomy(db)
    db.refresh(cat)
    assert cat.is_active is False and cat.description == "Edited by platform"


def test_seed_dry_run_writes_nothing(db: Session) -> None:
    result = seed_service_taxonomy(db, dry_run=True)
    assert result.categories_created  # reports what would be created
    assert repo.get_category_by_slug(db, "household-cleaning") is None
