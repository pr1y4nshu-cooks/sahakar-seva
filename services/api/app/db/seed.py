"""Idempotent development seed for the Phase 3A service taxonomy.

Run (from services/api, after `alembic upgrade head`):
    python -m app.db.seed                # seeds the database in DATABASE_URL
    python -m app.db.seed --dry-run      # show what would change, write nothing

Docker:
    docker compose exec api python -m app.db.seed

Safety:
- Inserts categories/skills only when their slug is missing; never updates or deletes
  existing rows (platform edits such as deactivation are preserved).
- Never touches users, worker profiles, organizations or worker skill declarations.
- Refuses to run when APP_ENV is "production" unless --allow-production is passed.
"""

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_taxonomy import ServiceCategory, Skill


@dataclass(frozen=True)
class SkillSeed:
    slug: str
    name: str
    description: str


@dataclass(frozen=True)
class CategorySeed:
    slug: str
    name: str
    description: str
    skills: tuple[SkillSeed, ...] = field(default_factory=tuple)


# Initial low-risk MVP categories (blueprint §15: higher-risk trades need separate standards).
SEED_CATEGORIES: tuple[CategorySeed, ...] = (
    CategorySeed(
        slug="household-cleaning",
        name="Household Cleaning",
        description="Routine cleaning of homes and living spaces.",
        skills=(
            SkillSeed("basic-home-cleaning", "Basic Home Cleaning", "Dusting, sweeping, mopping and tidying."),
            SkillSeed("kitchen-cleaning", "Kitchen Cleaning", "Cleaning counters, sinks, stovetops and cabinets."),
        ),
    ),
    CategorySeed(
        slug="gardening",
        name="Gardening",
        description="Routine care of gardens, lawns and plants.",
        skills=(
            SkillSeed("garden-maintenance", "Garden Maintenance", "Weeding, raking, watering and light pruning."),
            SkillSeed("plant-care", "Plant Care", "Potting, watering schedules and basic plant health care."),
        ),
    ),
    CategorySeed(
        slug="furniture-assembly",
        name="Furniture Assembly",
        description="Assembling flat-pack and ready-to-assemble furniture.",
        skills=(
            SkillSeed("desk-assembly", "Desk Assembly", "Assembling desks and work tables."),
            SkillSeed("shelf-assembly", "Shelf Assembly", "Assembling bookshelves and freestanding shelving."),
        ),
    ),
)


@dataclass
class SeedResult:
    categories_created: list[str] = field(default_factory=list)
    skills_created: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)


def seed_service_taxonomy(db: Session, *, dry_run: bool = False) -> SeedResult:
    """Insert missing seed categories and skills in a single transaction."""
    result = SeedResult()
    try:
        for cat_seed in SEED_CATEGORIES:
            category = db.scalar(select(ServiceCategory).where(ServiceCategory.slug == cat_seed.slug))
            if category is None:
                category = ServiceCategory(slug=cat_seed.slug, name=cat_seed.name, description=cat_seed.description)
                db.add(category)
                db.flush()
                result.categories_created.append(cat_seed.slug)
            else:
                result.skipped_existing.append(cat_seed.slug)

            for skill_seed in cat_seed.skills:
                existing = db.scalar(select(Skill).where(Skill.slug == skill_seed.slug))
                if existing is None:
                    db.add(
                        Skill(
                            category_id=category.id,
                            slug=skill_seed.slug,
                            name=skill_seed.name,
                            description=skill_seed.description,
                        )
                    )
                    result.skills_created.append(skill_seed.slug)
                else:
                    result.skipped_existing.append(skill_seed.slug)
        db.flush()
        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def main(argv: list[str] | None = None) -> int:
    from app.core.config import get_settings
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    parser.add_argument("--allow-production", action="store_true", help="required when APP_ENV=production")
    args = parser.parse_args(argv)

    if get_settings().app_env.lower() == "production" and not args.allow_production:
        print("Refusing to seed: APP_ENV=production (pass --allow-production to override).", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        result = seed_service_taxonomy(db, dry_run=args.dry_run)
    mode = "DRY RUN — no changes written" if args.dry_run else "committed"
    print(f"Service taxonomy seed ({mode})")
    print(f"  categories created: {result.categories_created or 'none'}")
    print(f"  skills created:     {result.skills_created or 'none'}")
    print(f"  already present:    {len(result.skipped_existing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
