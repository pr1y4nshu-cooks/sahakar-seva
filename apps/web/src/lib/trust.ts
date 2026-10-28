/**
 * Trust-ledger API client (docs/contracts/TRUST_LEDGER_API_CONTRACT.md).
 * All financial values shown in the UI come from these server responses; nothing is recomputed for display.
 */

import { request } from '@/lib/api-adapter';
import type { UUID } from '@/types/api';
import type { Booking } from '@/lib/marketplace';

export type AnchorStatus =
  | 'LOCAL_ONLY' | 'ANCHOR_PENDING' | 'ANCHOR_SUBMITTED' | 'EXTERNALLY_ANCHORED' | 'ANCHOR_FAILED' | 'PROOF_INVALID';

export type Bearer = 'customer' | 'worker' | 'business' | 'platform';
export type PolicyComponent = {
  code: string; kind: 'platform_fee' | 'processing_charge' | 'tax'; label: string; bearer: Bearer; percent_bps: number;
  fixed_paise: number; min_paise: number | null; max_paise: number | null; applies_to_origins: ('direct' | 'job')[];
  organization_bookings: 'any' | 'only' | 'never'; description?: string;
};
export type Promotion = { code: string; label: string; waives: string[]; starts_at: string | null; ends_at: string | null; max_service_price_paise: number | null; organization_bookings: string };
export type PolicyDefinition = {
  format?: string; label: string; description: string; is_example: boolean; components: PolicyComponent[]; promotions: Promotion[];
  max_total_charge_bps: number; subscription_plan_code: string | null;
};
export type PolicyView = {
  fee_policy_record_id: UUID; policy_id: string; version: number; scope: 'default' | 'organization'; label: string; description: string;
  is_example: boolean; status: string; pricing_model: string; max_total_charge_bps: number; absolute_ceiling_bps: number;
  definition_hash: string; definition: PolicyDefinition; components: (PolicyComponent & { description: string })[];
  promotions: Promotion[]; subscription_plan_code: string | null; activated_at: string | null; retired_at: string | null;
};
export type Evaluation = {
  service_price_paise: number; customer_total_paise: number; worker_payout_paise: number; platform_fee_paise: number;
  processing_charge_paise: number; tax_paise: number; customer_borne_paise: number; business_borne_paise: number;
  worker_borne_paise: number; platform_borne_paise: number; waived_paise: number; effective_charge_bps: number;
  max_total_charge_bps: number; evaluated_at: string;
  lines: { code: string; kind: string; label: string; bearer: Bearer; computed_paise: number; amount_paise: number; waived_by: string | null }[];
};
export type FeePolicyResponse = {
  active_policy: PolicyView | null;
  examples: { service_price_paise: number; customer_total_paise?: number; worker_payout_paise?: number; platform_fee_paise?: number; processing_charge_paise?: number; waived_paise?: number; error?: string }[];
  examples_note: string;
  rules: {
    assessed_when: string; cancellations: string; disputes: string; existing_agreements: string; bearers: Record<Bearer, string>;
    tax_note: string; processing_note: string; payments_mode: 'simulated' | 'live'; payments_note: string;
    free_for_individuals: string[]; not_final_pricing: string;
  };
};
export type SimulationRun = {
  items: ({ service_price_paise: number; origin: string; for_organization: boolean; refused?: string } & Partial<Evaluation>)[];
  totals: { bookings: number; refused: number; service_price_paise: number; customer_total_paise: number; worker_payout_paise: number;
    platform_fee_paise: number; processing_charge_paise: number; platform_borne_paise: number; waived_paise: number };
};
export type Simulation = { pricing_model: string; definition_hash: string; samples: SimulationRun; recorded_bookings?: SimulationRun; recorded_note?: string };

export type LedgerTx = {
  id: UUID; transaction_type: 'simulated_booking_settlement' | 'simulated_settlement_reversal'; amount_paise: number;
  currency: string; idempotency_key: string; settlement_id: UUID | null; reverses_transaction_id: UUID | null;
  is_simulated: boolean; created_at: string; total_debits_paise: number; total_credits_paise: number; balanced: boolean;
  entries: { index: number; account: string; direction: 'debit' | 'credit'; amount_paise: number }[];
};

