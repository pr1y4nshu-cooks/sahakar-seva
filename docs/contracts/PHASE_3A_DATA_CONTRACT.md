# SAHAKAR–SEVA — Phase 3A Data Contract: Service Taxonomy

**Contract ID:** SS-P3A-DATA-2026-10-27
**Owner:** Shresth (database). **Reviewer required before API work:** Priyanshu (backend). **FYI:** Dhwanit (frontend).
**Status:** Database layer implemented and tested on `shresthBranch`. The API proposals in §7 are **NOT YET FROZEN**.
**Migration:** `0003_skills_and_categories` (down revision `0002_phase2_constraints`).
**Does not change:** `docs/contracts/phase2.openapi.yaml`, any Phase 2 table, route, schema, or migration.

---

## 1. Purpose and product rules

The taxonomy lets a worker declare the physical, local services they offer, so that future discovery can filter by skill (blueprint R3, R6; Phase 3 roadmap).

- **A declaration is not verification.** A `worker_skills` row means "this worker says they offer this skill". It has no verified, certified, approved, or level field, and adding one does not change `worker_profiles.onboarding_status`. Competence, eligibility, and category approval will be a separate, explicitly designed process, with human review for higher-risk categories (blueprint R2, R8, §15).
- **Low-risk categories first.** The initial seed contains Household Cleaning, Gardening, and Furniture Assembly only. Higher-risk trades (electrical, plumbing, caregiving, and similar) must not be added to the seed without the safety standards required by blueprint §15.
- **One account, two roles.** Skills attach to `worker_profiles` (the optional "Earn" capability), never to `users` directly.

## 2. Entities

All primary keys are UUID v4 strings on the wire (PostgreSQL `uuid`). Timestamps are `timestamptz`, set by the server (`now()`), and serialized as ISO 8601 UTC.

### 2.1 `service_categories` — `ServiceCategory`

| Field | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | app `uuid4` | PK |
| `slug` | varchar(80) | no | — | Stable public identifier. Unique. Format below. |
| `name` | varchar(120) | no | — | Display name. Unique case-insensitively. At least 2 non-blank characters. |
| `description` | text | yes | — | Plain text; never rendered as HTML |
| `is_active` | boolean | no | `true` | Inactive categories are hidden from listings |
| `created_at` / `updated_at` | timestamptz | no | `now()` | |

### 2.2 `skills` — `Skill`

| Field | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | app `uuid4` | PK |
| `category_id` | uuid | no | — | FK → `service_categories.id`, **ON DELETE RESTRICT** |
| `slug` | varchar(80) | no | — | **Globally** unique, so it can be used alone in URLs or filters |
| `name` | varchar(120) | no | — | Unique case-insensitively **within a category**; the same name is allowed in different categories |
| `description` | text | yes | — | Plain text |
| `is_active` | boolean | no | `true` | |
| `created_at` / `updated_at` | timestamptz | no | `now()` | |

### 2.3 `worker_skills` — `WorkerSkill`

| Field | Type | Null | Notes |
|---|---|---|---|
| `id` | uuid | no | PK |
| `worker_profile_id` | uuid | no | FK → `worker_profiles.id`, **ON DELETE CASCADE** |
| `skill_id` | uuid | no | FK → `skills.id`, **ON DELETE RESTRICT** |
| `created_at` | timestamptz | no | When the worker declared it |

There is intentionally no `updated_at` (rows are inserted or deleted, never edited) and no verification or status column.

### 2.4 Constraints and indexes (names are stable and asserted by tests)

| Name | Definition |
|---|---|
| `uq_service_categories_slug` | UNIQUE (`slug`) |
| `uq_service_categories_name_lower` | UNIQUE INDEX (`lower(name)`) |
| `ck_service_categories_slug_format` | `slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'` |
| `ck_service_categories_name_not_blank` | `length(trim(name)) >= 2` |
| `uq_skills_slug` | UNIQUE (`slug`) |
| `uq_skills_category_name_lower` | UNIQUE INDEX (`category_id`, `lower(name)`) |
| `ck_skills_slug_format`, `ck_skills_name_not_blank` | Same rules as for categories |
| `ix_skills_category_id` | INDEX (`category_id`) |
| `skills_category_id_fkey` | FK RESTRICT |
| `uq_worker_skills_worker_profile_skill` | UNIQUE (`worker_profile_id`, `skill_id`). Also serves lookups by worker. |
| `ix_worker_skills_skill_id` | INDEX (`skill_id`), for future "workers offering skill X" discovery |
| `worker_skills_worker_profile_id_fkey` | FK CASCADE |
| `worker_skills_skill_id_fkey` | FK RESTRICT |

