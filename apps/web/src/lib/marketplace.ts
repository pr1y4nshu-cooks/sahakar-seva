/**
 * Marketplace API client (docs/contracts/MVP_MARKETPLACE_CONTRACT.md).
 * Always calls the real backend; there are no fixtures for marketplace data.
 */

import { request } from '@/lib/api-adapter';
import type { UUID } from '@/types/api';

export type Category = { id: UUID; slug: string; name: string; description: string | null };
export type Skill = { id: UUID; category_id: UUID; slug: string; name: string; description: string | null; is_active: boolean };
export type WorkerSkill = { skill: Skill; category: Category; declared_at: string; is_self_declared: true };
export type Locality = { slug: string; name: string; city: string; latitude: number; longitude: number };
export type RadiusKm = 2 | 5 | 10 | 15 | 25;
export const RADII: RadiusKm[] = [2, 5, 10, 15, 25];

export type ServiceSettings = {
  locality: string; latitude: number; longitude: number; radius_km: number; hourly_rate_paise: number;
  privacy_note: string; updated_at: string;
};
export type Slot = { id: UUID; starts_at: string; ends_at: string; is_active: boolean; booking_status: string | null };

export type WorkerResult = {
  worker_profile_id: UUID; display_name: string; bio: string | null; locality: string; distance_km: number;
  service_radius_km: number; hourly_rate_paise: number; onboarding_status: string; verification_label: string;
  skills: Skill[]; skills_are_self_declared: true;
  available_slots: { id: UUID; starts_at: string; ends_at: string; price_paise: number }[];
  match_reasons: string[];
};
export type SearchResponse = { results: WorkerResult[]; total: number; criteria: Record<string, unknown> };

export type BookingAction = 'accept' | 'decline' | 'cancel' | 'start' | 'complete' | 'dispute';
export type Settlement = {
  id: UUID; gross_paise: number; fee_bps: number; fee_paise: number; payout_paise: number; status: string;
  is_simulated: boolean; label: string; created_at: string;
};
export type Booking = {
  id: UUID; origin: 'direct' | 'job'; status: string; my_role: 'customer' | 'worker'; job_id: UUID | null;
  skill: Skill; worker_profile_id: UUID; worker_display_name: string; worker_verification_label: string;
  customer_display_name: string; starts_at: string; ends_at: string; locality: string;
  address_details: string | null; address_hidden_reason: string | null; customer_notes: string | null;
  price: { price_paise: number; fee_bps: number; fee_paise: number; payout_paise: number; fee_policy: string };
  settlement: Settlement | null;
  dispute: { id: UUID; status: string; description: string; outcome: string | null; resolution_reason: string | null; resolved_at: string | null; opened_by_me: boolean } | null;
  allowed_actions: BookingAction[]; created_at: string; updated_at: string;
};

export type Job = {
  id: UUID; title: string; description: string; skill: Skill; locality: string; starts_at: string; ends_at: string;
  budget_paise: number; status: string; organization_id: UUID | null; organization_name: string | null;
  distance_km: number | null; is_manager: boolean; address_details: string | null; application_count: number | null;
  my_application_status: string | null; i_declared_skill: boolean | null; booking_id: UUID | null; created_at: string;
};
export type Application = {
  id: UUID; job_id: UUID; job_title: string; job_starts_at: string; job_locality: string; job_budget_paise: number;
  status: string; message: string | null; worker_profile_id: UUID; worker_display_name: string;
  worker_verification_label: string; worker_distance_km: number | null; booking_id: UUID | null; created_at: string;
};
export type Earnings = {
  label: string; fee_policy: string;
  totals: { gross_paise: number; fee_paise: number; payout_paise: number; count: number; reconciles: boolean };
  settlements: (Settlement & { booking_id: UUID; starts_at: string; locality: string })[];
};
export type DisputeQueueItem = {
  id: UUID; booking_id: UUID; status: string; description: string; opened_by_role: 'customer' | 'worker';
  booking_status: string; skill_name: string; locality: string; starts_at: string; price_paise: number;
  customer_display_name: string; worker_display_name: string; can_resolve: boolean; outcome: string | null;
  resolution_reason: string | null; resolved_at: string | null; created_at: string;
};