export type FinancialRecord = {
  booking_id: UUID; booking_status: string; agreement: NonNullable<Booking['agreement']>;
  quote_versions: {
    quote_id: UUID; version: number; source: string; pricing_basis: string; customer_total_paise: number;
    worker_share_paise: number; platform_fee_paise: number; fee_bps: number; initiated_by_role: string; created_at: string;
    acceptances: { role: 'customer' | 'worker'; accepted_at: string }[];
  }[];
  settlement: { id: UUID; gross_paise: number; fee_paise: number; payout_paise: number; is_simulated: boolean; label: string; created_at: string } | null;
  ledger_transactions: LedgerTx[];
  events: { sequence: number; event_type: string; event_hash: string; previous_event_hash: string; created_at: string; checkpoint_index: number | null; anchor_status: AnchorStatus | null }[];
  evidence: NonNullable<Booking['evidence']>;
  accounting_note: string;
};

export type RepeatOptions = {
  previous_booking_id: UUID; eligible: boolean; reason: string | null; worker_profile_id: UUID; worker_display_name: string;
  worker_verification_label: string; current_hourly_rate_paise: number | null;
  skill: { id: UUID; name: string }; locality: string; address_details: string;
  available_slots: { id: UUID; starts_at: string; ends_at: string; price_paise: number; service_price_paise: number; customer_total_paise: number | null; worker_payout_paise: number | null }[];
  fee_policy: PolicyView | null; terms: string;
};

export type OrgSummary = {
  organization_id: UUID; organization_name: string; organization_type: string; jobs_posted: number; bookings_created: number;
  completed_bookings: number; agreed_spend_completed_paise: number; platform_fees_completed_paise: number; agreed_spend_open_paise: number;
  bookings: {
    booking_id: UUID; job_id: UUID; job_title: string; skill_name: string; starts_at: string; status: string; worker_display_name: string;
    quote_version: number | null; evidence_level: string; customer_total_paise: number; platform_fee_paise: number; worker_share_paise: number;
    simulated_settlement: boolean; ledger_reversed: boolean;
  }[];
  note: string; scope_note: string;
};

export type EconomicsSummary = {
  source: string; completed_bookings: number; total_booking_value_paise: number; total_simulated_platform_fees_paise: number;
  total_simulated_worker_payouts_paise: number; average_booking_value_paise: number; average_fee_per_booking_paise: number;
  effective_fee_bps: number; settlements_with_ledger_evidence: number; total_party_borne_charges_paise: number;
  ledger_platform_fee_allocations_paise: number; ledger_processing_charge_allocations_paise: number;
  active_policy: { policy_id: string; version: number; label: string; is_example: boolean; pricing_model: string } | null;
  legacy_settlements_without_ledger: number; reversed_settlements: number; reversed_value_paise: number; note: string;
};

export type AnchoringConfig = {
  tsa_configured: boolean; tsa_name: string | null; tsa_url: string | null; trust_anchor_sha256: string | null;
  protocol: string; data_sent: string; statuses: Record<AnchorStatus, string>;
};