## 3. Naming rules

- **Slug:** lowercase ASCII kebab-case (`household-cleaning`), at most 80 characters, no leading, trailing, or double hyphens. Slugs are **permanent identifiers**. Do not rename a slug that clients may already store. Change the display `name` instead, or deactivate the row and create a new one.
- **Name:** human-readable Title Case, 2–120 characters, unique as described in §2.
- APIs and the frontend should key on `id` or `slug`, never on `name`.

## 4. Lifecycle and deletion semantics

| Action | Behaviour | Rationale |
|---|---|---|
| Deactivate a skill or category (`is_active=false`) | Hidden from active listings. New declarations are rejected. **Existing declarations are kept** and still returned by `list_worker_skills`, where the caller can see `skill.is_active=false`. The worker can still remove it. | Never silently delete worker data |
| Hard-delete a skill that any worker declared | **Blocked** (FK RESTRICT) | Prevents corrupting worker data; deactivate instead |
| Hard-delete a category that still has skills | **Blocked** (FK RESTRICT) | Same |
| Delete a worker profile (or its user, via the existing cascade) | That worker's `worker_skills` rows are deleted (CASCADE). Skills and categories are unaffected. | Declarations belong to the worker |
| Worker removes a declaration | Deletes only that row, scoped to their own `worker_profile_id` | |

## 5. Repository interface (`app.repositories.service_taxonomy_repository`)

These follow the Phase 2 conventions. Each function takes an explicit `Session`, owned by the request. Reads never commit. Each write is one unit of work: it stages inside a SAVEPOINT and commits once. On failure it rolls back and raises a typed error.

```python
# Categories
list_active_categories(db: Session) -> list[ServiceCategory]                    # ordered by name
get_category_by_id(db: Session, category_id: UUID) -> ServiceCategory | None
get_category_by_slug(db: Session, slug: str) -> ServiceCategory | None          # slug trimmed + lowercased

# Skills (only active skills in active categories are listed)
list_active_skills(db: Session, category_id: UUID | None = None) -> list[Skill]  # ordered by category, name
list_skills_for_category(db: Session, category_id: UUID) -> list[Skill]
get_skill_by_id(db: Session, skill_id: UUID) -> Skill | None                    # returns inactive skills too

# Worker skills
list_worker_skills(db: Session, worker_profile_id: UUID) -> list[WorkerSkill]   # eager-loads skill + category; includes inactive
add_worker_skill(db: Session, worker_profile_id: UUID, skill_id: UUID) -> WorkerSkill
remove_worker_skill(db: Session, worker_profile_id: UUID, skill_id: UUID) -> None
```

### Typed errors (`app.repositories.exceptions`) and proposed HTTP mapping

| Exception | Raised by | Proposed HTTP / code (NOT FROZEN) |
|---|---|---|
| `SkillNotFoundError` | `add_worker_skill`: skill does not exist | 404 `RESOURCE_NOT_FOUND` (or 422 if the ID arrives in the body; Priyanshu to decide) |
| `SkillInactiveError` | `add_worker_skill`: skill or its category is inactive | 422 `SKILL_NOT_AVAILABLE` (new code) |
| `WorkerSkillExistsError` | `add_worker_skill`: already declared, including a concurrent insert | 409 `WORKER_SKILL_EXISTS` (new code) |
| `WorkerSkillNotFoundError` | `remove_worker_skill`: not declared by this worker | 404 `RESOURCE_NOT_FOUND` |
| `ServiceCategoryNotFoundError` | Reserved for service-layer lookups (repository getters return `None`) | 404 `RESOURCE_NOT_FOUND` |
| `IntegrityError` (SQLAlchemy) | `add_worker_skill` with a nonexistent `worker_profile_id`; should never happen if the service resolves the profile first | 500 `INTERNAL_ERROR` |

### Mandatory security rule for the service layer

