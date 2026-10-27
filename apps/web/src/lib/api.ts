/**
 * API Client - Legacy Compatibility Layer
 *
 * @deprecated Use the new api-adapter and hooks instead.
 * This file is kept for backward compatibility during migration.
 * New code should import from '@/lib/api-adapter' or use '@/hooks/useApi'.
 */

import { api } from '@/lib/api-adapter';
import type {
  HealthResponse,
  DatabaseHealthResponse,
  User,
  WorkerProfile,
  OrganizationWithMyRole,
} from '@/types/api';

// Re-export types for backward compatibility
export type { HealthResponse as ApiHealth, DatabaseHealthResponse as DatabaseHealth, User, WorkerProfile, OrganizationWithMyRole as Organization };

// Legacy API object (for components not yet migrated)
export const legacyApi = {
  health: () => api.health.check(),
  databaseHealth: () => api.health.checkDb(),
  getCurrentUser: async (token: string) => api.getImplementation().then(i => i.user.getCurrent(token)),
  updateCurrentUser: async (token: string, data: { display_name: string }) =>
    api.getImplementation().then(i => i.user.update(data, token)),
  createWorkerProfile: async (token: string, data: { display_name: string; bio?: string }) =>
    api.getImplementation().then(i => i.workerProfile.create(data, token)),
  getMyWorkerProfile: async (token: string) => api.getImplementation().then(i => i.workerProfile.getMine(token)),
  updateMyWorkerProfile: async (token: string, data: { display_name?: string; bio?: string }) =>
    api.getImplementation().then(i => i.workerProfile.update(data, token)),
  createOrganization: async (token: string, data: { name: string; organization_type: "business" | "cooperative" }) =>
    api.getImplementation().then(i => i.organization.create(data, token)),
  getMyOrganizations: async (token: string) => api.getImplementation().then(i => i.organization.getMine(token)),
};

export default legacyApi;