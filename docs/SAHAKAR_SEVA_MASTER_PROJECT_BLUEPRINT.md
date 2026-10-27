# SAHAKAR–SEVA
## Master Project Blueprint & Multi-Agent Collaboration Contract

**Document version:** 1.0  
**Date:** 27 October 2026  
**Team:** Zephyr — Dhwanit (Frontend), Priyanshu (Backend), Shresth (Database/Infrastructure)  
**Status:** Shared specification for team confirmation; does not claim Phase 1 has been successfully implemented  
**Purpose:** The single shared reference to give all three teammates and their coding agents before parallel work begins in Phase 2.

> **Working agreement:** No agent may reinterpret the product, invent additional features, introduce another stack, change a shared API contract, or modify another teammate's owned files without a documented team agreement. All agents must inspect the actual repository first. This document defines the *intended* architecture; the real codebase and successful tests determine what Phase 1 actually delivered.

---

# 1. One-Page Product Definition

**Name:** SAHAKAR–SEVA  
**Proposed positioning:** Local Skills. Real Opportunities. Fair Work.  
**Product:** A mobile-first, location-based marketplace for **physical/in-person services only**. An individual can hire nearby help, offer services as a worker, or do both using one account. Customers may either **(A) find a worker and request a direct hire** or **(B) post a local task and select an applicant**. Companies can eventually request recurring or multiple on-site tasks. Existing cooperatives/collectives may participate as organizations with their own member relationships and policies.

## Problems to solve
1. Customers and small businesses struggle to reliably discover suitable nearby workers, compare availability, agree on terms, and resolve problems.
2. Independent and part-time workers need discoverable local earning opportunities, scheduling control, clear take-home pay, and protection against opaque restrictions.
3. Worker groups and small organizations need simple digital records of work, earnings, and decisions without losing their identity or autonomy.

## Success means
A real request becomes a real persisted, mutually accepted booking. The system checks eligibility and availability, shows agreed pricing transparently, preserves a transaction history, and allows a human-reviewed dispute. Claims of income improvement, benefits delivery, worker ownership, and legal compliance require real evidence and cannot be simulated as facts.

## The product is NOT
- A global or remote-work freelancing site; no design, programming, or purely online gigs.
- A generic job board for permanent employment.
- A worker-owned legal cooperative merely because a voting screen exists.
- An AI matchmaking product, blockchain platform, real escrow wallet, or government benefits portal.
- A complete enterprise procurement system in the hackathon MVP.

# 2. Decision Record: Original PPT vs. Agreed Product

**Source of truth order:** (1) explicit latest team/product decisions recorded here; (2) original 12-slide *SAHAKAR–SEVA / Code Yudh* PPT for retained principles; (3) Phase 1 scaffolding prompt for intended technical foundation; (4) existing implementation *only for what is actually working*. If there is a conflict, **do not silently pick one**: record the difference and request agreement in the team channel before modifying interfaces or migrations.

