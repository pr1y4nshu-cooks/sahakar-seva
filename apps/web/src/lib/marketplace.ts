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
  dispute: {
    id: UUID; status: string; description: string; outcome: string | null; resolution_reason: string | null; resolved_at: string | null;
    opened_by_me: boolean; category?: string | null; related_quote_version?: number | null; ledger_correction?: string | null;
  } | null;
  allowed_actions: BookingAction[]; created_at: string; updated_at: string;
  agreement_actions?: AgreementAction[];
  agreement?: Agreement | null;
  evidence?: Evidence | null;
  repeat_of_booking_id?: UUID | null;
  is_synthetic_demo?: boolean;
};

export type AgreementAction = 'revise_quote' | 'accept_quote' | 'repeat' | 'download_receipt';
export type AgreementLine = {
  code: string; kind: 'platform_fee' | 'processing_charge' | 'tax'; label: string; bearer: 'customer' | 'worker' | 'business' | 'platform';
  percent_bps: number; fixed_paise: number; min_paise: number | null; max_paise: number | null; computed_paise: number;
  amount_paise: number; waived_by: string | null; description?: string;
};
export type Agreement = {
  service_price_paise: number; pricing_model: string | null; policy_definition_hash: string | null; is_example_policy: boolean | null;
  policy_label?: string | null; line_items: AgreementLine[]; processing_note?: string | null;
  evidence_level: 'versioned' | 'legacy_snapshot' | 'legacy'; note: string | null; quote_id: UUID | null; quote_version: number | null;
  source: string | null; versions: number; customer_total_paise: number; worker_share_paise: number; platform_fee_paise: number;
  additional_charges_paise: number; tax_paise: number; taxes_modeled: boolean; fee_bps: number; fee_policy_id: string | null;
  fee_policy_version: string | null; currency: string; created_at: string | null; customer_accepted_at: string | null;
  worker_accepted_at: string | null; awaiting_acceptance_from: 'customer' | 'worker' | null; matches_booking_snapshot: boolean;
  tax_note: string; additional_charges_note: string;
};
export type Evidence = {
  payment_evidence: string; payment_evidence_status: 'SIMULATED';
  ledger_status: 'posted' | 'reversed' | 'legacy_not_posted' | 'not_applicable_yet';
  ledger_transaction_id: UUID | null; ledger_balanced: boolean | null; reversal_transaction_id: UUID | null;
  event_count: number; latest_event_hash: string | null;
  anchor: { status: string | null; label: string; checkpoint_index: number | null; tsa_gen_time: string | null; events_externally_anchored: number; events_total: number };
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
  ledger_totals?: { reversed_payout_paise: number; net_simulated_payout_paise: number; posted_with_ledger: number } | null;
  settlements: (Settlement & { booking_id: UUID; starts_at: string; locality: string; ledger_transaction_id?: UUID | null;
    ledger_status?: string; reversed?: boolean; customer_total_paise?: number })[];
};
export type DisputeQueueItem = {
  id: UUID; booking_id: UUID; status: string; description: string; opened_by_role: 'customer' | 'worker';
  booking_status: string; skill_name: string; locality: string; starts_at: string; price_paise: number;
  customer_display_name: string; worker_display_name: string; can_resolve: boolean; outcome: string | null;
  resolution_reason: string | null; resolved_at: string | null; created_at: string;
  category?: string | null; related_quote_version?: number | null; ledger_correction?: string | null; has_simulated_settlement?: boolean;
};

const token = (): string | undefined => (window as any).__SAHAKAR_AUTH_TOKEN__ ?? undefined;
const get = <T,>(path: string) => request<T>(`/api/v1${path}`, {}, token());
const send = <T,>(method: string, path: string, body?: unknown) =>
  request<T>(`/api/v1${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) }, token());
const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && v !== false && p.set(k, String(v)));
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

  searchWorkers: (p: { latitude: number; longitude: number; radius_km: number; skill_id?: string; category_id?: string; starts_at?: string; ends_at?: string; sample_only?: boolean }) =>
    get<SearchResponse>(`/workers/search${qs(p)}`),

  requestBooking: (body: {
    worker_profile_id: UUID; slot_id: UUID; skill_id: UUID; locality: string; latitude: number; longitude: number;
    address_details: string; customer_notes?: string; repeat_of_booking_id?: UUID;
  }) => send<Booking>('POST', '/bookings', body),
  myBookings: () => get<Booking[]>('/bookings/mine'),
  bookingAction: (id: UUID, action: Exclude<BookingAction, 'dispute'>) => send<Booking>('POST', `/bookings/${id}/${action}`),
  openDispute: (id: UUID, description: string, category?: string, receipt_event_hash?: string) =>
    send<Booking>('POST', `/bookings/${id}/disputes`, { description, ...(category ? { category } : {}), ...(receipt_event_hash ? { receipt_event_hash } : {}) }),
  earnings: () => get<Earnings>('/earnings/mine'),

  postJob: (body: {
    skill_id: UUID; title: string; description: string; locality: string; latitude: number; longitude: number;
    address_details: string; starts_at: string; duration_minutes: number; budget_paise: number; organization_id?: UUID;
  }) => send<Job>('POST', '/jobs', body),
  myJobs: () => get<Job[]>('/jobs/mine'),
  job: (id: UUID) => get<Job>(`/jobs/${id}`),
  nearbyJobs: (skill_id?: string) => get<Job[]>(`/jobs/nearby${qs({ skill_id })}`),
  cancelJob: (id: UUID) => send<Job>('POST', `/jobs/${id}/cancel`),
  apply: (jobId: UUID, message?: string) => send<Application>('POST', `/jobs/${jobId}/applications`, { message: message || null }),
  jobApplications: (jobId: UUID) => get<Application[]>(`/jobs/${jobId}/applications`),
  selectApplicant: (jobId: UUID, applicationId: UUID) => send<Booking>('POST', `/jobs/${jobId}/applications/${applicationId}/select`),
  myApplications: () => get<Application[]>('/applications/mine'),
  withdraw: (id: UUID) => send<Application>('POST', `/applications/${id}/withdraw`),

  reviewerStatus: () => get<{ is_dispute_reviewer: boolean }>('/disputes/reviewer-status'),
  reviewQueue: () => get<DisputeQueueItem[]>('/disputes/review-queue'),
  resolveDispute: (id: UUID, outcome: string, reason: string, ledger_correction: 'none' | 'full_reversal' = 'none') =>
    send<DisputeQueueItem>('POST', `/disputes/${id}/resolve`, { outcome, reason, ledger_correction }),
};

// ===== formatting =====

export const rupees = (paise: number) =>
  `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: paise % 100 ? 2 : 0, maximumFractionDigits: 2 })}`;

export const when = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });

export const DISPUTE_CATEGORIES: [string, string][] = [
  ['customer_total_differs', 'Customer total differs from the agreed quote'],
  ['worker_payout_differs', 'Worker payout differs from the agreed amount'],
  ['unexpected_deduction', 'Unexpected deduction'],
  ['payment_evidence_mismatch', 'Payment evidence mismatch'],
  ['receipt_verification_failed', 'Receipt verification failed'],
  ['other_booking_issue', 'Other booking problem'],
];

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
