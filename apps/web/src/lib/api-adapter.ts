/**
 * API Adapter - Single entry point for all API calls
 *
 * Automatically switches between real backend and dev fixtures
 * based on environment configuration.
 *
 * - If VITE_API_BASE_URL is set and not placeholder -> real API
 * - If VITE_SUPABASE_URL/ANON_KEY are placeholders -> fixtures for auth
 * - Components never call fetch directly; they use this adapter
 */

import type {
  User,
  UserUpdateRequest,
  WorkerProfile,
  WorkerProfileCreateRequest,
  WorkerProfileUpdateRequest,
  OrganizationWithMyRole,
  OrganizationCreateRequest,
  HealthResponse,
  DatabaseHealthResponse,
  ApiErrorResponse,
} from '@/types/api';

// ===== Configuration Detection =====

const isPlaceholderUrl = (url: string | undefined): boolean => {
  if (!url) return true;
  return url.includes('placeholder') || url === 'https://placeholder.supabase.co';
};

const isPlaceholderKey = (key: string | undefined): boolean => {
  if (!key) return true;
  return key === 'placeholder-key';
};

export const apiMode = ((): 'real' | 'fixtures' => {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
  const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

  const hasRealApi = apiBaseUrl && apiBaseUrl !== 'http://localhost:8000' && !apiBaseUrl.includes('placeholder');
  const hasRealSupabase = !isPlaceholderUrl(supabaseUrl) && !isPlaceholderKey(supabaseAnonKey);

  // If either is placeholder, use fixtures
  if (!hasRealApi || !hasRealSupabase) {
    console.warn(
      '[API Adapter] Dev fixtures active. Set VITE_API_BASE_URL, VITE_SUPABASE_URL, and VITE_SUPABASE_ANON_KEY for real backend.'
    );
    return 'fixtures';
  }

  return 'real';
})();

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ===== Error Classes =====

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: ApiErrorResponse['error']['details'];
  isRetryable: boolean;

  constructor(message: string, status: number, code?: string, details?: ApiErrorResponse['error']['details']) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.isRetryable = status >= 500 || status === 0 || status === 408;
  }
}

export class AuthError extends ApiError {
  constructor(message: string, status: number = 401) {
    super(message, status, 'AUTH_ERROR');
    this.name = 'AuthError';
  }
}

export class ValidationError extends ApiError {
  constructor(message: string, details?: ApiErrorResponse['error']['details']) {
    super(message, 422, 'VALIDATION_ERROR', details);
    this.name = 'ValidationError';
  }
}

export class NotFoundError extends ApiError {
  constructor(message: string) {
    super(message, 404, 'RESOURCE_NOT_FOUND');
    this.name = 'NotFoundError';
  }
}

export class ConflictError extends ApiError {
  constructor(message: string) {
    super(message, 409, 'CONFLICT');
    this.name = 'ConflictError';
  }
}

// ===== Token Management =====

let currentAccessToken: string | null = null;
let tokenRefreshPromise: Promise<string> | null = null;

export function setAccessToken(token: string | null): void {
  currentAccessToken = token;
}

export function getAccessToken(): string | null {
  return currentAccessToken;
}

// ===== Request Helper =====

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const authToken = token ?? currentAccessToken;
  if (authToken) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${authToken}`;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      let errorData: ApiErrorResponse = { error: { code: 'UNKNOWN', message: 'Unknown error' } };
      try {
        errorData = (await response.json()) as ApiErrorResponse;
      } catch {
        // Ignore parse errors
      }

      const message = errorData.error?.message ?? `Request failed with status ${response.status}`;
      const code = errorData.error?.code;
      const details = errorData.error?.details;

      switch (response.status) {
        case 401:
          throw new AuthError(message, 401);
        case 403:
          throw new ApiError(message, 403, code, details);
        case 404:
          throw new NotFoundError(message);
        case 409:
          throw new ConflictError(message);
        case 422:
          throw new ValidationError(message, details);
        default:
          throw new ApiError(message, response.status, code, details);
      }
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

// ===== Health API =====

export const healthApi = {
  check: () => request<HealthResponse>('/api/v1/health'),
  checkDb: () => request<DatabaseHealthResponse>('/api/v1/health/db'),
};

// ===== User API =====

export const userApi = {
  getCurrent: (token?: string) => request<User>('/api/v1/users/me', {}, token),
  update: (data: UserUpdateRequest, token?: string) =>
    request<User>('/api/v1/users/me', { method: 'PATCH', body: JSON.stringify(data) }, token),
};

// ===== Worker Profile API =====

export const workerProfileApi = {
  create: (data: WorkerProfileCreateRequest, token?: string) =>
    request<WorkerProfile>('/api/v1/worker-profiles', { method: 'POST', body: JSON.stringify(data) }, token),
  getMine: (token?: string) => request<WorkerProfile>('/api/v1/worker-profiles/me', {}, token),
  update: (data: WorkerProfileUpdateRequest, token?: string) =>
    request<WorkerProfile>('/api/v1/worker-profiles/me', { method: 'PATCH', body: JSON.stringify(data) }, token),
};

// ===== Organization API =====

export const organizationApi = {
  create: (data: OrganizationCreateRequest, token?: string) =>
    request<OrganizationWithMyRole>('/api/v1/organizations', { method: 'POST', body: JSON.stringify(data) }, token),
  getMine: (token?: string) => request<OrganizationWithMyRole[]>('/api/v1/organizations/mine', {}, token),
};

// ===== Fixtures Import (lazy loaded) =====

let fixtures: {
  healthApi: typeof healthApi;
  userApi: typeof userApi;
  workerProfileApi: typeof workerProfileApi;
  organizationApi: typeof organizationApi;
} | null = null;

async function loadFixtures() {
  if (!fixtures) {
    const { fixtures: loadedFixtures } = await import('@/fixtures/api-fixtures');
    fixtures = loadedFixtures;
  }
  return fixtures;
}

// ===== Unified API Export =====

export const api = {
  health: healthApi,
  user: userApi,
  workerProfile: workerProfileApi,
  organization: organizationApi,

  // Use this to get the appropriate implementation based on mode
  getImplementation() {
    if (apiMode === 'fixtures') {
      return loadFixtures().then(f => ({
        health: f.healthApi,
        user: f.userApi,
        workerProfile: f.workerProfileApi,
        organization: f.organizationApi,
      }));
    }
    return Promise.resolve({
      health: healthApi,
      user: userApi,
      workerProfile: workerProfileApi,
      organization: organizationApi,
    });
  },

  // Helper to check current mode
  isFixturesMode: () => apiMode === 'fixtures',
};

// ===== Mode Badge Helper =====

export function getApiModeBadge(): { text: string; variant: 'dev' | 'prod' } {
  return apiMode === 'fixtures'
    ? { text: 'Dev fixtures active', variant: 'dev' }
    : { text: 'Production API', variant: 'prod' };
}