| Topic | Original PPT | Updated binding decision | How continuity is preserved |
|---|---|---|---|
| Intended users | Cooperative workers, households, cooperatives | Open access for individuals who hire and/or work; later business and collective organizations | Retains worker and household value; adds independent earners and business demand |
| Registration vs. discovery | Worker verification before appearing in search | Anyone may **register and declare skills immediately**; **only appropriately approved/eligible workers** can accept or appear for bookable categories | Open registration does not override safety/verification requirements |
| Ways to hire | Search, shortlist, book | **Both** direct worker request and customer job posting with applications | Both routes converge on **one booking lifecycle** |
| Work type | Electrician, plumber, cleaner, caregiver examples | **Physical/local services only**; start with low-risk defined tasks (e.g., furniture assembly, basic cleaning, gardening) | High-risk categories postponed pending standards, competence, and safeguards |
| Control/ownership | Cooperative-owned Seva Nodes; future federation | Open marketplace, **cooperative-ready organization mode**; real legal member ownership is **not claimed** for all users | Preserve transparent policies, due process, member control within participating co-ops |
| Worker protections | Wage-floor configuration, capped fees, workload tie-break, appeals, audit | Retain as policy-enforced capabilities, with measurable tests; calibrate actual thresholds through a pilot | Keep the PPT's strongest differentiator |
| Pricing | Proposed 10–15% commission cap; sustainability to validate | **No universal commission promise yet**; transparent, configurable fee cap; 10% may be a **demo-only assumption** | Does not assert untested financial sustainability |
| Integrations | UPI, welfare, maps, Bhashini as mock/sandbox; ONDC/Beckn inspired | No live integrations necessary for MVP; simulated settlements visibly labelled; no official affiliation claim | Keeps the PPT's integration honesty |
| Team allocation | Dhwanit product, Priyanshu frontend, Shresth backend | **Dhwanit frontend; Priyanshu backend/API/auth; Shresth database/infra** | This explicitly supersedes PPT slide 2 assignments |
| Tech foundation | React PWA, FastAPI, PostgreSQL/PostGIS | React + TypeScript/Vite/Tailwind; FastAPI; PostgreSQL/PostGIS; Docker; Supabase Auth target | Core architecture remains aligned |
| Delivery | One 24-hour vertical slice | First verify Phase 1; Phase 2 auth/profile foundation; then a narrow integrated hiring/bookings demo | Maintains “one complete flow over many partial integrations” |

**Do not call these product changes accidental discrepancies.** They are intentional refinements. What would be a discrepancy is for one agent to implement cooperative-only signup, another to build independent-worker signup, and another to assume everyone is already verified.

# 3. Core Product Rules — Non-Negotiable

**R1. Dual-mode account.** A user may hire and offer services; customer/worker are capabilities, not permanently exclusive user types. One user identity can also be an authorized organization member.

**R2. Open registration, conditional activation.** Signup and self-declared skills are open. Profile creation, identity verification, skill verification, and category eligibility are separate concepts. A new user must not receive a misleading “verified” badge. Self-declared skill alone does not authorize safety-sensitive work.

**R3. Local, physical services only.** Workers control where they operate (locality/radius), relevant skills, and availability. Location permission must be optional when a manual locality can work.

**R4. Two hiring funnels, one fulfillment engine.** A direct-hire request and an accepted application to a posted job both create a booking subject to the same acceptance, schedule, fee, and audit rules.

**R5. Mutual agreement.** No confirmed job without the required customer and worker acceptance. Job scope, location disclosure, time, price, and cancellation expectations must be agreed.

**R6. Explainable matching.** Filter by eligible skills/category, availability, service area, then order by relevant suitability and distance. Workload may be a carefully designed secondary tie-breaker; no black-box AI requirement.

**R7. Transparent pay.** Show the quoted price, fees, and expected worker payout before agreement. Store currency in integer paise. Effective hourly earnings are estimates until actual time/expenses are known.

**R8. Human due process.** An automated flag may create a review case but cannot alone impose a punitive restriction. Record who decided, why, when, and under which policy.

**R9. Privacy/security by default.** Don't expose exact residential addresses to public browsing. No raw Aadhaar uploads by default. No production secrets in Git, client-side service-role credentials, or frontend-only access control.

**R10. No false launch claims.** Development fixtures and payment simulations must be visibly identified. “Verified,” “paid,” “worker owned,” “government integrated,” and “fully compliant” require actual supporting evidence.

# 4. Personas, Account Structure and Authorization

**Human account:** signed-in individual with identity from the chosen auth provider and a `users` row. Can become a customer, worker, and organization member. A worker profile is optional.

**Worker profile:** skill/service interests, onboarding status, service area, and availability (some fields introduced in later phases); approval/eligibility is independent of account creation.

**Organization:** `business` or `cooperative`, with `owner`, `admin`, and `member` roles scoped to that organization. Creating an organization does not grant platform administrator rights.

**Platform staff/admin:** a separate trusted capability, NOT a choice in a public signup form; explicit server-assigned authorization required. No public API allowing a user to make themselves a platform admin or approve their own verification.

