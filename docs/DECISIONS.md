# Architecture Decisions Log

## 2026-10-27: Phase 1 API Layer Hardening

### Decision: Dual-mode API Adapter with Automatic Fixture Fallback

**Context:** Frontend must work both with real Supabase backend and in development without credentials.

**Options Considered:**
1. Manual toggle via environment variable
2. Automatic detection based on env vars (chosen)
3. Separate build configurations

**Chosen Approach:** Automatic detection in `api-adapter.ts`:
- Checks `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- If any are placeholders/missing → `fixtures` mode
- Logs single clear console warning
- Shows "Dev fixtures active" badge in UI

**Rationale:** Zero-config DX for developers; no manual switching; same code paths for both modes.

### Decision: Fixture Contract Compliance

**Context:** Fixtures must be swappable with real API without component changes.

**Implementation:** 
- Fixtures in `src/fixtures/api-fixtures.ts` implement exact same interfaces as real API
- Include special tokens for error testing: `expired-token`, `forbidden-token`, valid tokens
- All validation matches OpenAPI contract (2-80 char display_name, 500 char bio, etc.)
- 401, 403, 409, 422, 5xx error paths all exercisable

### Decision: TanStack Query as Single Data Layer

**Context:** Need consistent caching, invalidation, and error handling across all pages.

**Implementation in `hooks/useApi.ts`:**
- Per-resource hooks (`useCurrentUser`, `useWorkerProfile`, `useMyOrganizations`)
- Mutations with automatic cache updates (`onSuccess` sets query data)
- Standardized retry logic (no retry on 401/403/404)
- Token provider pattern for auth integration
- Query keys as constants in `types/api.ts`

### Decision: Centralized Error Mapping

**Context:** Contract requires specific HTTP→UI mappings:
- 401 → redirect to sign-in with return path
- 403 → permission denial message
- 409 → duplicate conflict message
- 422 → field-level validation errors
- 5xx → retry-able error state

**Implementation:** Error classes in `api-adapter.ts` (`AuthError`, `ValidationError`, `NotFoundError`, `ConflictError`) with `isRetryable` flag. Components catch typed errors.

### Decision: Type Source of Truth

**Context:** Blueprint requires types match frozen OpenAPI contract exactly.

**Implementation:** `src/types/api.ts` manually maintained to match `docs/contracts/phase2.openapi.yaml`. 
- All request/response types defined
- Query keys as typed constants
- Enums for `OnboardingStatus`, `OrganizationType`, `MembershipRole`

**Future:** May switch to `openapi-typescript` generation when contract stabilizes.

### Decision: Auth Token Management

**Pattern:** Single token stored in `window.__SAHAKAR_AUTH_TOKEN__` and Supabase session.
- AuthProvider sets/clears on signIn/signOut/refresh
- `setTokenProvider` in `useApi.ts` reads from this global
- Fixtures mode uses special token strings (`valid-user-123`, `expired-token`, etc.)

---

## Upcoming Decisions (Phase 2+)

### Token Refresh Strategy
- Compare: background refresh vs. on-401 retry vs. SDK auto-refresh
- Arena evaluation when first auth issue encountered

### Error Boundary Placement
- Per-page vs. app-level vs. feature-level
- Test with actual error scenarios

### Cache Invalidation Strategy
- Current: `onSuccess` updates specific query data
- Alternative: Broad invalidation on any mutation
- Measure: actual network requests in devtools

---