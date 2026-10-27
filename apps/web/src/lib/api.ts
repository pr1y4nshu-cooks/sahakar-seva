const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type ApiHealth = { status: string; service: string };
export type DatabaseHealth = { status: string; database: string };

// Phase 2 Types
export type User = {
  id: string;
  display_name: string;
  email: string;
  created_at: string;
  updated_at: string;
};

export type WorkerProfile = {
  id: string;
  user_id: string;
  display_name: string;
  bio: string | null;
  onboarding_status: "draft" | "pending_review" | "approved" | "restricted";
  created_at: string;
  updated_at: string;
};

export type Organization = {
  id: string;
  name: string;
  organization_type: "business" | "cooperative";
  my_membership_role: "owner" | "admin" | "member";
  created_at: string;
  updated_at: string;
};

export type ApiError = {
  error: {
    code: string;
    message: string;
    details?: Array<{ field?: string; message: string }>;
  };
};

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10000);

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorData = (await response.json().catch(() => ({}))) as ApiError;
      const message = errorData.error?.message ?? `Request failed with status ${response.status}`;
      const error = new Error(message) as Error & {
        status: number;
        code?: string;
        details?: ApiError["error"]["details"];
      };
      error.status = response.status;
      error.code = errorData.error?.code;
      error.details = errorData.error?.details;
      throw error;
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

export const api = {
  // Health endpoints (existing)
  health: () => request<ApiHealth>("/api/v1/health"),
  databaseHealth: () => request<DatabaseHealth>("/api/v1/health/db"),

  // Phase 2: User endpoints
  getCurrentUser: (token: string) => request<User>("/api/v1/users/me", {}, token),
  updateCurrentUser: (token: string, data: { display_name: string }) =>
    request<User>("/api/v1/users/me", { method: "PATCH", body: JSON.stringify(data) }, token),

  // Phase 2: Worker Profile endpoints
  createWorkerProfile: (token: string, data: { display_name: string; bio?: string }) =>
    request<WorkerProfile>("/api/v1/worker-profiles", { method: "POST", body: JSON.stringify(data) }, token),
  getMyWorkerProfile: (token: string) => request<WorkerProfile>("/api/v1/worker-profiles/me", {}, token),
  updateMyWorkerProfile: (token: string, data: { display_name?: string; bio?: string }) =>
    request<WorkerProfile>("/api/v1/worker-profiles/me", { method: "PATCH", body: JSON.stringify(data) }, token),

  // Phase 2: Organization endpoints
  createOrganization: (token: string, data: { name: string; organization_type: "business" | "cooperative" }) =>
    request<Organization>("/api/v1/organizations", { method: "POST", body: JSON.stringify(data) }, token),
  getMyOrganizations: (token: string) => request<Organization[]>("/api/v1/organizations/mine", {}, token),
};