const token = (): string | undefined => (window as any).__SAHAKAR_AUTH_TOKEN__ ?? undefined;
const get = <T,>(path: string) => request<T>(`/api/v1${path}`, {}, token());
const send = <T,>(method: string, path: string, body?: unknown) =>
  request<T>(`/api/v1${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) }, token());
const qs = (params: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && p.set(k, String(v)));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const marketplace = {
  categories: () => get<Category[]>('/service-categories'),
  skills: (categoryId?: string) => get<Skill[]>(`/skills${qs({ category_id: categoryId })}`),
  localities: () => get<Locality[]>('/localities'),

  mySkills: () => get<WorkerSkill[]>('/worker-profiles/me/skills'),
  addSkill: (skill_id: UUID) => send<WorkerSkill>('POST', '/worker-profiles/me/skills', { skill_id }),
  removeSkill: (skill_id: UUID) => send<void>('DELETE', `/worker-profiles/me/skills/${skill_id}`),
  serviceSettings: () => get<ServiceSettings>('/worker-profiles/me/service-settings'),
  saveServiceSettings: (body: Omit<ServiceSettings, 'privacy_note' | 'updated_at'>) =>
    send<ServiceSettings>('PUT', '/worker-profiles/me/service-settings', body),
  mySlots: () => get<Slot[]>('/worker-profiles/me/availability'),
  addSlot: (starts_at: string, ends_at: string) => send<Slot>('POST', '/worker-profiles/me/availability', { starts_at, ends_at }),
  removeSlot: (id: UUID) => send<void>('DELETE', `/worker-profiles/me/availability/${id}`),

  searchWorkers: (p: { latitude: number; longitude: number; radius_km: number; skill_id?: string; category_id?: string; starts_at?: string; ends_at?: string }) =>
    get<SearchResponse>(`/workers/search${qs(p)}`),

  requestBooking: (body: {
    worker_profile_id: UUID; slot_id: UUID; skill_id: UUID; locality: string; latitude: number; longitude: number;
    address_details: string; customer_notes?: string;
  }) => send<Booking>('POST', '/bookings', body),
  myBookings: () => get<Booking[]>('/bookings/mine'),
  bookingAction: (id: UUID, action: Exclude<BookingAction, 'dispute'>) => send<Booking>('POST', `/bookings/${id}/${action}`),
  openDispute: (id: UUID, description: string) => send<Booking>('POST', `/bookings/${id}/disputes`, { description }),
  earnings: () => get<Earnings>('/earnings/mine'),

  postJob: (body: {
    skill_id: UUID; title: string; description: string; locality: string; latitude: number; longitude: number;
    address_details: string; starts_at: string; duration_minutes: number; budget_paise: number; organization_id?: UUID;
  }) => send<Job>('POST', '/jobs', body),
  myJobs: () => get<Job[]>('/jobs/mine'),
  nearbyJobs: (skill_id?: string) => get<Job[]>(`/jobs/nearby${qs({ skill_id })}`),
  cancelJob: (id: UUID) => send<Job>('POST', `/jobs/${id}/cancel`),
  apply: (jobId: UUID, message?: string) => send<Application>('POST', `/jobs/${jobId}/applications`, { message: message || null }),
  jobApplications: (jobId: UUID) => get<Application[]>(`/jobs/${jobId}/applications`),
  selectApplicant: (jobId: UUID, applicationId: UUID) => send<Booking>('POST', `/jobs/${jobId}/applications/${applicationId}/select`),
  myApplications: () => get<Application[]>('/applications/mine'),
  withdraw: (id: UUID) => send<Application>('POST', `/applications/${id}/withdraw`),

  reviewerStatus: () => get<{ is_dispute_reviewer: boolean }>('/disputes/reviewer-status'),
  reviewQueue: () => get<DisputeQueueItem[]>('/disputes/review-queue'),
  resolveDispute: (id: UUID, outcome: string, reason: string) =>
    send<DisputeQueueItem>('POST', `/disputes/${id}/resolve`, { outcome, reason }),
};

// ===== formatting =====

export const rupees = (paise: number) =>
  `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: paise % 100 ? 2 : 0, maximumFractionDigits: 2 })}`;

export const when = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });

export const timeRange = (start: string, end: string) =>
  `${when(start)} – ${new Date(end).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}`;

export const errorMessage = (err: unknown) => (err as any)?.message ?? 'Something went wrong';

export const STATUS_STYLES: Record<string, string> = {
  requested: 'bg-amber-50 text-amber-700',
  confirmed: 'bg-emerald-50 text-emerald-700',
  in_progress: 'bg-blue-50 text-blue-700',
  completed: 'bg-ink/10 text-ink',
  cancelled: 'bg-rose-50 text-rose-700',
  declined: 'bg-rose-50 text-rose-700',
  disputed: 'bg-purple-50 text-purple-700',
  open: 'bg-emerald-50 text-emerald-700',
  filled: 'bg-blue-50 text-blue-700',
  applied: 'bg-amber-50 text-amber-700',
  selected: 'bg-emerald-50 text-emerald-700',
  rejected: 'bg-rose-50 text-rose-700',
  withdrawn: 'bg-ink/10 text-ink/60',
  resolved: 'bg-emerald-50 text-emerald-700',
};
