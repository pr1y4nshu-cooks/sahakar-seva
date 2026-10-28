"""Phase 3A service taxonomy: categories, skills and worker skill declarations.

A WorkerSkill is a *self-declaration* by a worker. It deliberately carries no verification,
certification or approval state; competence/eligibility is a separate, future process.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Lowercase kebab-case, e.g. "household-cleaning". Enforced in PostgreSQL only (regex operator);
# ddl_if keeps the SQLite-based API test schema creatable.
SLUG_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*$"


class ServiceCategory(Base):
    __tablename__ = "service_categories"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_service_categories_slug"),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="ck_service_categories_slug_format").ddl_if(
            dialect="postgresql"
        ),
        CheckConstraint("length(trim(name)) >= 2", name="ck_service_categories_name_not_blank"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    skills: Mapped[list["Skill"]] = relationship(back_populates="category", passive_deletes="all")


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_skills_slug"),
        Index("ix_skills_category_id", "category_id"),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="ck_skills_slug_format").ddl_if(dialect="postgresql"),
        CheckConstraint("length(trim(name)) >= 2", name="ck_skills_name_not_blank"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # RESTRICT: a category that still has skills cannot be hard-deleted; deactivate it instead.
    category_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("service_categories.id", ondelete="RESTRICT")
    )
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    category: Mapped[ServiceCategory] = relationship(back_populates="skills")


class WorkerSkill(Base):
    __tablename__ = "worker_skills"
    __table_args__ = (
        # Also serves lookups by worker_profile_id (leading column).
        UniqueConstraint("worker_profile_id", "skill_id", name="uq_worker_skills_worker_profile_skill"),
        Index("ix_worker_skills_skill_id", "skill_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # CASCADE: declarations belong to the worker profile and disappear with it.
    worker_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("worker_profiles.id", ondelete="CASCADE")
    )
    # RESTRICT: a skill that workers have declared cannot be hard-deleted; deactivate it instead.
    skill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    skill: Mapped[Skill] = relationship()


# Case-insensitive name uniqueness (functional indexes must reference mapped columns).
Index("uq_service_categories_name_lower", func.lower(ServiceCategory.name), unique=True)
Index("uq_skills_category_name_lower", Skill.category_id, func.lower(Skill.name), unique=True)
