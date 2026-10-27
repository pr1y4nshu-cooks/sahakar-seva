/**
 * Development Fixtures
 *
 * Used when Supabase credentials or API base URL are not configured.
 * All fixtures obey the exact same contract shapes as the real API.
 * Includes error cases for 401, 403, 409, 422, 5xx.
 *
 * Import this ONLY through the api-adapter's getImplementation() method.
 */

import type {
  User,
  WorkerProfile,
  OrganizationWithMyRole,
  HealthResponse,
  DatabaseHealthResponse,
} from '@/types/api';
import { AuthError, NotFoundError, ConflictError, ValidationError, ApiError } from '@/lib/api-adapter';

// ===== Simulated State =====

interface FixtureState {
  currentUser: User | null;
  workerProfile: WorkerProfile | null;
  organizations: OrganizationWithMyRole[];
}

let state: FixtureState = {
  currentUser: null,
  workerProfile: null,
  organizations: [],
};

// Simulated delay to mimic network
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

// Simulated token validation
interface TokenValidationResult {
  valid: boolean;
  userId: string;
  forbidden?: boolean;
}

function validateToken(token: string | undefined): TokenValidationResult {
  if (!token) {
    return { valid: false, userId: '' };
  }

  // Special tokens for error testing
  if (token === 'expired-token') {
    return { valid: false, userId: '' };
  }
  if (token === 'forbidden-token') {
    return { valid: false, userId: '', forbidden: true };
  }

  // Valid tokens start with "valid-"
  if (token.startsWith('valid-')) {
    return { valid: true, userId: token.replace('valid-', '') };
  }

  return { valid: false, userId: '' };
}

// ===== Fixture Implementations =====

