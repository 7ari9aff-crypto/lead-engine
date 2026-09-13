// API client for the Lead Engine backend.
// All requests go through Vite proxy in dev and the configured backend in prod.
// Auth: Supabase Bearer token when a session exists; cookie fallback otherwise.

import { getAccessToken } from "@/lib/supabase";

const BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T = any>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const url = `${BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  const token = await getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, {
    credentials: "include",
    headers,
    ...init,
  });
  const text = await res.text();
  let body: any = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {}
  if (!res.ok) {
    const msg =
      (body && (body.error || body.detail || body.message)) ||
      `HTTP ${res.status}`;
    throw new ApiError(typeof msg === "string" ? msg : JSON.stringify(msg), res.status, body);
  }
  return body as T;
}

export const api = {
  get: <T = any>(p: string) => request<T>(p, { method: "GET" }),
  post: <T = any>(p: string, body?: any) =>
    request<T>(p, { method: "POST", body: body != null ? JSON.stringify(body) : undefined }),
  put: <T = any>(p: string, body?: any) =>
    request<T>(p, { method: "PUT", body: body != null ? JSON.stringify(body) : undefined }),
  patch: <T = any>(p: string, body?: any) =>
    request<T>(p, { method: "PATCH", body: body != null ? JSON.stringify(body) : undefined }),
  delete: <T = any>(p: string) => request<T>(p, { method: "DELETE" }),
};

// ===== Typed shapes (matched to /api/status + per-resource endpoints) =====

export type ProviderRow = {
  name: string;
  task: string;
  type?: string;
  priority?: number;
  status: "active" | "degraded" | "disabled" | "exhausted" | "unknown";
  status_reason?: string | null;
  cooldown_until?: string | null;
  key_env?: string | null;
  env_key?: string | null;
  has_key?: boolean;
  is_local?: boolean;
  quota_kind?: string;
  quota_limit?: number | null;
  quota_used?: number;
  period?: string | null;
  rpm_limit?: number | null;
  base_url?: string | null;
  model_name?: string | null;
  calls?: number;
  units?: number;
  last_used?: string | null;
  // derived in UI
  key_state?: "set" | "missing" | "local" | "unknown";
};

export type JobRow = {
  job_id: string;
  icp_id: string;
  state: "QUEUED" | "RUNNING" | "DEGRADED" | "COMPLETED" | "PAUSED" | "RESUMING" | "FAILED";
  pause_reason: string | null;
  resume_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  started_at?: string | null;
  metrics?: any;
  params?: any;
};

export type LeadRow = {
  lead_id?: string | null;
  name: string;
  city?: string | null;
  domain?: string | null;
  website?: string | null;
  phone?: string | null;
  email?: string | null;
  email_status?: string | null;
  tier?: string | null;
  score?: number | null;
  decision_maker?: string | null;
  stage: "ACCEPTED" | "REVIEW" | "REJECTED";
  legal_status?: string | null;
  job_id?: string | null;
};

export type KeyCard = {
  index: number | null;
  masked: string | null;
  calls: number;
  units: number;
  prompt_tokens: number;
  completion_tokens: number;
  last_used: string | null;
};

export type ProviderUsageRow = {
  provider: string;
  env_key: string;
  docs_url: string;
  keys_configured: number;
  keys: KeyCard[];
  usage: {
    calls: number;
    units: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  quota: {
    kind: string | null;
    limit: number | null;
    used: number;
    percent: number | null;
  };
  live: { usage_source: string; used: number | null; limit: number | null; percent: number | null } | null;
  status: string | null;
};

export type KeyUsageResponse = {
  providers: ProviderUsageRow[];
  totals: { prompt_tokens: number; completion_tokens: number; calls: number };
};

export type ActivityEvent = {
  id: number;
  ts: string;
  kind: string;
  payload: any;
  correlation_id: string | null;
};

export type IntegrationRow = {
  provider: string;
  configured: boolean;
  connected: boolean;
  status: string | null;
  scopes: string[];
  expires_at: string | null;
};

export type SuppressionEntry = {
  id: string;
  channel: string;
  value: string;
  reason: string;
  source: string;
  created_at: string;
};

// ===== Stage 3 — agentic research & human review =====

export type FactNode = {
  value: string;
  value_kind?: string;
  status: "VERIFIED" | "CONFLICTED" | "STALE" | "UNVERIFIED" | "INFERRED";
  confidence: number | null;
  collected_at: string | null;
  expires_at: string | null;
  fact_id: string;
  sources: { source_url: string | null; source_kind: string; provider: string | null; quote: string | null }[];
  alternatives?: { value: string; status: string; fact_id: string }[];
};

export type FactSnapshot = {
  subject_kind: string;
  subject_id: string;
  fields: Record<string, FactNode>;
  conflicts: { conflict_id: string; field: string; fact_a: string; fact_b: string; resolution: string }[];
  stale_fields: string[];
};

export type Presentation = {
  lead: {
    lead_id: string | null;
    job_id: string | null;
    stage: string | null;
    score: number | null;
    qualification_score: number | null;
    tier: string | null;
    disposition: "APPROVE_CONTACT" | "REJECT" | "RESEARCH_MORE" | "SAVE_FOR_LATER" | null;
    disposition_note: string | null;
    disposition_at: string | null;
  };
  subject: { kind: string; id: string };
  identity: Record<string, { value: string; status: string; confidence: number } | null | undefined>;
  fit: {
    fit_score: number | null;
    tier: string | null;
    why: string[];
    confidence: number | null;
    blockers: string[];
    processing_mode?: string | null;
    deterministic?: boolean;
  };
  verification: {
    email_status: string | null;
    email_confidence: number | null;
    verified_facts: number;
    contact_coverage: Record<string, boolean>;
  };
  facts_snapshot: FactSnapshot;
  missing_information: string[];
  conflicts: FactSnapshot["conflicts"];
  stale_fields: string[];
  sources_count: number;
};

export type ResearchProgress = {
  job_id: string;
  state: string;
  pause_reason?: string | null;
  objective: string | null;
  counters: Record<string, number>;
  budgets: Record<string, { used: number; limit: number }>;
  stop_reason: string | null;
  parent_job_id: string | null;
  stats: {
    candidates: number;
    verified_facts: number;
    all_facts: number;
    open_conflicts: number;
    open_questions: number;
    visited_sources: number;
  };
  note?: string | null;
};

export type Entitlements = {
  organization_id: string | null;
  limits: Record<string, unknown>;
};

export type StatusResponse = {
  version: string;
  providers: ProviderRow[];
  jobs_by_state: Record<string, number>;
  recent_jobs: JobRow[];
  leads_total: number;
  leads_by_stage: Record<string, number>;
  cache_entries: Record<string, number>;
  usage_totals: { provider: string; task: string; calls: number; units: number }[];
  system: {
    db_path: string;
    supabase_configured: boolean;
    python: string;
    config_dir: string;
  };
};

// Normalize provider status (uppercase) → UI shape
function normalizeProvider(p: any): ProviderRow {
  const env = p.key_env || p.env_key;
  const keyState: ProviderRow["key_state"] = env == null
    ? "local"
    : p.has_key
    ? "set"
    : "missing";
  return {
    ...p,
    status: (p.status || "unknown").toLowerCase(),
    key_state: keyState,
    env_key: env,
  };
}

export const apiGet = {
  authSession: () => api.get<{ authenticated: boolean; mode?: "supabase" | "password" | "open"; org_id?: string | null }>("/api/auth/session"),
  agents: () => api.get<{ agents: any[] }>("/api/agents"),
  agentRuns: () => api.get<{ runs: any[] }>("/api/agent-runs"),
  tools: () => api.get<{ tools: any[] }>("/api/tools"),
  approvals: () => api.get<{ approvals: any[] }>("/api/approvals"),
  status: async (): Promise<StatusResponse> => {
    const r = await api.get<any>("/api/status");
    return {
      ...r,
      providers: (r.providers || []).map(normalizeProvider),
    };
  },
  providers: async (): Promise<{ providers: ProviderRow[] }> => {
    const r = await api.get<any>("/providers");
    const arr = r.status || [];
    return { providers: arr.map(normalizeProvider) };
  },
  jobs: async (): Promise<JobRow[]> => {
    return api.get<JobRow[]>("/api/jobs");
  },
  job: (id: string) => api.get<{ job: JobRow; events: any[] }>(`/api/jobs/${encodeURIComponent(id)}`),
  leads: (params: { job_id?: string; stage?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.job_id) q.set("job_id", params.job_id);
    if (params.stage) q.set("stage", params.stage);
    if (params.limit) q.set("limit", String(params.limit));
    return api.get<LeadRow[]>(`/api/leads?${q.toString()}`);
  },
  config: async (): Promise<{ files: Record<string, { path: string; text: string; parsed: any }> }> => {
    const r = await api.get<Record<string, { path: string; text: string; parsed: any }>>("/api/config");
    return { files: r };
  },
  report: (id: string) => api.get<{ job_id: string; metrics: any; report_markdown: string }>(`/report/${encodeURIComponent(id)}`),
  health: () => api.get<any>("/health"),
  openapi: () => api.get<any>("/openapi.json"),
  analytics: () => api.get<{
    leads_over_time: { date: string; count: number }[];
    jobs_over_time: { date: string; total: number; completed: number; paused: number; failed: number }[];
    usage_over_time: { date: string; units: number; calls: number }[];
  }>("/api/analytics"),
  keysUsage: () => api.get<KeyUsageResponse>("/api/keys/usage"),
  integrations: () => api.get<{ integrations: IntegrationRow[] }>("/api/v1/integrations"),
  suppression: (channel?: string) =>
    api.get<{ entries: SuppressionEntry[] }>(
      `/api/v1/suppression${channel ? `?channel=${encodeURIComponent(channel)}` : ""}`
    ),
  entitlements: () => api.get<Entitlements>("/api/v1/entitlements"),
  keys: () => api.get<{
    env_path: string;
    groups: Record<string, string>;
    keys: { name: string; group: string; configured: boolean; masked: string; plain?: boolean }[];
  }>("/api/keys"),
  activity: (limit = 50, kind?: string) => {
    const q = new URLSearchParams();
    q.set("limit", String(limit));
    if (kind) q.set("kind", kind);
    return api.get<{events: ActivityEvent[]}>(`/api/activity?${q.toString()}`);
  },
  reviewPending: (jobId?: string) =>
    api.get<{ leads: Presentation[] }>(
      `/api/v1/review/pending${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`
    ),
  leadPresentation: (leadId: string) =>
    api.get<Presentation>(`/api/v1/leads/${encodeURIComponent(leadId)}/presentation`),
  researchProgress: (jobId: string) =>
    api.get<ResearchProgress>(`/api/v1/research/${encodeURIComponent(jobId)}`),
  researchEvents: (jobId: string) =>
    api.get<{ events: { ts: string; from_state: string; to_state: string; reason: string | null }[] }>(
      `/api/v1/research/${encodeURIComponent(jobId)}/events`
    ),
};

export const apiPost = {
  login: (password: string) => api.post<{ authenticated: boolean }>("/api/auth/login", { password }),
  logout: () => api.post<{ authenticated: boolean }>("/api/auth/logout"),
  runBenchmark: (body: { icp?: string; seed_csv?: string; overrides?: { v0_limits?: Record<string, number> } }) =>
    api.post<{ job_id: string; state: string; pause_reason?: string; metrics?: any }>(
      "/benchmark/run",
      body
    ),
  resumeJob: (id: string) =>
    api.post<{ ok: boolean; state: string; metrics?: any }>(`/jobs/${encodeURIComponent(id)}/resume`, {}),
  syncSupabase: (id: string, stage = "ACCEPTED") =>
    api.post<any>(`/sync-supabase`, { job_id: id, stage }),
  verifyEmail: (email: string) =>
    api.post<any>(`/verify-email`, { email }),
  chat: (
    messages: { role: string; content: string }[],
    options: { provider?: string | null; tools?: string[] | null; agent?: string | null } = {}
  ) =>
    api.post<any>(`/api/chat`, {
      messages,
      provider: options.provider || null,
      tools: options.tools ?? null,
      agent: options.agent || null,
    }),
  saveKeys: (keys: Record<string, string>) => api.post<{ ok: boolean; saved: string[] }>(`/api/keys`, keys),
  saveConfig: (key: string, text: string) =>
    api.put<{ ok: boolean; backup: string }>(`/api/config/${key}`, { text }),
  saveConfigValues: (key: string, values: Record<string, any>) =>
    api.put<{ ok: boolean; backup: string }>(`/api/config/${key}`, { values }),
  providerSetStatus: (name: string, task: string, status: "active" | "disabled") =>
    api.post<{ ok: boolean }>(`/api/providers/${encodeURIComponent(name)}/${encodeURIComponent(task)}/status`, { status }),
  providerReset: (name: string, task: string) =>
    api.post<{ ok: boolean }>(`/api/providers/${encodeURIComponent(name)}/${encodeURIComponent(task)}/reset`),
  providerConfig: (name: string, task: string, config: { base_url?: string; model_name?: string }) =>
    api.put<{ ok: boolean }>(`/api/providers/${encodeURIComponent(name)}/${encodeURIComponent(task)}/config`, config),
  wipeData: () => api.post<{ ok: boolean }>(`/api/data/reset`),
  deleteLead: (id: string) =>
    api.delete<{ ok: boolean }>(`/api/v1/leads/${encodeURIComponent(id)}`),
  purgeCache: () => api.post<{ ok: boolean }>(`/api/cache/purge`),
  resolveApproval: (id: string, status: "APPROVED" | "REJECTED") =>
    api.post<{ ok: boolean }>(`/api/approvals/${encodeURIComponent(id)}/resolve`, { status }),
  createAgent: (body: { slug: string; name: string; description?: string; status?: string }) =>
    api.post<{ agent: any }>(`/api/agents`, body),
  updateAgent: (slug: string, body: { name?: string; description?: string; status?: string }) =>
    api.patch<{ agent: any }>(`/api/agents/${encodeURIComponent(slug)}`, body),
  createAgentVersion: (slug: string, body: {
    version: string;
    instructions?: string;
    model_provider?: string;
    model_name?: string;
    thinking_effort?: string;
    tool_policy?: { scopes?: string[] };
    activate?: boolean;
  }) =>
    api.post<{ version: any; activated: any }>(`/api/agents/${encodeURIComponent(slug)}/versions`, body),
  recordActivity: (body: {kind: string, payload: any, correlation_id?: string}) =>
    api.post<{event: ActivityEvent}>("/api/activity", body),
  integrationConnect: (provider: string) =>
    api.post<{ authorize_url: string }>(`/api/v1/integrations/${encodeURIComponent(provider)}/connect`, {}),
  integrationRevoke: (provider: string) =>
    api.post<{ ok: boolean }>(`/api/v1/integrations/${encodeURIComponent(provider)}/revoke`, {}),
  suppressionAdd: (channel: string, value: string, reason: string) =>
    api.post<{ id?: string }>("/api/v1/suppression", { channel, value, reason }),
  suppressionRemove: (id: string) =>
    api.delete<{ ok: boolean }>(`/api/v1/suppression/${encodeURIComponent(id)}`),
  // Stage 3 — human decisions (APPROVE_CONTACT is the terminal state; nothing sends)
  leadDecision: (leadId: string, action: "APPROVE_CONTACT" | "REJECT" | "RESEARCH_MORE" | "SAVE_FOR_LATER", note?: string) =>
    api.post<{ ok: boolean; child_job_id?: string; note?: string }>(
      `/api/v1/leads/${encodeURIComponent(leadId)}/decision`, { action, note: note || null }
    ),
  leadRequalify: (leadId: string, icpVersionId?: string) =>
    api.post<{ ok: boolean; presentation: Presentation }>(
      `/api/v1/leads/${encodeURIComponent(leadId)}/requalify`,
      { icp_version_id: icpVersionId || null }
    ),
  startResearch: (objective: string, icpVersionId?: string, budgets?: Record<string, number>) =>
    api.post<{ job_id: string; state: string; mode: string }>(
      "/api/v1/research", { objective, icp_version_id: icpVersionId || null, budgets: budgets || null }
    ),
  researchCancel: (jobId: string) =>
    api.post<{ ok: boolean }>(`/api/v1/research/${encodeURIComponent(jobId)}/cancel`, {}),
};