const token = (): string | undefined => (window as any).__SAHAKAR_AUTH_TOKEN__ ?? undefined;
const get = <T,>(path: string) => request<T>(`/api/v1${path}`, {}, token());
const send = <T,>(method: string, path: string, body?: unknown) =>
  request<T>(`/api/v1${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) }, token());

export const trust = {
  feePolicy: () => get<FeePolicyResponse>('/fee-policy'),
  feePolicyHistory: () => get<Omit<PolicyView, 'definition'>[]>('/fee-policies'),
  preview: (service_price_paise: number, origin: 'direct' | 'job' = 'direct') =>
    send<{ policy: { policy_id: string; version: number; label: string; is_example: boolean; pricing_model: string; definition_hash: string }; evaluation: Evaluation; note: string }>(
      'POST', '/pricing/preview', { service_price_paise, origin }),
  simulate: (definition: PolicyDefinition, sample_service_prices_paise: number[], include_recorded_bookings = false) =>
    send<Simulation>('POST', '/pricing/simulate', { definition, sample_service_prices_paise, include_recorded_bookings }),
  anchoring: () => get<AnchoringConfig>('/trust/anchoring'),
  financialRecord: (bookingId: UUID) => get<FinancialRecord>(`/bookings/${bookingId}/financial-record`),
  receipt: (bookingId: UUID) => get<Record<string, unknown>>(`/bookings/${bookingId}/receipt`),
  reviseQuote: (bookingId: UUID, service_price_paise: number) =>
    send<Booking>('POST', `/bookings/${bookingId}/quote-revisions`, { service_price_paise }),
  acceptQuote: (bookingId: UUID, version: number) => send<Booking>('POST', `/bookings/${bookingId}/quotes/${version}/accept`),
  acceptBooking: (bookingId: UUID, quote_version: number | null) =>
    send<Booking>('POST', `/bookings/${bookingId}/accept`, quote_version ? { quote_version } : {}),
  repeatOptions: (bookingId: UUID) => get<RepeatOptions>(`/bookings/${bookingId}/repeat-options`),
  orgSummary: (orgId: UUID) => get<OrgSummary>(`/organizations/${orgId}/financial-summary`),
  economics: () => get<EconomicsSummary>('/economics/summary'),
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Download the participant's receipt as a JSON file they keep independently. */
export async function downloadReceipt(bookingId: UUID): Promise<Record<string, unknown>> {
  const body = await trust.receipt(bookingId);
  saveBlob(new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' }), `sahakar-receipt-${bookingId}.json`);
  return body;
}

export async function downloadOrgCsv(orgId: UUID): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/organizations/${orgId}/financial-report.csv`, {
    headers: token() ? { Authorization: `Bearer ${token()}` } : {},
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  saveBlob(await res.blob(), `sahakar-org-${orgId}.csv`);
}

export type Overview = {
  available_workers: number; service_categories: number; skills: number; open_jobs: number; is_demo_dataset: boolean;
  demo_label: string | null; sample_data_share: { workers: number; open_jobs: number }; default_locality: string | null; note: string | null;
};
export type OpenJob = {
  id: UUID; title: string; description: string; skill: { id: UUID; name: string; slug: string }; locality: string; starts_at: string;
  ends_at: string; budget_paise: number; organization_name: string | null; is_synthetic_demo: boolean;
};
export type ShowcaseItem = {
  key: string; label: string; description: string; status: string; service: string | null; locality: string; pricing_model: string | null;
  fee_policy_id: string | null; service_price_paise: number; customer_total_paise: number; worker_payout_paise: number;
  platform_charges_paise: number; anchor_status: AnchorStatus | null; anchor_label: string;
};
export type DemoGuide = {
  enabled: boolean; label: string; dataset: string; personas: { email: string; name: string; role: string }[];
  steps: { title: string; route: string; hint: string }[]; showcase: ShowcaseItem[];
  external_anchoring: { tsa_configured: boolean; tsa_name: string | null; checkpoints_by_status: Record<string, number> };
  passcode_note: string; synthetic_note: string;
};

export const publicApi = {
  overview: () => get<Overview>('/marketplace/overview'),
  openJobs: (skill_id?: string, sampleOnly = false) => get<OpenJob[]>(`/jobs/open?${new URLSearchParams({ ...(skill_id ? { skill_id } : {}), ...(sampleOnly ? { sample_only: 'true' } : {}) })}`),
  demoGuide: () => get<DemoGuide>('/demo/guide'),
  showcaseReceipt: (key: string) => get<Record<string, any>>(`/demo/showcase/${key}/receipt`),
  booking: (id: UUID) => get<Booking>(`/bookings/${id}`),
};

export const ANCHOR_LABELS: Record<AnchorStatus, string> = {
  LOCAL_ONLY: 'Local integrity only — no external timestamp yet',
  ANCHOR_PENDING: 'External timestamp pending',
  ANCHOR_SUBMITTED: 'External timestamp requested',
  EXTERNALLY_ANCHORED: 'External timestamp verified',
  ANCHOR_FAILED: 'External timestamp failed — local integrity only',
  PROOF_INVALID: 'External timestamp response failed verification',
};

export const BEARER_LABELS: Record<Bearer, string> = {
  customer: 'Paid by customer (added to total)',
  worker: 'Borne by worker (deducted from payout)',
  business: 'Billed to the organization',
  platform: 'Absorbed by the platform',
};

export function describeComponent(c: Pick<PolicyComponent, 'percent_bps' | 'fixed_paise' | 'min_paise' | 'max_paise'>): string {
  const r = (p: number) => `₹${(p / 100).toLocaleString('en-IN')}`;
  const parts = [c.percent_bps ? `${c.percent_bps / 100}% of the service price` : '', c.fixed_paise ? `${r(c.fixed_paise)} fixed` : ''].filter(Boolean);
  let t = parts.join(' + ') || '₹0';
  if (c.min_paise !== null) t += `, at least ${r(c.min_paise)}`;
  if (c.max_paise !== null) t += `, at most ${r(c.max_paise)}`;
  return t;
}
