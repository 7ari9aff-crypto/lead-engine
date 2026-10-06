import { describe, it, expect } from "vitest";
import { mapJob, mapLead, mapProvider } from "./api";

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

  it("maps provider status and quota", () => {
    const p = mapProvider({ name: "tavily", task: "web_search", status: "cooldown", quota_used: 32, quota_limit: 1000 });
    expect(p.status).toBe("DEGRADED");
    expect(p.quota.used).toBe(32);
    expect(p.hasKey).toBe(false);
  });
});
