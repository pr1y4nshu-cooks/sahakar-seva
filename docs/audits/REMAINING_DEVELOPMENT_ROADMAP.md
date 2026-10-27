# SAHAKAR–SEVA — Remaining Development Roadmap

**Audit date:** 2026-10-27
**Basis:** `docs/SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md`, `docs/contracts/PHASE_3A_DATA_CONTRACT.md` §7 (proposed, unfrozen API), and the current implementation inventory in `CURRENT_PROJECT_IMPLEMENTATION_STATUS.md`.

This roadmap lists what remains, not what to build next without further product sign-off. Nothing here should be started without the relevant contract being frozen and acknowledged by all three owners, per the project's own phase discipline.

---

## Phase 3A — close-out (small, mostly done)

| Task | Depends on | Owner | Complexity | Notes |
|---|---|---|---|---|
| Commit the Phase 3A working-tree changes | None — ready now | Shresth | Trivial | Currently uncommitted/untracked on `shresthBranch`. Review the diff, then commit (do not push without explicit approval per repo rules). |
| Freeze the Phase 3A API contract (§7 of the data contract) | Priyanshu + Dhwanit review of open questions in the data contract (public list auth, skill cap, bulk vs individual add/remove) | Priyanshu (owner), Shresth + Dhwanit review | Small | Blocks any skills API work. The repository layer is ready and tested; only the HTTP surface needs design sign-off. |
| Implement skills API routes once frozen | Frozen Phase 3A contract | Priyanshu | Small–Medium | `WorkerSkillService` mapping the typed exceptions already defined in `app.repositories.exceptions`; reuse `ContractCompliantRoute` pattern from Phase 2. |
| Wire frontend skill selection UI | Skills API routes live | Dhwanit | Small–Medium | Must label all skills as "self-declared," no verified badge (blueprint R2, R10). |

## Phase 3B — Worker discovery and location

| Task | Depends on | Owner | Complexity | Priority |
|---|---|---|---|---|
| Design location/privacy model (approximate vs exact service area) | Product decision | Shresth (schema) + product owners | Medium | High — blocks all discovery and booking work |
| Add PostGIS geometry columns + GIST indexes for worker service area and job sites | Location model decision | Shresth | Medium | High |
| Worker discovery search endpoint (by skill + radius) | Skills API + location columns | Priyanshu | Medium | High |
| Discovery UI (replace `Hire.tsx` placeholder with live search) | Discovery endpoint | Dhwanit | Medium | High — the current `/hire` placeholder's commented-out card markup is effectively a UI prototype already, worth reusing |

## Phase 3B/4 — Booking lifecycle

| Task | Depends on | Owner | Complexity | Priority |
|---|---|---|---|---|
| Shared booking state machine design (direct-hire and job-application funnels converge here, per Phase 2 remediation report §16) | Product decision on the state machine | All three (design), Shresth (schema) | High | High — core to both customer and worker flows |
| `jobs` table + `job_applications` table | Booking state machine design | Shresth | Medium | Medium |
| Job posting API | `jobs` schema | Priyanshu | Medium | Medium |
| Job posting / browse UI (replace `FindWork.tsx` placeholder) | Job posting API | Dhwanit | Medium | Medium |
| Direct-hire request flow | Booking state machine + discovery | Priyanshu + Dhwanit | Medium | Medium |

## Phase 4 — Worker protections and transparency

| Task | Depends on | Owner | Complexity | Priority |
|---|---|---|---|---|
| Transparent pricing / quote entities attached to bookings | Booking schema | Shresth + Priyanshu | Medium | Medium |
| Eligibility/approval process separate from `onboarding_status` (per data contract §1: "a declaration is not verification") | Product decision on review criteria | Product + Priyanshu | Medium | High (worker-protection requirement, blueprint R2/R8) |
| Dispute/complaint tickets linked to bookings and users | Booking schema | Shresth + Priyanshu | Medium | Medium |
| Human review workflow for punitive decisions | Dispute schema | Product + Priyanshu | Medium | High (explicit blueprint requirement) |

## Phase 5+ — Payments, reviews, cooperative governance, notifications

| Task | Depends on | Owner | Complexity | Priority |
|---|---|---|---|---|
| Simulated/provider payment ledger | Booking completion state | Shresth + Priyanshu | Medium–High | Lower until booking lifecycle exists |
| Review/rating system | Completed booking state | Shresth + Priyanshu + Dhwanit | Medium | Lower |
| Cooperative governance tooling (collective participation records) | Organization model already supports `cooperative` type — this is additive | Shresth + Priyanshu | Medium | Lower |
| Notifications | Any async event source (bookings, applications) | Priyanshu + Dhwanit | Medium | Lower |

---

## Cross-cutting housekeeping (not phase-gated, low complexity, can be done anytime)

| Task | Owner | Complexity |
|---|---|---|
| Resolve `/health/db` 503 body shape vs. contract (§14.2 of remediation report) | Priyanshu (contract owner) | Trivial — needs a decision, not design work |
| Regenerate or delete stale `services/api/requirements.txt` | Shresth | Trivial |
| Remove duplicate `docs/PHASE_2_TECHNICAL_CONTRACT.md` (root copy) | Priyanshu or whoever owns `docs/` cleanup | Trivial |
| Remove stray empty root file `change: status bubble update` | Dhwanit | Trivial |
| Relabel or remove hardcoded fake counts in `Hire.tsx` / `FindWork.tsx` | Dhwanit | Trivial |
| Code-split the 530 KB frontend chunk | Dhwanit | Small |
| Configure a real Supabase project for local/live auth testing | Whoever owns credentials provisioning | Small (external dependency, not code) |

---

## Recommended integration order

1. **Commit Phase 3A** (trivial, unblocks everything else being built on a clean base).
2. **Freeze Phase 3A API contract** (small, no schema work, mostly a design conversation).
3. **Implement + wire skills API and UI** (closes out Phase 3A completely).
4. **Design the location/privacy model and shared booking state machine together** (these are the two decisions that gate nearly all of Phase 3B/4 — doing them separately risks rework).
5. **Worker discovery (PostGIS + search endpoint + UI)** — highest product value once the above decisions are made, and reuses the existing `/hire` placeholder's visual design.
6. **Booking lifecycle (jobs, applications, direct hire)**.
7. **Worker protections (eligibility review, transparent pricing, disputes, human review)** — should land alongside or immediately after booking, not after payments, per the blueprint's emphasis on worker protection as core rather than an afterthought.
8. **Payments, reviews, cooperative governance, notifications** — in roughly that order, each depending on a completed booking lifecycle.

Housekeeping items can be picked up opportunistically by their owners at any point and do not block the above sequence.