| Action | Signed-in person | Worker-profile owner | Organization owner/admin | Platform reviewer |
|---|---|---|---|---|
| Read/update own user profile | Yes | Same identity | Same identity | Only within approved support policy |
| Create own worker profile | Yes | Once per user | Same identity | N/A |
| Change own bio/declared skills | If profile exists | Yes | Not for someone else by default | Only with documented authority |
| Approve worker skill/verification | No | No | Later, for authorized member scope only | Later, with recorded decision |
| Create organization | Yes (subject to validation) | Yes | N/A | Not required |
| View/manage organization's private membership | No, unless member | Only if authorized | Yes, within organization | Limited authorized support |
| View other users' private details | No | No | No by default | Least privilege only |

# 5. User Journeys and Acceptance Criteria

## 5.1 Direct hire (later marketplace phase)
1. Customer enters service, locality, and preferred slot.
2. System returns eligible available workers who serve that location, with truthful trust indicators.
3. Customer reviews quote / price range, sends request to one worker.
4. Worker accepts or declines; accepted booking is persisted only if the slot is still free.
5. Both sides see confirmed scope, timing, price, and status.
6. Work is completed and the settlement simulation is recorded for the demo (not a real transfer).
7. Either side can raise a dispute; a reviewer documents the outcome.

**Pass:** request/accept/complete state is persisted across sessions; ineligible/unavailable workers are excluded; duplicate confirms are prevented.

## 5.2 Job post → application → hire (later marketplace phase)
1. Individual or authorized business publishes a physical-service task with category, locality, date/time, budget, and scope.
2. Eligible workers whose service areas include the task can discover it and apply.
3. Customer reviews applications and selects a worker; the selected offer converts to the same booking model as direct hire.
4. Other applications close or become non-selected; no duplicate confirmed booking is created.

**Pass:** posted-job funnel and direct-hire funnel call the *same* booking business rules, not different payout/accountability implementations.

## 5.3 Worker onboarding (Phase 2)
1. User signs up through the real auth provider and opens “Earn”.
2. User creates a basic worker profile and declares a bio and display name.
3. UI displays a truthful `draft`/not-yet-approved status. No suggestion they are approved for an unsafe trade.
4. Worker can edit their own profile; another logged-in user cannot edit or read private fields.

**Pass:** repeat creation is safely rejected or idempotently returns existing, depending on frozen API contract; users cannot set their own `approved` status.

## 5.4 Organizations (Phase 2 minimal / later expansion)
Authorized individual creates a business or cooperative organization and receives owner membership in the *same transaction*. No company-wide recurring job/invoicing system yet. Cooperative members and governance decisions are later-phase features.

# 6. Product Roadmap: What Each Phase Actually Contains

| Phase | Scope | Exit gate |
|---|---|---|
| **Phase 1 — foundation** (prompt already executed; results unverified) | Monorepo, React app shell, FastAPI health, PostgreSQL/PostGIS, Alembic, local Docker, basic `users`/`worker_profiles`/`organizations`/`organization_memberships` schema | Frontend, backend, DB and migration tests really pass; inspect repo, no assumptions |
| **Phase 2 — identity + profiles** (**NEXT**) | Supabase Auth integration, bearer-token verification, current-user endpoint, dual-role user model, basic worker-profile CRUD, organization creation/member ownership, typed frontend calls, test coverage | Signup/login works; isolated permissions; real DB persists all changes; no fake auth |
| **Phase 3 — marketplace discovery** | Service categories, worker skill declarations, availability, service radii, location-safe discovery, jobs and applications | Nearby eligible workers/jobs appear correctly; negative tests pass |
| **Phase 4 — transactional booking** | Direct hire + accepted application → common state machine; slot locking; consent/price snapshot; mocked settlement ledger | Both funnels complete end-to-end without duplicate bookings or incorrect splits |
| **Phase 5 — trust and governance MVP** | Review queue, dispute/appeal decisions, event log, fee policy, worker-facing earning statements | Can challenge a rule live; reviewer action is traceable |
| **After pilot validation** | Business repeat bookings, higher-risk trades, regulated payments, multilingual assistance, verified co-op nodes/federation, welfare referrals | Only if demand, controls, legal requirements, and operations justify them |

