# SAHAKAR–SEVA Phase 2-4 Handoff Document

**Project:** SAHAKAR–SEVA  
**Team:** Zephyr — Dhwanit (Frontend), Priyanshu (Backend/API), Shresth (Database/Infra)  
**Document Version:** 1.0  
**Date:** 2026-10-27  

---

## Summary

This document summarizes the complete implementation of Phases 2-4 for the SAHAKAR–SEVA frontend (Dhwanit's ownership). All work follows the frozen Phase 2 contract in `docs/contracts/phase2.openapi.yaml`.

---

## Phase 2 — Identity + Profiles (Frontend)

### Screens Implemented (`apps/web/src/pages/`)

| Screen | Path | Component | Status |
|--------|------|-----------|--------|
| **Home** | `/` | `Home.tsx` | ✅ Public landing |
| **Hire Placeholder** | `/hire` | `Placeholder.tsx` | ✅ Phase 3 coming soon |
| **Find Work Placeholder** | `/find-work` | `Placeholder.tsx` | ✅ Phase 3 coming soon |
| **Login** | `/login` | `Login.tsx` | ✅ Supabase Auth |
| **Signup** | `/signup` | `Signup.tsx` | ✅ Supabase Auth + email confirmation flow |
| **Dashboard** | `/dashboard` | `Dashboard.tsx` | ✅ Profile + Worker + Org overview |
| **Profile** | `/profile` | `Profile.tsx` | ✅ Edit display_name |
| **Earn (Worker Profile)** | `/earn` | `Earn.tsx` | ✅ Create/edit worker profile, draft status |
| **Organizations** | `/organizations` | `Organizations.tsx` | ✅ Create business/coop, list owned |

### Auth & Session (`apps/web/src/lib/auth.tsx`)

- **AuthProvider** — Supabase Auth integration with session management
- **Email confirmation flow** — Dedicated screen when signup returns no session
- **Token provider** — Sets `window.__SAHAKAR_AUTH_TOKEN__` for TanStack Query hooks
- **Session expiry detection** — AuthGuard proactively validates session on mount

### Route Guards (`apps/web/src/components/auth/AuthGuard.tsx`)

| Guard | Purpose |
|-------|---------|
| `AuthGuard` | Protects routes; redirects to `/login` with return URL; detects session expiry |
| `PublicOnlyGuard` | Redirects authenticated users away from `/login`, `/signup` |
| `EmailConfirmationRequired` | Shows email verification screen with resend option |

---

## Phase 2 — API Layer (`apps/web/src/lib/`, `apps/web/src/hooks/`)

### Dual-Mode API Adapter (`apps/web/src/lib/api-adapter.ts`)

Automatically switches between:
- **Real API** — When `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` are set
- **Dev Fixtures** — Fallback mode with clear console warning + "Dev fixtures active" badge

### Fixtures (`apps/web/src/fixtures/api-fixtures.ts`)

Full contract-compliant mock API with all error paths exercisable:
- Special tokens: `valid-<id>`, `expired-token`, `forbidden-token`
- Error paths: 401, 403, 409, 422, 5xx

### TanStack Query Hooks (`apps/web/src/hooks/useApi.ts`)

| Hook | Purpose |
|------|---------|
| `useCurrentUser()` | Fetches `/users/me` with 5min cache |
| `useUpdateCurrentUser()` | Mutates `/users/me` PATCH |
| `useWorkerProfile()` | Fetches `/worker-profiles/me` |
| `useCreateWorkerProfile()` | Mutates `/worker-profiles` POST |
| `useUpdateWorkerProfile()` | Mutates `/worker-profiles/me` PATCH |
| `useMyOrganizations()` | Fetches `/organizations/mine` |
| `useCreateOrganization()` | Mutates `/organizations` POST |
| `useInvalidateQueries()` / `usePrefetchQueries()` | Cache management helpers |

### Types (`apps/web/src/types/api.ts`)

**Single source of truth** matching frozen OpenAPI contract exactly:
- All request/response types match `docs/contracts/phase2.openapi.yaml`
- Contract drift check: `node --import tsx scripts/check-contract-drift.ts` ✅ 0 issues

---

## Phase 3 — UI/UX Polish & Accessibility

### Focus Management (`apps/web/src/hooks/`)

| Hook/Component | Purpose |
|----------------|---------|
| `useFocusTrap()` | Traps Tab/Shift+Tab within container; restores focus on deactivate |
| `FocusTrap` | Wrapper component for modals/dialogs with `role="dialog" aria-modal="true"` |
| `useFocusVisible()` | Detects keyboard vs mouse navigation; applies `:focus-visible` polyfill |

### CSS Accessibility (`apps/web/src/index.css`)

```css
/* Focus visible ring for keyboard navigation */
.focus-visible-ring:focus-visible { ... }

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) { ... }

/* High contrast mode */
@media (prefers-contrast: high) { ... }
```

### Components Updated

| Component | Accessibility |
|-----------|---------------|
| `Button` | `focus-visible-ring` class + `variant` prop (primary/secondary/outline/ghost) |
| `Input` | `focus-visible-ring` class |

---

## Phase 4 — Integration & Documentation

### Contract Drift Check

Automated script verifies TypeScript types match frozen OpenAPI contract:

```bash
node --import tsx scripts/check-contract-drift.ts
```

**Result:** ✅ 0 critical issues — All 9 OpenAPI schemas present in TypeScript

### Test Commands

```bash
# Frontend
cd apps/web
npm run typecheck    # TypeScript check
npm run build        # Production build
npm test             # Vitest (24 tests passing)

# Backend
cd services/api
python3 -m pytest -v # Pytest (health tests passing)
```

### Dev Fixtures Mode

When Supabase credentials not configured (local development):
- Auto-detects missing/placeholder env vars
- Logs clear warning: `"Dev fixtures active. Set VITE_API_BASE_URL..."`
- Shows "Dev fixtures active" badge in bottom-left corner
- All API calls use in-memory fixtures with realistic delays
- Special tokens for error testing: `valid-<id>`, `expired-token`, `forbidden-token`

### Environment Variables

**`.env.example`** (root):
```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=your-project-url
VITE_SUPABASE_ANON_KEY=your-anon-key
```

---

## File Ownership Map (`docs/OWNERSHIP_MAP.md`)

| Area | Owner | Paths |
|------|-------|-------|
| Frontend | **Dhwanit** | `apps/web/**` |
| Backend API & Auth | **Priyanshu** | `services/api/app/api/**`, `services/api/app/schemas/**`, `services/api/app/core/security.py` |
| Database & Infra | **Shresth** | `services/api/app/models/**`, `services/api/app/repositories/**`, `services/api/alembic/**`, `compose.yml` |

---

## Contract Reference

- **OpenAPI Contract:** `docs/contracts/phase2.openapi.yaml` (frozen)
- **Technical Contract:** `docs/contracts/PHASE_2_TECHNICAL_CONTRACT.md`
- **Project Blueprint:** `docs/SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md`
- **Ownership Map:** `docs/OWNERSHIP_MAP.md`
- **Decisions Log:** `docs/DECISIONS.md`

---

## Commit History (Frontend)

| Commit | Message | Phase |
|--------|---------|-------|
| `ac8ae4d` | API layer hardened with dual-mode adapter, fixes, etc. | Phase 1 |
| `347df06` | Added UI changes and some fixes, Passed 24 UI state tests | Phase 1 |
| `e88eec1` | Auth edge cases and session handling | Phase 2 |
| `89af9cc` | UI/UX Polish and accessibility | Phase 3 |

---

## Next Steps (Post-Phase 4)

When backend is ready for integration:

1. **Configure Supabase** — Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
2. **Run contract drift check** — Ensure no drift after backend changes
3. **Run E2E tests** — Full auth + profile + org flows with real backend
4. **Verify redirects** — Login flow with return URL, session expiry redirect
5. **Run contract drift check** — Confirm no drift after any backend changes

---

## Known Limitations / Future Work

| Item | Phase | Notes |
|------|-------|-------|
| Hire/Find Work marketplace | Phase 3+ | Currently placeholders |
| Real Supabase integration | Phase 3+ | Requires project setup |
| Rate limiting / CSRF | Future | Not in Phase 2 scope |
| Internationalization | Future | English only for MVP |
| Native mobile (PWA) | Future | Responsive web only |

---

**End of Handoff Document**  
All frontend work for Phases 2-4 complete and verified. Ready for backend integration.