export const fixtures = {
  healthApi: {
    check: async (): Promise<HealthResponse> => {
      await delay(100);
      return { status: 'ok', service: 'api' };
    },
    checkDb: async (): Promise<DatabaseHealthResponse> => {
      await delay(100);
      return { status: 'ok', database: 'connected' };
    },
  },

  userApi: {
    getCurrent: async (token?: string): Promise<User> => {
      await delay(200);

      const validation = validateToken(token);
      if (!validation.valid) {
        if (validation.forbidden) {
          // For forbidden token, we still throw 401 (simulating 403 behavior)
          throw new AuthError('Forbidden: token belongs to different user', 403);
        }
        throw new AuthError('Missing or invalid bearer token', 401);
      }
      const userId = validation.userId;

      // Return existing user or create new one
      if (!state.currentUser || state.currentUser.id !== userId) {
        state.currentUser = {
          id: userId,
          display_name: 'Dev User',
          email: 'dev@example.com',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      }

      return state.currentUser;
    },

    update: async (data: { display_name: string }, token?: string): Promise<User> => {
      await delay(200);

      const { valid } = validateToken(token);
      if (!valid) {
        throw new AuthError('Missing or invalid bearer token', 401);
      }

      if (!data.display_name || data.display_name.trim().length < 2) {
        throw new ValidationError('display_name must be at least 2 characters');
      }
      if (data.display_name.trim().length > 80) {
        throw new ValidationError('display_name must be at most 80 characters');
      }

      if (!state.currentUser) {
        throw new NotFoundError('User not found');
      }

      state.currentUser = {
        ...state.currentUser,
        display_name: data.display_name.trim(),
        updated_at: new Date().toISOString(),
      };

      return state.currentUser;
    },
  },

  workerProfileApi: {
    create: async (data: { display_name: string; bio?: string | null }, token?: string): Promise<WorkerProfile> => {
      await delay(300);

      const validation = validateToken(token);
      if (!validation.valid) {
        if (validation.forbidden) {
          // For forbidden token, we still throw 401 (simulating 403 behavior)
          throw new AuthError('Forbidden: token belongs to different user', 403);
        }
        throw new AuthError('Missing or invalid bearer token', 401);
      }
      const userId = validation.userId;

      if (!data.display_name || data.display_name.trim().length < 2) {
        throw new ValidationError('display_name must be at least 2 characters');
      }
      if (data.display_name.trim().length > 80) {
        throw new ValidationError('display_name must be at most 80 characters');
      }
      if (data.bio && data.bio.length > 500) {
        throw new ValidationError('bio must be at most 500 characters');
      }

      if (state.workerProfile && state.workerProfile.user_id === userId) {
        throw new ConflictError('Worker profile already exists for this user');
      }

      const now = new Date().toISOString();
      state.workerProfile = {
        id: crypto.randomUUID(),
        user_id: userId,
        display_name: data.display_name.trim(),
        bio: data.bio?.trim() || null,
        onboarding_status: 'draft',
        created_at: now,
        updated_at: now,
      };

      return state.workerProfile;
    },

    getMine: async (token?: string): Promise<WorkerProfile> => {
      await delay(200);

      const validation = validateToken(token);
      if (!validation.valid) {
        if (validation.forbidden) {
          // For forbidden token, we still throw 401 (simulating 403 behavior)
          throw new AuthError('Forbidden: token belongs to different user', 403);
        }
        throw new AuthError('Missing or invalid bearer token', 401);
      }
      const userId = validation.userId;

      if (!state.workerProfile || state.workerProfile.user_id !== userId) {
        throw new NotFoundError('Worker profile not found');
      }

      return state.workerProfile;
    },

    update: async (data: { display_name?: string; bio?: string | null }, token?: string): Promise<WorkerProfile> => {
      await delay(300);

      const validation = validateToken(token);
      if (!validation.valid) {
        if (validation.forbidden) {
          // For forbidden token, we still throw 401 (simulating 403 behavior)
          throw new AuthError('Forbidden: token belongs to different user', 403);
        }
        throw new AuthError('Missing or invalid bearer token', 401);
      }
      const userId = validation.userId;

      if (!state.workerProfile || state.workerProfile.user_id !== userId) {
        throw new NotFoundError('Worker profile not found');
      }

      if (data.display_name !== undefined) {
        if (!data.display_name || data.display_name.trim().length < 2) {
          throw new ValidationError('display_name must be at least 2 characters');
        }
        if (data.display_name.trim().length > 80) {
          throw new ValidationError('display_name must be at most 80 characters');
        }
        state.workerProfile.display_name = data.display_name.trim();
      }

      if (data.bio !== undefined) {
        if (data.bio && data.bio.length > 500) {
          throw new ValidationError('bio must be at most 500 characters');
        }
        state.workerProfile.bio = data.bio?.trim() || null;
      }

      state.workerProfile.updated_at = new Date().toISOString();
      return state.workerProfile;
    },
  },

  organizationApi: {
    create: async (data: { name: string; organization_type: 'business' | 'cooperative' }, token?: string): Promise<OrganizationWithMyRole> => {
      await delay(400);

      const validation = validateToken(token);
      if (!validation.valid) {
        if (validation.forbidden) {
          // For forbidden token, we still throw 401 (simulating 403 behavior)
          throw new AuthError('Forbidden: token belongs to different user', 403);
        }
        throw new AuthError('Missing or invalid bearer token', 401);
      }
      const userId = validation.userId;

      if (!data.name || data.name.trim().length < 2) {
        throw new ValidationError('name must be at least 2 characters');
      }
      if (data.name.trim().length > 120) {
        throw new ValidationError('name must be at most 120 characters');
      }
      if (!['business', 'cooperative'].includes(data.organization_type)) {
        throw new ValidationError('organization_type must be business or cooperative');
      }

      const now = new Date().toISOString();
      const org: OrganizationWithMyRole = {
        id: crypto.randomUUID(),
        name: data.name.trim(),
        organization_type: data.organization_type,
        my_membership_role: 'owner',
        created_at: now,
        updated_at: now,
      };

      state.organizations.push(org);
      return org;
    },

    getMine: async (token?: string): Promise<OrganizationWithMyRole[]> => {
      await delay(200);

      const { valid } = validateToken(token);
      if (!valid) {
        throw new AuthError('Missing or invalid bearer token', 401);
      }

      return [...state.organizations];
    },
  },
};

// ===== Reset Helper (for tests) =====

export function resetFixtures(): void {
  state = {
    currentUser: null,
    workerProfile: null,
    organizations: [],
  };
}

// ===== Special Token Helpers (for testing error paths) =====

export const testTokens = {
  valid: (userId: string = 'user-123') => `valid-${userId}`,
  expired: 'expired-token',
  forbidden: 'forbidden-token',
  missing: undefined,
};