**Hackathon compression rule:** If necessary, combine *small slices* of Phases 3–5 to make **one working request-to-booking-to-audit demo**; never build the breadth of all phases with static placeholders masquerading as functionality.

# 7. Locked Technical Architecture and Boundaries

**Frontend:** `apps/web` — React, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router, TanStack Query, responsive PWA. Frontend communicates with FastAPI for *all business data*. Supabase client may be used for authentication only.

**Backend:** `services/api` — FastAPI, Pydantic v2, SQLAlchemy 2, Psycopg 3, Alembic, Pytest, modular monolith. Backend checks authenticated claims and authorizes *every* protected operation. No trust in `user_id` submitted by a client when ownership must come from token identity.

**Database:** PostgreSQL + PostGIS. Migrations via Alembic only, not ad hoc `create_all` on application startup. Use UUID identifiers consistently for new tables (confirm Phase 1 actual type before any migration); UTC timezone-aware timestamps; explicit unique constraints/foreign keys.

**Authentication:** Supabase Auth is the target chosen in the foundation prompt. Frontend receives a short-lived user access token from the provider and sends it as `Authorization: Bearer <token>` to FastAPI. Backend validates issuer, audience, signature (using provider-appropriate JWKS/configuration), expiry, and user identifier; maps the token subject to `users.external_auth_id`. **Never trust an unverified JWT decode.** Do not put the Supabase service-role secret in the browser. Use local/mock UI fixtures only for parallel interface development, visibly marked and never as production authentication.

**Infrastructure:** Docker Compose for PostGIS and services; Supabase-hosted PostgreSQL possible later, but avoid switching development databases mid-phase without migration proof. Deployment setup follows actual existing repo configuration, not assumed host names.

**Excluded until justified:** Redis, Celery, microservices, AI matching, OCR-driven approval, blockchain, live UPI or escrow, real ONDC connection, complex company ERP, raw sensitive-document storage.

# 8. Phase 2 Database Contract (Shresth owns)

**Audit the Phase 1 schema before changing anything.** The first prompt proposed these tables, but they may differ in actual code. Changes must be additive and migration-backed. No destructive reset or migrations over others' changes without sign-off.

| Entity | Required Phase 2 behavior | Constraints / notes |
|---|---|---|
| `users` | App user linked to provider identity; public `display_name`; normalized `email`; timestamps | `external_auth_id` nullable initially, unique when present; no insecure user-supplied identity binding |
| `worker_profiles` | Zero/one per user; `display_name`, optional `bio`, `onboarding_status` | Unique `user_id`; initial `draft`; status **not writable by worker** |
| `organizations` | Name and kind `business` or `cooperative` | Validated kind; no claim of legal verification from a simple registration |
| `organization_memberships` | Links user to organization with scoped `owner`/`admin`/`member` | Unique `(organization_id, user_id)`; creation of org + owner row atomic |

**Canonical Phase 2 worker onboarding status:** `draft`, `pending_review`, `approved`, `restricted`. **Phase 2 only creates `draft`; no fabricated approval UI/API.** The later review system may transition other states with authorization and an audit event. Decide if these are DB native enums or constrained strings *once* and document it.

**Do not prematurely add** job, application, booking, ledger, payouts, ratings, welfare, exact private addresses, government IDs, or location-tracking tables in Phase 2. Location/radius become structured fields in Phase 3 when matching contracts are specified.

**Migration rules:** Shresth is the only migration author/merger for Phase 2. Priyanshu requests schema changes through contract review, not independent edits in `alembic/`. Migration must upgrade an existing Phase 1 DB and support fresh setup. No `--accept-data-loss` or schema-reset shortcut on shared environments.

# 9. Phase 2 API Contract — Freeze Before Parallel Coding

