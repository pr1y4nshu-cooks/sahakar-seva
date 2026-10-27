const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type ApiHealth = { status: string; service: string };
export type DatabaseHealth = { status: string; database: string };

async function request<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { signal: controller.signal });
    if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

export const api = {
  health: () => request<ApiHealth>("/api/v1/health"),
  databaseHealth: () => request<DatabaseHealth>("/api/v1/health/db"),
};

