// API client for the Lead Engine backend.
// All requests go through Vite proxy in dev and the configured backend in prod.

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
  const res = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
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
  authSession: () => api.get<{ authenticated: boolean }>("/api/auth/session"),
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
    return api.get<JobRow[]>("/jobs");
  },
  job: (id: string) => api.get<{ job: JobRow; events: any[] }>(`/jobs/${encodeURIComponent(id)}`),
  leads: (params: { job_id?: string; stage?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.job_id) q.set("job_id", params.job_id);
    if (params.stage) q.set("stage", params.stage);
    return api.get<LeadRow[]>(`/leads?${q.toString()}`);
  },
  config: async (): Promise<{ files: { path: string; content: string }[] }> => {
    const r = await api.get<Record<string, { path: string; text: string }>>("/api/config");
    return {
      files: Object.entries(r).map(([key, val]) => ({
        path: val.path,
        content: val.text,
      })),
    };
  },
  report: (id: string) => api.get<{ job_id: string; metrics: any; report_markdown: string }>(`/report/${encodeURIComponent(id)}`),
  health: () => api.get<any>("/health"),
  openapi: () => api.get<any>("/openapi.json"),
  analytics: () => api.get<{
    leads_over_time: { date: string; count: number }[];
    jobs_over_time: { date: string; total: number; completed: number; paused: number; failed: number }[];
    usage_over_time: { date: string; units: number; calls: number }[];
  }>("/api/analytics"),
};

export const apiPost = {
  login: (password: string) => api.post<{ authenticated: boolean }>("/api/auth/login", { password }),
  logout: () => api.post<{ authenticated: boolean }>("/api/auth/logout"),
  runBenchmark: (body: { icp?: string; seed_csv?: string }) =>
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
  chat: (messages: { role: string; content: string }[]) =>
    api.post<any>(`/api/chat`, { messages }),
  saveKeys: (keys: Record<string, string>) => api.post<{ ok: boolean; saved: string[] }>(`/api/keys`, keys),
  saveConfig: (key: string, text: string) =>
    api.put<{ ok: boolean; backup: string }>(`/api/config/${key}`, { text }),
  providerSetStatus: (name: string, task: string, status: "active" | "disabled") =>
    api.post<{ ok: boolean }>(`/api/providers/${encodeURIComponent(name)}/${encodeURIComponent(task)}/status`, { status }),
  providerReset: (name: string, task: string) =>
    api.post<{ ok: boolean }>(`/api/providers/${encodeURIComponent(name)}/${encodeURIComponent(task)}/reset`),
  providerConfig: (name: string, task: string, config: { base_url?: string; model_name?: string }) =>
    api.put<{ ok: boolean }>(`/api/providers/${encodeURIComponent(name)}/${encodeURIComponent(task)}/config`, config),
  wipeData: () => api.post<{ ok: boolean }>(`/api/data/reset`),
  purgeCache: () => api.post<{ ok: boolean }>(`/api/cache/purge`),
};
