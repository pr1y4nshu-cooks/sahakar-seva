# Ownership Map

This document reflects the actual repository structure and ownership assignments for the SAHAKAR–SEVA project.

## Repository Structure

```
sahakar-seva/
├── apps/web/                    # Frontend (Dhwanit owns)
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/Layout.tsx
│   │   │   └── ui/ (Button, Card, Input, StatusState)
│   │   ├── lib/
│   │   │   ├── api.ts           # Typed API client
│   │   │   ├── auth.tsx         # Supabase Auth provider
│   │   │   └── supabase.ts      # Supabase client
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── Placeholder.tsx
│   │   │   ├── Login.tsx
│   │   │   ├── Signup.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Profile.tsx
│   │   │   ├── Earn.tsx
│   │   │   └── Organizations.tsx
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── vitest.config.ts
├── services/api/                # Backend (Priyanshu owns)
│   ├── app/
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   └── v1/
│   │   │       ├── health.py
│   │   │       └── users.py     # Phase 2 endpoints
│   │   ├── core/
│   │   │   ├── auth.py          # Supabase JWT validation
│   │   │   ├── config.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── base.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   └── organization.py
│   │   ├── repositories/
│   │   │   └── user.py          # Repository layer
│   │   ├── schemas/
│   │   │   └── user.py          # Pydantic schemas
│   │   └── main.py
│   ├── alembic/
│   │   └── versions/0001_foundation.py
│   ├── tests/
│   │   ├── conftest.py
│   │   └── test_health.py
│   └── pyproject.toml
├── docs/
│   ├── SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md
│   ├── api-contracts.md
│   └── architecture.md
├── compose.yml
├── .env.example
└── README.md
```

## Ownership (per Section 11 of Blueprint)

| Workstream | Primary Owner | Directories |
|---|---|---|
| Frontend | **Dhwanit** | `apps/web/**` |
| Backend API & Auth | **Priyanshu** | `services/api/app/api/**`, `services/api/app/schemas/**`, `services/api/app/core/auth.py` |
| Database & Infrastructure | **Shresth** | `services/api/app/db/**`, `services/api/app/models/**`, `services/api/app/repositories/**`, `services/api/alembic/**`, `compose.yml` |
| Shared Integration | **Shresth** (custodian) | `services/api/app/main.py`, `services/api/app/core/config.py`, `services/api/pyproject.toml`, root `.env.example` |

## Phase 2 Implemented Frontend Screens (Dhwanit)

1. ✅ **Auth**: `/login` (Login.tsx), `/signup` (Signup.tsx) - Supabase Auth integration
2. ✅ **Account**: `/profile` (Profile.tsx) - User profile with editable display_name
3. ✅ **Earn**: `/earn` (Earn.tsx) - Worker profile create/edit with honest `draft` status
4. ✅ **Organization**: `/organizations` (Organizations.tsx) - Create business/cooperative, list own
5. ✅ **Dashboard**: `/dashboard` (Dashboard.tsx) - Overview with navigation to all features
6. ✅ **Public**: `/` (Home.tsx), `/hire`, `/find-work` (Placeholder.tsx)
7. ✅ **Layout**: Updated with auth-aware navigation, sign in/out, user status

## Phase 2 Implemented Backend Endpoints (Priyanshu)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Health check (Phase 1) |
| GET | `/api/v1/health/db` | Database health (Phase 1) |
| GET | `/api/v1/users/me` | Current user profile |
| PATCH | `/api/v1/users/me` | Update display_name |
| POST | `/api/v1/worker-profiles` | Create worker profile (draft) |
| GET | `/api/v1/worker-profiles/me` | Get own worker profile |
| PATCH | `/api/v1/worker-profiles/me` | Update worker profile (not onboarding_status) |
| POST | `/api/v1/organizations` | Create org + owner membership |
| GET | `/api/v1/organizations/mine` | List user's organizations |

## Supabase Auth Integration

- Frontend: `AuthProvider` context in `apps/web/src/lib/auth.tsx`
- Backend: JWT validation via JWKS in `services/api/app/core/auth.py`
- Token injection in API client via `Authorization: Bearer <token>`

## Tests

- Frontend: `npm test` (Vitest + React Testing Library) - 3 passing
- Backend: `pytest` - 2 passing
- Typecheck: `npm run typecheck` - passes
- Build: `npm run build` - passes

## Notes

- Supabase credentials (VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY) are optional in development - clearly marked when not configured
- Phase 1 database schema matches the blueprint (users, worker_profiles, organizations, organization_memberships)
- No Alembic migrations needed for Phase 2 (Phase 1 schema already complete)
- API contract follows the documented error format: `{"error":{"code":"...","message":"..."}}`