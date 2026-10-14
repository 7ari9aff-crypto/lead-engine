import { describe, it, expect } from "vitest";
import { mapJob, mapLead, mapProvider, mapAgent, mapTool, agentRunStats } from "./api";

// Every payload below is a verbatim shape captured from the live backend
// (GET /api/status, /api/jobs, /api/agents, /api/tools on the local server
// pointed at the production Postgres). These tests exist because the v12
// dashboard shipped pages reading fields the endpoints never send.

describe("backend → dashboard mappers", () => {
  it("maps a legacy job row to the UI shape", () => {
    const j = mapJob({
      job_id: "job-abc", icp_id: "v0", state: "READY_FOR_REVIEW",
      created_at: "2026-10-04T00:00:00Z", updated_at: "2026-10-04T01:00:00Z",
      metrics: { discovery_raw_candidates: 42, review_leads: 3 },
    });
    expect(j.id).toBe("job-abc");
    expect(j.status).toBe("READY_FOR_REVIEW");
    expect(j.stages.discovered).toBe(42);
    expect(j.stages.readyForReview).toBe(3);
    expect(j.completedAt).toBeTruthy();
  });

  it("maps lead stage to review statuses", () => {
    expect(mapLead({ lead_id: "l1", name: "X", stage: "ACCEPTED", score: 91 }).status).toBe("APPROVED");
    expect(mapLead({ lead_id: "l2", name: "Y", stage: "REVIEW", score: 55 }).status).toBe("READY_FOR_REVIEW");
    expect(mapLead({ lead_id: "l3", name: "Z", stage: "REJECTED", score: 20 }).status).toBe("REJECTED");
  });
});

describe("mapProvider — real /api/status row", () => {
  // Captured verbatim from GET /api/status providers[0].
  const realRow = {
    name: "openmanus", task: "deep_research", type: "runtime", priority: 1,
    status: "active", status_reason: null, cooldown_until: null,
    key_env: "OPENMANUS_BASE_URL", has_key: true, is_local: false,
    quota_kind: "requests", quota_limit: null, quota_used: 0, period: "none",
    rpm_limit: null, base_url: null, model_name: null, calls: 0, units: 0,
    last_used: null,
  };

  it("reads has_key (not key_state) and keeps quota fields numeric", () => {
    const p = mapProvider(realRow);
    expect(p.hasKey).toBe(true);            // was always false before
    expect(p.id).toBe("openmanus:deep_research");
    expect(p.status).toBe("OPERATIONAL");
    expect(p.quota.used).toBe(0);
    expect(p.quota.limit).toBeNull();
    expect(p.remaining).toBeNull();
    expect(p.priority).toBe(1);
  });

  it("computes remaining quota for a limited provider", () => {
    const p = mapProvider({ ...realRow, name: "tavily", task: "web_search", quota_kind: "credits", quota_limit: 1000, quota_used: 320, calls: 41, units: 35, status: "cooldown" });
    expect(p.remaining).toBe(680);
    expect(p.status).toBe("DEGRADED");
    expect(p.calls).toBe(41);
  });
});

