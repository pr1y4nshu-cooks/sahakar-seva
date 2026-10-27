/**
 * API Type Definitions
 *
 * Single source of truth for all API types.
 * These MUST match the frozen OpenAPI contract exactly.
 * If the OpenAPI contract changes, regenerate these types or update manually.
 *
 * Source: docs/contracts/phase2.openapi.yaml
 */

// ===== Base Types =====

export type UUID = string;

// Type aliases matching OpenAPI contract names exactly
export type ErrorDetail = ApiErrorDetail;
export type ErrorResponse = ApiErrorResponse;
export type UserUpdate = UserUpdateRequest;
export type WorkerProfileCreate = WorkerProfileCreateRequest;
export type WorkerProfileUpdate = WorkerProfileUpdateRequest;
export type OrganizationCreate = OrganizationCreateRequest;

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

// ===== Health =====

export interface HealthResponse {
  status: string;
  service: string;
}

export interface DatabaseHealthResponse {
  status: string;
  database: string;
}

// ===== User =====

export interface User {
  id: UUID;
  display_name: string;
  email: string;
  created_at: string; // ISO 8601 UTC
  updated_at: string; // ISO 8601 UTC
}

export interface UserUpdateRequest {
  display_name: string;
}

// ===== Worker Profile =====

export type OnboardingStatus = 'draft' | 'pending_review' | 'approved' | 'restricted';

export interface WorkerProfile {
  id: UUID;
  user_id: UUID;
  display_name: string;
  bio: string | null;
  onboarding_status: OnboardingStatus;
  created_at: string;
  updated_at: string;
}

export interface WorkerProfileCreateRequest {
  display_name: string;
  bio?: string | null;
}

export interface WorkerProfileUpdateRequest {
  display_name?: string;
  bio?: string | null;
}

// ===== Organization =====

export type OrganizationType = 'business' | 'cooperative';
export type MembershipRole = 'owner' | 'admin' | 'member';

export interface OrganizationWithMyRole {
  id: UUID;
  name: string;
  organization_type: OrganizationType;
  my_membership_role: MembershipRole;
  created_at: string;
  updated_at: string;
}

export interface OrganizationCreateRequest {
  name: string;
  organization_type: OrganizationType;
}

// ===== Query Keys =====

export const queryKeys = {
  health: ['health'] as const,
  dbHealth: ['db-health'] as const,
  currentUser: ['user', 'current'] as const,
  workerProfile: ['worker-profile', 'me'] as const,
  organizations: ['organizations', 'mine'] as const,
} as const;