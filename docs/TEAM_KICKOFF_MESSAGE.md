# Team Zephyr — Phase 2 kickoff message (send to teammates)

Phase 1 of SAHAKAR–SEVA has been reported as running and tested: React/Vite frontend, FastAPI health APIs, PostgreSQL/PostGIS, Alembic `0001_foundation`, and Docker Compose. We will verify the same Git commit and tests on each machine before proceeding.

**Final team ownership**
- Dhwanit — frontend (`apps/web/**`)
- Priyanshu — FastAPI authentication, endpoint contracts, schemas, service logic
- Shresth — SQLAlchemy models, DB repositories, migrations, Compose and shared integration

**Final product**
A hyperlocal marketplace for **physical/in-person services only**, open to people who want to hire, offer services, or both. Later features include direct hiring, posted jobs, transparent earnings, and optional business/cooperative participation. Do not turn this into a remote-work freelance app or a cooperative-only signup flow. We retain worker protections without falsely claiming legal cooperative ownership.

**Phase 2 is strictly** Supabase authentication + verified identity mapping + editable own user profile + optional draft worker profile + basic business/cooperative account creation/listing. No matching, radius, jobs, bookings or payments yet.

Everyone must read `docs/PROJECT_BLUEPRINT.md` and the **same** `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md`. Priyanshu freezes `phase2.openapi.yaml` after checking it with Dhwanit and Shresth; we record the repository's actual PK types, migration head and auth signing mode before coding. Then develop in three separate Git branches and clones, never editing each other's implementation paths.

Merge order: **database → backend API/auth → frontend**, with real auth, real database and test gates before merge to main. We do not report a feature as complete simply because an agent generated files. Any conflict becomes a written contract change request with affected owners' consent.
