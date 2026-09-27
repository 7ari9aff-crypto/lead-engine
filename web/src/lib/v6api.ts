/**
 * V6 engine client — talks to the embedded V6 router (mounted under /v6 by
 * api/bridge.py on the legacy backend). Same-origin through the Vite proxy.
 */
import { api } from "./api";

export interface V6PrincipalOrg {
  orgId: string | null;
}

export interface V6Lead {
  id: string;
  company_id: string;
  contact_id: string | null;
  display: { name?: string; domain?: string; city?: string; industry?: string };
  masked_email: string | null;
  masked_phone: string | null;
  email_status: string | null;
  score: number | null;
  decision: string | null;
  state: string;
  built_at: string;
}

export interface V6Job {
  id: string;
  campaign_id: string | null;
  job_type: string;
  state: string;
  current_phase: string | null;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  created_at: string;
}

export interface V6Lineage {
  lead: { id: string; state: string; decision: string | null; score: number | null };
  qualification: { decision: string; reasons: string[]; created_at: string }[];
  scores: { score: number; score_version: string; explanations: string[] }[];
  claims: { field: string; value: string | null; truth_state: string }[];
  sources: { id: string; kind: string; url: string | null; provider_id: string | null }[];
  verifications: { status: string; provider_id: string | null }[];
  provider_calls: { provider_id: string; operation: string; status: string; cost_cents: number }[];
}

const BASE = "/v6";

export const v6Api = {
  health: () => api.get<{ status: string; system: string }>(`${BASE}/healthz`),

  createCampaign: (body: { name: string; icp: Record<string, unknown>; budget_cents?: number }) =>
    api.post<{ campaign_id: string; icp_version_id: string; job_id: string }>(
      `${BASE}/api/v1/campaigns`, body),

  jobs: (limit = 30) => api.get<V6Job[]>(`${BASE}/api/v1/jobs?limit=${limit}`),

  pending: (limit = 50) => api.get<V6Lead[]>(`${BASE}/api/v1/review/pending?limit=${limit}`),

  leads: (limit = 50) => api.get<V6Lead[]>(`${BASE}/api/v1/leads?limit=${limit}`),

  decide: (leadId: string, approve: boolean, reason = "") =>
    api.post<{ lead_id: string; state: string; policy: string }>(
      `${BASE}/api/v1/review/leads/${encodeURIComponent(leadId)}/decision`,
      { approve, reason }),

  lineage: (leadId: string) =>
    api.get<V6Lineage>(`${BASE}/api/v1/lineage/leads/${encodeURIComponent(leadId)}`),

  revealPii: (leadId: string, purpose: string, requestId?: string) =>
    api.post<{ contact_id: string; name?: string; role?: string; email?: string; phone?: string }>(
      `${BASE}/api/v1/leads/${encodeURIComponent(leadId)}/pii`,
      { purpose, request_id: requestId || `ui-${Date.now()}` }),
};
