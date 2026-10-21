// Real backend client for the Lead Engine dashboard.
// All requests go through the Vite proxy in dev and the same-origin backend
// in production. Auth: Supabase Bearer token when a session exists; the
// legacy signed-cookie (password mode) fallback works through credentials.

import { displayCompanyName } from "./format";

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
//
// Every shape below is pinned against a REAL captured payload in
// api.test.js — the v12 rewrite shipped pages reading fields the endpoints
// never send (Providers: [object Object] + NaN% bars; Agents: empty stats).
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

// DB columns hold JSON as TEXT; the API may return it either way.
const asJson = (v) => {
  if (v == null || v === "") return null;
  if (typeof v === "object") return v;
  try { return JSON.parse(v); } catch { return null; }
};

// Real pipeline metrics live under jobs.params.metrics (benchmark runs) — the
// per-job detail endpoint is the only other place they appear.
const jobMetrics = (row) => asJson(row?.params)?.metrics || row?.metrics || asJson(row?.result)?.metrics || {};
const jobStages = (row) => asJson(row?.result)?.stages || {};

export function mapJob(row, index = 0) {
  const m = jobMetrics(row);
  const st = jobStages(row);
  const params = asJson(row?.params) || {};
  const stages = {
    discovered: m.discovery_raw_candidates ?? st.discovery?.raw_candidates ?? 0,
    deduplicated: m.unique_after_dedup ?? st.dedup?.output_count ?? 0,
    researched: m.researched ?? st.research?.researched ?? 0,
    verified: st.verification?.verified ?? m.verified ?? 0,
    qualified: m.qualification_scored ?? st.qualification?.scored ?? 0,
    readyForReview: m.review_leads ?? st.legal_gate?.review ?? 0,
    final: m.final_leads ?? st.legal_gate?.accepted ?? 0,
  };
  const stopMap = {
    COMPLETED: "COMPLETED", PAUSED: "WAITING_FOR_USER", FAILED: "SYSTEM_FAILURE",
    CANCELLED: "CANCELLED", READY_FOR_REVIEW: "COMPLETED",
    WAITING_FOR_USER: "WAITING_FOR_USER", PARTIAL_SUCCESS: "COMPLETED",
  };
  // A job's objective is what the operator asked for; benchmark runs have no
  // free-text objective, so the icp id is the honest label for them.
  const objective = params.objective || row.icp_id || row.job_id;
  return {
    id: row.job_id,
    objective,
    icpVersion: row.icp_id || null,
    status: JOB_STATUS_MAP[row.state] || row.state,
    createdAt: row.created_at,
    startedAt: row.started_at || row.created_at,
    completedAt: row.updated_at && ["COMPLETED", "FAILED", "CANCELLED", "READY_FOR_REVIEW"].includes(row.state)
      ? row.updated_at : null,
    stages,
    targets: null,
    budget: {
      used: Math.round(m.quota_units_total ?? 0),
      // The daily provider-call ceiling lives on the organization, not the
      // job row — null means "unknown here", never a fabricated 500.
      limit: m.quota_limit ?? null,
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
      // Shown everywhere (lists, review queue, search). The extractor stores a page
      // <title> as the name, so a page title is swapped for the domain here, once;
      // rawName keeps what is actually stored.
      name: displayCompanyName({ name: row.name, domain: row.domain }) || row.lead_id,
      rawName: row.name || null,
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
    exhausted: "EXHAUSTED", cooldown: "DEGRADED", unavailable: "UNKNOWN",
    unknown: "UNKNOWN",
  };
  // Real row (app.py _build_status): name, task, type, priority, status,
  // status_reason, cooldown_until, key_env, has_key, is_local, quota_kind,
  // quota_limit, quota_used, period, rpm_limit, base_url, model_name,
  // calls, units, last_used. `has_key` — not `key_state`.
  const limit = p.quota_limit ?? null;
  const used = p.quota_used ?? 0;
  let status = statusMap[p.status] || p.status;
  let health = p.status_reason || p.status || "";
  // The server's "active" means "not switched off", not "usable". A provider that
  // needs a key (key_env set, not local) and has none cannot serve a request, yet
  // the dashboard painted it green: 19 of 21 live rows on 2026-10-21. Only a row
  // the server calls active is relabelled; disabled/cooldown/exhausted already say
  // something more specific and keep their own state.
  const needsKey = !!p.key_env && !p.is_local;
  if (status === "OPERATIONAL" && needsKey && p.has_key === false) {
    status = "UNCONFIGURED";
    health = `${p.key_env} غير مضبوط`;
  }
  return {
    id: `${p.name}:${p.task}`,
    name: p.name,
    task: p.task,
    type: p.type || null,
    priority: p.priority ?? null,
    status,
    health,
    lastFailure: p.status_reason || null,
    quota: { used, limit, kind: p.quota_kind || null },
    remaining: limit != null ? Math.max(0, limit - used) : null,
    calls: p.calls ?? 0,
    units: p.units ?? 0,
    period: p.period || null,
    rpmLimit: p.rpm_limit ?? null,
    lastUsed: p.last_used || null,
    hasKey: p.has_key ?? (p.key_state === "set" || p.key_state === "local"),
    isLocal: !!p.is_local,
    keyEnv: p.key_env || null,
    baseUrl: p.base_url || null,
    modelName: p.model_name || null,
  };
}

// engine.agents row: agent_id, slug, name, description, status,
// current_version, created_at, updated_at. Run counters and tool lists are
// NOT on the row — the store enriches via agentRunStats()/the tools registry.
export function mapAgent(a) {
  return {
    id: a.agent_id || a.slug,
    slug: a.slug,
    name: a.name,
    version: a.current_version || null,
    status: a.status,
    note: a.description || null,
    recentRuns: 0,
    failures: 0,
    lastRunAt: null,
    tools: [],
  };
}

// Aggregates engine.agent_runs rows per agent_id (pure — tested).
export function agentRunStats(runs) {
  const out = {};
  for (const r of runs || []) {
    const id = r.agent_id;
    if (!id) continue;
    const s = out[id] || (out[id] = { recentRuns: 0, failures: 0, lastRunAt: null });
    s.recentRuns += 1;
    if (r.status === "FAILED") s.failures += 1;
    const at = r.created_at || r.updated_at;
    if (at && (!s.lastRunAt || at > s.lastRunAt)) s.lastRunAt = at;
  }
  return out;
}

// engine.tools row: name, description, input_schema, output_schema,
// scopes (JSON text), requires_approval, enabled, created_at.
export function mapTool(t) {
  let scopes = [];
  try { scopes = JSON.parse(t.scopes || "[]"); } catch { scopes = []; }
  return {
    name: t.name,
    description: t.description || "",
    scopes: Array.isArray(scopes) ? scopes : [],
    requiresApproval: !!t.requires_approval,
    enabled: t.enabled !== 0 && t.enabled !== false,
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
  tools: () => api.get("/api/tools"),
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