`worker_profile_id` **must never come from the client.** The service resolves it from the authenticated identity: `user = UserService.get_or_sync_user(...)`, then `profile = get_worker_profile_by_user(db, user.id)`. If no profile exists, return 404 `RESOURCE_NOT_FOUND`, the same as `GET /worker-profiles/me`. The client sends only `skill_id`.

## 6. Seed data (development)

Run `python -m app.db.seed` (or `docker compose exec api python -m app.db.seed`) after `alembic upgrade head`. `--dry-run` shows what would change. The command refuses to run with `APP_ENV=production` unless `--allow-production` is passed.

- **Insert-only by slug:** it never updates, reactivates, or deletes existing rows, and never touches users, worker profiles, organizations, or `worker_skills`.
- **Seeded rows:**

| Category slug | Skill slugs |
|---|---|
| `household-cleaning` | `basic-home-cleaning`, `kitchen-cleaning` |
| `gardening` | `garden-maintenance`, `plant-care` |
| `furniture-assembly` | `desk-assembly`, `shelf-assembly` |

Frontend and backend fixtures should use these slugs.

## 7. Proposed future API — **NOT YET FROZEN**

This is a proposal for Priyanshu (contract owner) to review. Nothing here is implemented. A Phase 3 OpenAPI contract must be frozen and acknowledged by all three owners first. These would be additive and would not change any Phase 2 route.

| Method | Path | Auth | Request | Success | Errors |
|---|---|---|---|---|---|
| GET | `/api/v1/service-categories` | Public (proposed) | — | 200 `ServiceCategory[]` (active only) | 503 |
| GET | `/api/v1/skills?category_id=<uuid>` or `?category=<slug>` | Public (proposed) | — | 200 `Skill[]` (active only) | 404 unknown category, 422 bad UUID |
| GET | `/api/v1/worker-profiles/me/skills` | Bearer | — | 200 `WorkerSkill[]` | 401, 404 (no worker profile), 503 |
| POST | `/api/v1/worker-profiles/me/skills` | Bearer | `{"skill_id": "<uuid>"}` (`extra="forbid"`) | 201 `WorkerSkill` | 401, 404, 409 `WORKER_SKILL_EXISTS`, 422 (incl. `SKILL_NOT_AVAILABLE`), 503 |
| DELETE | `/api/v1/worker-profiles/me/skills/{skill_id}` | Bearer | — | 204 | 401, 404, 503 |

Proposed response shapes:

```json
// ServiceCategory
{"id": "uuid", "slug": "gardening", "name": "Gardening", "description": "…"}
// Skill
{"id": "uuid", "category_id": "uuid", "slug": "plant-care", "name": "Plant Care", "description": "…"}
// WorkerSkill (declaration)
{"skill": {Skill + "is_active": bool}, "category": {"id","slug","name"}, "declared_at": "ISO-8601", "is_self_declared": true}
```

Open questions for Priyanshu and Dhwanit:

1. Should the public list endpoints be unauthenticated? The data is non-personal.
2. Should there be a cap on declared skills per worker (for example 20)? The DB currently has none.
3. Should `list_worker_skills` hide inactive skills in the UI, or show them with a "no longer offered" label?
4. Should the existing error vocabulary be extended with `WORKER_SKILL_EXISTS` and `SKILL_NOT_AVAILABLE`?
5. Bulk replace (`PUT …/me/skills`) vs individual add/remove.

## 8. Integration notes

- **Backend (Priyanshu):** add a `WorkerSkillService` that maps the exceptions in §5 and resolves the worker profile from the token. Reuse `ContractCompliantRoute` and `error_responses()`. The API tests' SQLite fixture already creates these tables via `Base.metadata.create_all` (the PostgreSQL-only slug regex is skipped there; the PostgreSQL tests cover it).
- **Frontend (Dhwanit):** the UI must label skills as **"self-declared"** and must not show any verified badge (blueprint R2, R10). Key on `slug` or `id`.
- **Database tests:** run against the isolated `TEST_DATABASE_URL` only (see README, "Database tests").
- **Future discovery (Phase 3B, not designed here):** worker service area or location (PostGIS), availability, and eligibility (separate from declaration). `ix_worker_skills_skill_id` already supports "workers by skill" joins.

## 9. Change control

Changes to the tables, constraints, or repository signatures in this document need a new migration by Shresth and review by Priyanshu. The API in §7 becomes binding only once it is frozen in a Phase 3 OpenAPI contract.
