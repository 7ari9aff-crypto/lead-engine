// Real backend client for the Lead Engine dashboard.
// All requests go through the Vite proxy in dev and the same-origin backend
// in production. Auth: Supabase Bearer token when a session exists; the
// legacy signed-cookie (password mode) fallback works through credentials.

const BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request(path, init = {}) {
  const { getAccessToken } = await import("@/lib/supabase");
  const url = `${BASE}${path}`;
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = await getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url, { ...init, credentials: "include", headers });
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const msg = (body && (body.error || body.detail || body.message)) || `HTTP ${res.status}`;
    throw new ApiError(typeof msg === "string" ? msg : JSON.stringify(msg), res.status, body);
  }
  return body;
}

export const api = {
  get: (p) => request(p, { method: "GET" }),
  post: (p, body) => request(p, { method: "POST", body: body != null ? JSON.stringify(body) : undefined }),
  put: (p, body) => request(p, { method: "PUT", body: body != null ? JSON.stringify(body) : undefined }),
  delete: (p) => request(p, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Backend shape → dashboard shape mappers. The backend speaks its own dialect
// (engine.jobs / engine.leads rows); the pages speak the review-workflow
// dialect (company/contact/facts). These are the ONLY translation points.
// ---------------------------------------------------------------------------

const JOB_STATUS_MAP = {
  QUEUED: "QUEUED", RUNNING: "RUNNING", DISCOVERING: "DISCOVERING",
  RESEARCHING: "RESEARCHING", VERIFYING: "VERIFYING", QUALIFYING: "QUALIFYING",
  READY_FOR_REVIEW: "READY_FOR_REVIEW", COMPLETED: "COMPLETED",
  PAUSED: "PAUSED", WAITING_FOR_USER: "WAITING_FOR_USER",
  CANCELLED: "CANCELLED", FAILED: "FAILED", DEGRADED: "RUNNING",
  RESUMING: "QUEUED", PLANNING: "DISCOVERING", ENRICHING: "DISCOVERING",
  SCORING: "VERIFYING", CANCELLING: "CANCELLED",
};

const STAGE_TO_STATUS = {
  ACCEPTED: "APPROVED", REVIEW: "READY_FOR_REVIEW", REJECTED: "REJECTED",
};

const EMAIL_STATUS_TO_VERIFICATION = {
  DELIVERABLE: "VERIFIED", RISKY: "PARTIALLY_VERIFIED",
  CATCH_ALL: "PARTIALLY_VERIFIED", UNKNOWN: "UNVERIFIED", INVALID: "UNVERIFIED",
};

export function mapJob(row, index = 0) {
  const metrics = row.metrics || {};
  const stages = {
    discovered: metrics.discovery_raw_candidates ?? metrics.discovered ?? 0,
    deduplicated: metrics.unique_after_dedup ?? metrics.deduplicated ?? 0,
    researched: metrics.researched ?? 0,
    verified: metrics.verified ?? 0,
    qualified: metrics.final_leads ?? metrics.qualified ?? 0,
    readyForReview: metrics.review_leads ?? metrics.readyForReview ?? 0,
  };
  const stopMap = {
    COMPLETED: "COMPLETED", PAUSED: "WAITING_FOR_USER", FAILED: "SYSTEM_FAILURE",
    CANCELLED: "CANCELLED", READY_FOR_REVIEW: "COMPLETED",
    WAITING_FOR_USER: "WAITING_FOR_USER", PARTIAL_SUCCESS: "COMPLETED",
  };
  return {
    id: row.job_id,
    objective: row.params?.objective || row.icp_id || row.job_id,
    icpVersion: row.icp_id || null,
    status: JOB_STATUS_MAP[row.state] || row.state,
    createdAt: row.created_at,
    startedAt: row.started_at || row.created_at,
    completedAt: row.updated_at && ["COMPLETED", "FAILED", "CANCELLED", "READY_FOR_REVIEW"].includes(row.state)
      ? row.updated_at : null,
    stages,
    targets: null,
    budget: {
      used: Math.round(metrics.quota_units_total ?? 0),
      limit: Math.round(metrics.quota_units_total ?? 0) + 500,
      unit: "نداء",
    },
    stopReason: row.pause_reason ? "PROVIDER_UNAVAILABLE" : (stopMap[row.state] || null),
    pauseReason: row.pause_reason || null,
    timeline: [],
    providerActivity: [],
    leadIds: [],
    waitingQuestion: row.state === "WAITING_FOR_USER"
      ? { prompt: "النظام بحاجة لإجابتك لاستكمال البحث", options: [], kind: "free" }
      : null,
    _index: index,
  };
}

export function mapLead(row) {
  const status = STAGE_TO_STATUS[row.stage] || "READY_FOR_REVIEW";
  const score = row.qualification_score ?? row.score ?? 0;
  return {
    id: row.lead_id,
    company: {
      name: row.name || row.domain || row.lead_id,
      domain: row.domain,
      location: row.city,
      industry: row.industry,
      size: row.employee_count ?? null,
      sizeRange: null,
      website: row.website || (row.domain ? `https://${row.domain}` : null),
      founded: null,
      businessModel: null,
      hasSalesTeam: null,
      description: null,
    },
    contact: {
      name: row.decision_maker || "—",
      title: row.decision_maker_title || "—",
      email: row.email || "—",
      phone: row.phone || "—",
      linkedin: row.linkedin || "—",
      piiAccessed: false,
      revealReason: null,
      revealAt: null,
    },
    icpFit: { score, criteria: [] },
    status,
    verificationStatus: EMAIL_STATUS_TO_VERIFICATION[row.email_status] || "UNVERIFIED",
    evidenceCoverage: row.email_status ? 60 : 0,
    confidence: score >= 80 ? "عالية" : score >= 60 ? "متوسطة" : "منخفضة",
    lastUpdated: row.updated_at,
    jobId: row.job_id,
    icpVersion: null,
    facts: [],
    conflicts: [],
    evidence: [],
    timeline: [],
    reviewDecision: row.disposition || null,
    reviewNote: row.disposition_note || null,
    reviewAt: row.disposition_at || null,
  };
}

export function mapProvider(p) {
  const statusMap = {
    active: "OPERATIONAL", degraded: "DEGRADED", disabled: "DISCONNECTED",
    exhausted: "EXHAUSTED", cooldown: "DEGRADED", unknown: "UNKNOWN",
  };
  return {
    id: `${p.name}:${p.task}`,
    name: p.name,
    task: p.task,
    status: statusMap[p.status] || p.status,
    health: p.status_reason || p.status || "",
    lastFailure: p.status_reason || null,
    quota: {
      used: p.quota_used ?? 0,
      limit: p.quota_limit ?? null,
      kind: p.quota_kind || null,
    },
    lastUsed: p.last_used || null,
    hasKey: p.key_state === "set" || p.key_state === "local",
  };
}

export function mapActivityEvent(e) {
  const payload = e.payload || {};
  return {
    id: String(e.id),
    actor: payload.actor || payload.decided_by || "SYSTEM",
    action: e.kind,
    target: payload.entity_id || payload.job_id || payload.lead_id || "",
    at: e.ts,
    detail: payload.detail || payload.note || payload.error || "",
  };
}

export function mapCredential(k) {
  return {
    id: k.name,
    service: k.name,
    masked: k.masked || null,
    connected: k.configured,
    status: k.configured ? "OK" : "MISSING",
    lastTested: null,
    note: k.group || "",
  };
}

export function mapIcp(v) {
  return {
    id: v.icp_version_id,
    version: v.version,
    label: `ICP ${v.slug} v${v.version}`,
    isCurrent: v.status === "active",
    createdBy: v.created_by || "—",
    createdAt: v.created_at,
    changes: v.source || "",
    criteria: v.definition || {},
  };
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const apiGet = {
  session: () => api.get("/api/auth/session"),
  status: () => api.get("/api/status"),
  jobs: () => api.get("/api/jobs"),
  job: (id) => api.get(`/api/jobs/${encodeURIComponent(id)}`),
  leads: (params = {}) => {
    const q = new URLSearchParams();
    if (params.job_id) q.set("job_id", params.job_id);
    if (params.stage) q.set("stage", params.stage);
    q.set("limit", String(params.limit ?? 500));
    return api.get(`/api/leads?${q.toString()}`);
  },
  reviewPending: (jobId) =>
    api.get(`/api/v1/review/pending${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`),
  analytics: () => api.get("/api/analytics"),
  activity: (limit = 50) => api.get(`/api/activity?limit=${limit}`),
  agents: () => api.get("/api/agents"),
  agentRuns: () => api.get("/api/agent-runs"),
  keys: () => api.get("/api/keys"),
  keysUsage: () => api.get("/api/keys/usage"),
  icps: (slug = "agentic") =>
    api.get(`/api/v1/icps?slug=${encodeURIComponent(slug)}`),
  integrations: () => api.get("/api/v1/integrations").catch(() => ({ integrations: [] })),
  researchProgress: (jobId) =>
    api.get(`/api/v1/research/${encodeURIComponent(jobId)}`),
  researchEvents: (jobId) =>
    api.get(`/api/v1/research/${encodeURIComponent(jobId)}/events`),
};

export const apiPost = {
  login: (password) => api.post("/api/auth/login", { password }),
  logout: () => api.post("/api/auth/logout"),
  leadDecision: (leadId, action, note) =>
    api.post(`/api/v1/leads/${encodeURIComponent(leadId)}/decision`, { action, note: note || null }),
  leadRequalify: (leadId) =>
    api.post(`/api/v1/leads/${encodeURIComponent(leadId)}/requalify`, {}),
  researchStart: (objective) =>
    api.post("/api/v1/research", { objective, icp_version_id: null }),
  researchAnswer: (jobId, answer) =>
    api.post(`/api/v1/research/${encodeURIComponent(jobId)}/answer`, { answer }),
  researchCancel: (jobId) =>
    api.post(`/api/v1/research/${encodeURIComponent(jobId)}/cancel`, {}),
  resumeJob: (jobId) => api.post(`/jobs/${encodeURIComponent(jobId)}/resume`, {}),
  keysSave: (keys) => api.post("/api/keys", keys),
  chat: (messages) => api.post("/api/chat", { messages, provider: null, tools: null, agent: null }),
  runBenchmark: (icp = "v0") => api.post("/benchmark/run", { icp }),
};