**Base URL:** `/api/v1`  
**Auth for protected routes:** `Authorization: Bearer <Supabase access token>`  
**Data format:** `application/json`, UTF-8; stable UUID identifiers as strings; ISO-8601 UTC timestamps.  
**Response policy:** successful responses are plain resource JSON (no invented wrapper); errors use a consistent documented shape: `{"error":{"code":"...","message":"..."}}` plus HTTP status. Validation errors can carry an optional `details` array. Do not leak internal SQL or provider secrets.

| Method and path | Owner | Request | Success / failures |
|---|---|---|---|
| `GET /api/v1/health` | Existing Phase 1 | None | Basic API status; leave backwards-compatible |
| `GET /api/v1/health/db` | Existing Phase 1 | None | Real DB check; leave backwards-compatible |
| `GET /api/v1/users/me` | Priyanshu | Bearer token | `200` current user (create/sync once safely if no row); `401` invalid token |
| `PATCH /api/v1/users/me` | Priyanshu | `{ "display_name": "..." }` | `200` updated self; `401`, `422` |
| `POST /api/v1/worker-profiles` | Priyanshu | `{ "display_name": "...", "bio": "..." }` | `201` own draft worker profile; `409` duplicate; `401`, `422` |
| `GET /api/v1/worker-profiles/me` | Priyanshu | Bearer token | `200` own profile; `404` if absent |
| `PATCH /api/v1/worker-profiles/me` | Priyanshu | `{ "display_name"?: "...", "bio"?: "..." }` | `200` updated; prohibit status/verification edits; `401`, `404`, `422` |
| `POST /api/v1/organizations` | Priyanshu | `{ "name": "...", "organization_type": "business" | "cooperative" }` | `201` organization + caller as owner; `401`, `422` |
| `GET /api/v1/organizations/mine` | Priyanshu | Bearer token | `200` list of organizations and caller's scoped membership role |

**Minimal response fields** (exact OpenAPI to be frozen by Priyanshu before implementation):
- `User`: `id`, `display_name`, `email`, `created_at`, `updated_at`; never expose provider secrets.
- `WorkerProfile`: `id`, `user_id`, `display_name`, `bio`, `onboarding_status`, `created_at`, `updated_at`.
- `Organization`: `id`, `name`, `organization_type`, `my_membership_role`, `created_at`, `updated_at`.

**Required HTTP semantics:** `401` unauthenticated/invalid token, `403` authenticated but forbidden, `404` absent/not accessible, `409` duplicate/conflict, `422` invalid input, `5xx` unexpected server fault. No `200 OK` with `{success:false}` for a failed operation.

**Contract authority:** Priyanshu owns `docs/contracts/phase2.openapi.yaml` (or equivalent checked-in OpenAPI artifact), obtains acknowledgment from Dhwanit and Shresth, then freezes paths, request/response fields, status codes, and the error format. A contract change requires a versioned PR with both consumers' reviews. Frontend should generate/request typed models from the frozen contract, not guess endpoint names.

# 10. Phase 2 Frontend Contract (Dhwanit owns)

**Build these connected screens only:**
1. Public app layout, existing Home/Hire/Earn placeholders preserved; no fake marketplace data.
2. Auth: signup, login, logout, session loading/expired state using the real configured provider (only when credentials exist).
3. Account: “My profile” displaying provider-linked user info and editable `display_name`.
4. Earn: create/edit **basic** worker profile; honest `draft` status, no self-approval.
5. Organization: basic create business/cooperative form and list own organizations, only if endpoints ready.
6. A Hire/Earn navigation switch available to the *same* account, no duplicate identities.

**UX rules:** show loading/empty/error states; no pretending unauthenticated placeholders are real personal dashboards; low-bandwidth friendly; accessible labels; works on phone width; do not require geolocation permission. Show “verification coming later” rather than an unsupported verified badge. Do not store service-role keys in public environment variables.

**Integration rules:** Use one typed API client (`apps/web/src/services` or the existing equivalent) and TanStack Query; token injection from the auth session; handle `401` with sign-in/retry guidance, `403` with permission explanation, `409` with duplication feedback. Avoid hardcoding backend resource data in UI. For parallel build, use clearly labelled development fixtures that are removed/disabled in final integration.