describe("mapAgent / agentRunStats — real /api/agents + /api/agent-runs rows", () => {
  const realAgent = {
    agent_id: "agent:engine-maintainer", slug: "engine-maintainer",
    name: "Engine Maintainer Agent",
    description: "وكيل صيانة المحرك: يتتبّع المشكلة في الكود بنفسه…",
    status: "active", current_version: "1.0.0",
    created_at: "2026-09-25T08:49:22Z", updated_at: "2026-09-25T08:49:22Z",
    organization_id: "fc4505fe-382e-4df9-bc2a-f97ae17590db",
  };

  it("maps the agent row to the fields the page renders", () => {
    const a = mapAgent(realAgent);
    expect(a.id).toBe("agent:engine-maintainer");
    expect(a.version).toBe("1.0.0");       // current_version, not `version`
    expect(a.status).toBe("active");
    expect(a.note).toContain("وكيل صيانة المحرك");
    expect(a.recentRuns).toBe(0);          // enriched by the store, not invented
  });

  it("aggregates runs per agent without touching failures of others", () => {
    const stats = agentRunStats([
      { agent_id: "agent:engine-maintainer", status: "COMPLETED", created_at: "2026-09-26T10:00:00Z" },
      { agent_id: "agent:engine-maintainer", status: "FAILED", created_at: "2026-09-27T10:00:00Z" },
      { agent_id: "agent:lead-research", status: "COMPLETED", created_at: "2026-09-27T11:00:00Z" },
      { agent_id: null, status: "FAILED" }, // ignored
    ]);
    expect(stats["agent:engine-maintainer"]).toEqual({ recentRuns: 2, failures: 1, lastRunAt: "2026-09-27T10:00:00Z" });
    expect(stats["agent:lead-research"].recentRuns).toBe(1);
    expect(Object.keys(stats)).toHaveLength(2);
  });
});

describe("mapTool — real /api/tools row", () => {
  it("parses the scopes JSON text and gating flags", () => {
    const tool = mapTool({
      name: "ask_user", description: "Ask the user a blocking question (job goes WAITING_FOR_USER)",
      input_schema: null, output_schema: null,
      scopes: '["interaction:write"]', requires_approval: 1, enabled: 1,
      created_at: "2026-09-25T08:49:22Z",
    });
    expect(tool.scopes).toEqual(["interaction:write"]);
    expect(tool.requiresApproval).toBe(true);
    expect(tool.enabled).toBe(true);
  });

  it("tolerates broken scopes text and disabled tools", () => {
    const tool = mapTool({ name: "x", description: "", scopes: "not-json", requires_approval: 0, enabled: 0 });
    expect(tool.scopes).toEqual([]);
    expect(tool.enabled).toBe(false);
  });
});

describe("mapJob — real /api/jobs row", () => {
  // Captured verbatim from GET /api/jobs (the SELECT that previously omitted
  // params, so the dashboard showed the icp_id as the objective and zeros).
  const realRow = {
    job_id: "job-f6824339d9", icp_id: "v0", state: "COMPLETED",
    pause_reason: null, resume_at: null,
    params: '{"metrics": {"discovery_raw_candidates": 64, "unique_after_dedup": 40, "qualification_scored": 36, "review_leads": 24, "final_leads": 12, "quota_units_total": 1.0}, "outputs": {}}',
    created_at: "2026-09-16T12:59:41Z", updated_at: "2026-09-16T12:59:41Z",
  };

  it("reads the objective and stage counters from params.metrics (JSON text)", () => {
    const j = mapJob(realRow);
    expect(j.id).toBe("job-f6824339d9");
    expect(j.status).toBe("COMPLETED");
    expect(j.stages.discovered).toBe(64);
    expect(j.stages.deduplicated).toBe(40);
    expect(j.stages.qualified).toBe(36);
    expect(j.stages.readyForReview).toBe(24);
    expect(j.budget.used).toBe(1);
  });

  it("prefers a real objective and never fabricates a budget limit", () => {
    const withObjective = mapJob({
      ...realRow,
      params: '{"objective": "عيادات أسنان في الرياض", "metrics": {}}',
    });
    expect(withObjective.objective).toBe("عيادات أسنان في الرياض");
    // no organization limit is known from a job row — null, not used+500
    expect(withObjective.budget.limit).toBeNull();
  });

  it("falls back to the icp id for benchmark runs without an objective", () => {
    const j = mapJob({ job_id: "job-x", icp_id: "v0", state: "PAUSED", pause_reason: "NO_AVAILABLE_PROVIDER:web_search" });
    expect(j.objective).toBe("v0");
    expect(j.status).toBe("PAUSED");
    expect(j.stopReason).toBe("PROVIDER_UNAVAILABLE");
  });
});
