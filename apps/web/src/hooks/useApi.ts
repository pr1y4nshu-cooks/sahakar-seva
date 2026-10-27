/**
 * TanStack Query Hooks
 *
 * Centralized query and mutation hooks for all API resources.
 * Provides consistent query keys, cache invalidation, and error handling.
 *
 * Usage:
 *   const { data, isLoading, error } = useCurrentUser();
 *   const mutation = useCreateWorkerProfile();
 */

import { useQuery, useMutation, useQueryClient, QueryKey } from '@tanstack/react-query';
import { api } from '@/lib/api-adapter';
import { queryKeys } from '@/types/api';
import type {
  User,
  UserUpdateRequest,
  WorkerProfile,
  WorkerProfileCreateRequest,
  WorkerProfileUpdateRequest,
  OrganizationWithMyRole,
  OrganizationCreateRequest,
} from '@/types/api';

// ===== Access Token Management =====

let getTokenFn: (() => Promise<string | null>) | null = null;

export function setTokenProvider(fn: () => Promise<string | null>): void {
  getTokenFn = fn;
}

async function getToken(): Promise<string | undefined> {
  if (getTokenFn) {
    const token = await getTokenFn();
    return token ?? undefined;
  }
  return undefined;
}

// ===== Health Hooks =====

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api.health.check(),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useDbHealth() {
  return useQuery({
    queryKey: queryKeys.dbHealth,
    queryFn: () => api.health.checkDb(),
    staleTime: 30_000,
    retry: 1,
  });
}

// ===== User Hooks =====

export function useCurrentUser(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.currentUser,
    queryFn: async () => {
      const token = await getToken();
      return api.user.getCurrent(token);
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60_000, // 5 minutes
    retry: (failureCount, error: any) => {
      // Don't retry on auth errors
      if (error?.status === 401 || error?.status === 403) return false;
      return failureCount < 2;
    },
  });
}

export function useUpdateCurrentUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: UserUpdateRequest) => {
      const token = await getToken();
      return api.user.update(data, token);
    },
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(queryKeys.currentUser, updatedUser);
    },
  });
}

// ===== Worker Profile Hooks =====

export function useWorkerProfile(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.workerProfile,
    queryFn: async () => {
      const token = await getToken();
      return api.workerProfile.getMine(token);
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60_000,
    retry: (failureCount, error: any) => {
      if (error?.status === 401 || error?.status === 403) return false;
      // Don't retry 404 - profile doesn't exist
      if (error?.status === 404) return false;
      return failureCount < 2;
    },
  });
}

export function useCreateWorkerProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: WorkerProfileCreateRequest) => {
      const token = await getToken();
      return api.workerProfile.create(data, token);
    },
    onSuccess: (newProfile) => {
      queryClient.setQueryData(queryKeys.workerProfile, newProfile);
    },
  });
}

export function useUpdateWorkerProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: WorkerProfileUpdateRequest) => {
      const token = await getToken();
      return api.workerProfile.update(data, token);
    },
    onSuccess: (updatedProfile) => {
      queryClient.setQueryData(queryKeys.workerProfile, updatedProfile);
    },
  });
}

// ===== Organization Hooks =====

export function useMyOrganizations(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.organizations,
    queryFn: async () => {
      const token = await getToken();
      return api.organization.getMine(token);
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60_000,
    retry: (failureCount, error: any) => {
      if (error?.status === 401 || error?.status === 403) return false;
      return failureCount < 2;
    },
  });
}

export function useCreateOrganization() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: OrganizationCreateRequest) => {
      const token = await getToken();
      return api.organization.create(data, token);
    },
    onSuccess: (newOrg) => {
      queryClient.setQueryData<OrganizationWithMyRole[]>(queryKeys.organizations, (old) =>
        old ? [...old, newOrg] : [newOrg]
      );
    },
  });
}

// ===== Generic Invalidation Helpers =====

export function useInvalidateQueries() {
  const queryClient = useQueryClient();

  return {
    invalidateUser: () => queryClient.invalidateQueries({ queryKey: queryKeys.currentUser }),
    invalidateWorkerProfile: () => queryClient.invalidateQueries({ queryKey: queryKeys.workerProfile }),
    invalidateOrganizations: () => queryClient.invalidateQueries({ queryKey: queryKeys.organizations }),
    invalidateAll: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.currentUser });
      queryClient.invalidateQueries({ queryKey: queryKeys.workerProfile });
      queryClient.invalidateQueries({ queryKey: queryKeys.organizations });
    },
  };
}

// ===== Prefetch Helpers (for navigation) =====

export function usePrefetchQueries() {
  const queryClient = useQueryClient();

  return {
    prefetchUser: () => queryClient.prefetchQuery({
      queryKey: queryKeys.currentUser,
      queryFn: async () => {
        const token = await getToken();
        return api.user.getCurrent(token);
      },
    }),
    prefetchWorkerProfile: () => queryClient.prefetchQuery({
      queryKey: queryKeys.workerProfile,
      queryFn: async () => {
        const token = await getToken();
        return api.workerProfile.getMine(token);
      },
    }),
    prefetchOrganizations: () => queryClient.prefetchQuery({
      queryKey: queryKeys.organizations,
      queryFn: async () => {
        const token = await getToken();
        return api.organization.getMine(token);
      },
    }),
  };
}