# 11. Team Ownership and No-Conflict File Contract

| Workstream | Primary owner | May edit | Must not edit without approval |
|---|---|---|---|
| Frontend | **Dhwanit** | `apps/web/**`, frontend-specific tests, frontend-only setup files | Backend routes/models/migrations, root Compose, API contracts |
| Backend API & auth | **Priyanshu** | `services/api/app/api/**`, `app/schemas/**`, `app/services/**`, backend auth/security dependencies, `services/api/tests/api/**`, `docs/contracts/phase2.openapi.yaml` | `app/db/**`, `app/models/**`, `app/repositories/**`, Alembic migrations, frontend |
| Database & infrastructure | **Shresth** | `services/api/app/db/**`, `app/models/**`, `app/repositories/**`, `services/api/alembic/**`, `services/api/tests/db/**`, `compose.yml` / DB environment setup | API request/response shapes, frontend screens, another agent's security flow |
| Shared integration files | **Shresth as integration custodian**, reviewed by Priyanshu | `services/api/app/main.py`, common `app/core/config.py`, backend dependency files, `services/api/pyproject.toml`, root `.env.example`, root README and Compose if needed | Changes from either other agent without a small reviewed PR |
| Product specification | **All approve; Dhwanit may propose editorial changes** | This document through reviewed change request | Silent feature additions/removed safeguards |

**Repository reality overrides path guesses.** If Phase 1 used different folders, write `docs/OWNERSHIP_MAP.md` reflecting actual paths before parallel edits. Do not reorganize the repo just to match this document.

**Explicit backend split:** Priyanshu owns contracts, route/service logic, auth validation; Shresth owns tables, migrations, session/repository access, indexes and transactional primitives. Repository function signatures (`get_or_create_user_by_auth_subject`, `get_worker_profile_by_user`, `create_worker_profile`, `create_organization_with_owner`, etc.) are **proposed interface names**, and must be agreed in a short handshake before independent coding. No one should assume a repository function exists until it is merged.

# 12. Git Workflow and Agent Coordination

1. **Before branching:** one team member creates a shared remote repository or verifies the existing remote. Record the actual Git default branch and Phase 1 baseline commit. Run frontend build, backend tests, DB health check, and migrations; publish blockers.
2. **Create** a protected integration branch, for example `integration/phase2`, from the verified baseline. Feature branches: `feat/p2-frontend-dhwanit`, `feat/p2-api-priyanshu`, `feat/p2-db-shresth`.
3. **Freeze the API/data contract before implementing dependent calls.** An acknowledgment message from all three is enough; unresolved fields must be resolved once, not independently guessed.
4. **Never have two agents commit to the same working directory** or run simultaneous schema rewrites. Each teammate uses their own Git branch and clone/worktree.
5. **Recommended merge sequence:** (a) Shresth's migration/models/repository PR, (b) Priyanshu's API/auth/service PR, (c) Dhwanit's integrated frontend PR. Dhwanit builds against contract fixtures in parallel; final integration begins after API merge.
6. **PR checks:** branch rebased/merged from integration head; tests pass; changed files respect ownership; endpoints and migration behavior reviewed; secrets scan; docs updated for any contract change.
7. **Shared files:** one assigned integrator changes common configuration/entry points. Other members provide patches or PR requests, not direct conflicting edits.
8. **Only merge tested work**, avoid force-pushing shared branches, and never reset the shared database to force a demo to work.
9. **Daily/phase checkpoint:** each teammate reports: finished endpoints/files, blockers, assumptions, tests run, and upcoming dependency. Never report untested code as complete.

**Required coordination message format:** `Change request | reason | impacted paths / DB / API | backwards compatibility | affected owners' approvals | tests`.

# 13. Phase 2 Parallel Agent Briefs (copy into each agent with THIS document)

## Dhwanit's frontend agent
**Mission:** Implement ONLY Phase 2 responsive auth/account/worker-profile/org screens in `apps/web/**`, using the team's frozen API contract. Inspect Phase 1 existing frontend first. Keep visual style light neutral + purple, accessible, mobile-first. Integrate provider sign-in through real Supabase Auth when credentials exist; do not implement a custom backend login or pretend mocks are live. Do not modify FastAPI, DB, migrations, root Compose, or frozen OpenAPI. First list any missing API response field and request a contract decision; do not invent it. Run typecheck, build, UI/auth error tests. Provide PR, files changed, screenshots where useful, and real test results.

## Priyanshu's backend/API agent
**Mission:** Implement ONLY Phase 2 authenticated REST endpoints, token validation, policy guards, Pydantic schemas, and API tests. First inspect existing API, confirm configuration/security expectations with Shresth, freeze `docs/contracts/phase2.openapi.yaml` and publish the contract to Dhwanit. Only user-controlled profile fields are writable; status/verification or platform admin permissions cannot be self-assigned. Use repository interfaces supplied by Shresth. Do not change DB models/Alembic or frontend. Implement secure bearer token errors and tests for 401/403/404/409/422, duplicate worker profiles, and organization creation. Never claim JWT verification unless signature/issuer/audience/expiry tests run.

## Shresth's database/infrastructure agent
**Mission:** Implement ONLY Phase 2 database audit, additive migrations, model relationships, repositories, transaction handling, and DB integration tests. Begin with actual Phase 1 migrations: don't assume schema matches prompt. Agree repository calls and field names with Priyanshu before implementation. Preserve provider-identity uniqueness, one worker profile per user, unique organization membership, and atomic organization+owner creation. Own environment/Compose compatibility, migrations, and integration of shared app config via small reviewed changes. Do not implement frontend or silently alter API response fields. Test migration on fresh and existing databases; report exact commands and errors.

# 14. Phase 2 Test Matrix and Definition of Done

| Test | Owner | Expected outcome |
|---|---|---|
| Phase 1 baseline frontend build / API health / DB health | All (Shresth coordinates) | Real working startup or documented pre-existing blocker |
| Supabase signup/login/logout and session refresh | Dhwanit + Priyanshu | Real provider flow, protected routes; no fake authentication |
| Bad/expired bearer token | Priyanshu | `401`, no data exposure |
| User profile `/users/me` | Priyanshu + Shresth | Correct token identity mapped to a persisted user row |
| Attempt to edit someone else's profile | Priyanshu | Prevented by token-scoped endpoint/permissions |
| New worker profile | All | Persists as `draft`, displayed accurately |
| Repeated worker profile creation | Priyanshu + Shresth | `409`, no duplicate row |
| Worker submits `onboarding_status=approved` | Priyanshu | `422`/rejected; no elevation |
| New organization + owner membership | Priyanshu + Shresth | Both committed or both rolled back |
| Worker profile / organization API failures | Dhwanit | Understandable loading/error states, no misleading success |
| Database down | Shresth + Dhwanit | Health check fails correctly, frontend does not lie |
| Alembic upgrades fresh DB and existing Phase 1 DB | Shresth | No destructive reset required |
| Full build/typecheck/test commands | All | Actual execution outcomes recorded in PRs |

**Phase 2 DONE only when:** all agreed endpoints and screens are working end to end against a real backend/database, required permissions are tested, the SQL migration works, frontend build and backend tests pass, secrets remain private, and all three branches are merged into the integration branch. **An agent saying “implemented” is not proof.** If Supabase cannot be configured, Phase 2 remains partially blocked; non-auth UI work may continue with clearly marked temporary fixtures.

# 15. Risks, Compliance and Trust — Design Constraints

- **Location privacy:** approximate public service area; reveal exact job location only to authorized participants when appropriate; no always-on GPS.
- **Service safety:** initial pilot/demo uses bounded lower-risk tasks. Higher-risk electrical, plumbing, childcare/caregiving, medical, or hazardous work requires separate standards, qualifications, screening, and support before launch.
- **Age policy:** initial commercial worker onboarding should be adult-only, subject to appropriate legal review.
- **Privacy:** collect minimal personal data, retain only necessary verification results, restrict uploads, document consent and deletion pathways. Review applicable Indian DPDP obligations at actual launch time.
- **Payments:** mock ledger only for hackathon; later real charges/payouts through an appropriately compliant service. No internally held escrow or false payment confirmations.
- **Labour/consumer/tax:** before commercial rollout review applicable gig/platform-worker obligations, GST treatment of services via an e-commerce operator, consumer redress, terms, insurance/liability, and B2B contracting with qualified advisers.
- **Cooperatives:** organization type does not establish legal cooperative registration or member ownership; distinguish verified cooperative partner claims from self-declaration.
- **Reliability:** server-side authorization, transactional booking, no double reservations, idempotent settlement actions, events with timestamps/actors, human escalation for disputes. Implement progressively in the proper phase.

# 16. Value, Motivation, Sustainability, and Impact

**Workers:** flexible local earning, control over jobs/schedule/radius, transparent take-home amounts, portable history subject to consent, fair review. **Customers:** predictable discovery, understandable price, eligibility signals, reliable confirmation, problem resolution. **Companies:** repeatable local sourcing and transaction records; recurring contracting later. **Collectives:** discovery and admin tools without surrendering their independent governance.

**Community engagement:** service mentoring, referrals with safeguards, direct member feedback, cooperative-approved policies where real governance exists. Avoid pay-to-rank schemes that undermine opportunity fairness or manipulative gamification.

**Business model hypotheses (not validated):** free worker entry; clearly disclosed transaction fees within published policy; optional organization subscription for valuable recurring operations; cooperative-level software/support options. No investor ROI, job creation, commission sustainability, or income uplift claims without observed data and cost accounting.

**Key pilot metrics:** filled requests, time to accepted booking, worker active utilization, net earnings per actual hour after known expenses, repeat customer rate, cancellation/dispute rate, response and resolution times, contribution margin per completed job, and genuine worker-policy participation. Record baseline and observation sample size; never relabel simulated data as field evidence.

# 17. Open Decisions and Phase-Start Gate

Before starting Phase 2, the team must verify or decide only these material unknowns:

1. **What actually exists after Phase 1?** Confirm repository tree, migrations, environment files, build/test status and remote URL. This document does NOT certify that the prior coding agent completed the prompt.
2. **Supabase Auth readiness:** Is an authentication project/configuration available to all developers? Set development/test configuration appropriately, without sharing secrets in the document or Git.
3. **Exact owner/name/path agreement:** Check that Phase 1 file names match Section 11. Record differences in the repository ownership map.
4. **Schema contract:** Agree actual primary-key type, current columns, and repository function signatures, and freeze the OpenAPI shapes.
5. **Minimum demo service:** Choose one bounded physical service (e.g., furniture assembly) and one locality for later matching/booking tests; it does not block basic Phase 2 identity work.

**Default if uncertain:** stop only the conflicting edit, surface it as a contract decision, and continue independent work that does not risk breaking shared data or APIs.

# 18. Reference and Change Control

**Source:** The team's original 12-slide presentation, *SAHAKAR–SEVA — Code Yudh Submission* (Team Zephyr); the agreed conversation decisions about open signup, both hiring models, physical/local services only, and improved product strategy; and the previously executed *Phase 1 — Full-Stack Project Foundation* prompt. This is a **reconciled new design**, not a claim that the original PPT already contained the open marketplace or revised team assignments.

**Document maintenance:** Store this file in the repo as `docs/PROJECT_BLUEPRINT.md` after team review. Future intentional changes must include an explicit decision record, affected sections, API/DB migration impact, responsible owner, and effective phase. Agents may suggest improvements but may not silently rewrite core scope.

**Team acknowledgment:** Dhwanit — Frontend; Priyanshu — Backend/API/Auth; Shresth — Database/Infra. Record approval of v1.0 in the team channel before running independent Phase 2 implementation prompts.
