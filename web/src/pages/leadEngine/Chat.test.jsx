// Regression: Chat's RunPanel crashed the whole page (blank screen, sidebar gone)
// for every real job. mapJob deliberately sets budget.limit = null ("unknown, never
// a fabricated 500") and RunPanel called job.budget.limit.toLocaleString().
// 0 of 38 production jobs carry a quota limit, so this was the normal case.
import React from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

// The suite runs in the plain `node` environment (no jsdom dependency). A few
// modules read `window` at import time, so provide the minimum before importing.
vi.hoisted(() => {
  if (typeof globalThis.window === "undefined") {
    const w = { location: { href: "http://localhost/", origin: "http://localhost", pathname: "/", search: "" },
      matchMedia: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }),
      addEventListener() {}, removeEventListener() {}, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
    w.self = w; w.top = w;
    globalThis.window = w;
  }
});

const { RunPanel } = await import("./Chat");
const { mapJob } = await import("@/lib/leadEngine/api");

const realShapedJob = (params = "{}") => mapJob({
  job_id: "job-1", icp_id: "agentic", state: "COMPLETED",
  created_at: "2026-10-14T00:00:00Z", updated_at: "2026-10-14T01:00:00Z", params,
});

const render = (job) => renderToString(
  <MemoryRouter><RunPanel job={job} ar live={false} /></MemoryRouter>,
);

describe("RunPanel budget", () => {
  test("a job with an unknown budget limit renders instead of crashing", () => {
    const job = realShapedJob();
    expect(job.budget.limit).toBeNull();            // the real-world shape
    expect(() => render(job)).not.toThrow();
  });

  test("an unknown limit shows only the used amount, no fake ceiling or NaN", () => {
    const html = render(realShapedJob());
    expect(html).not.toMatch(/NaN|Infinity|undefined|null/);
    expect(html).not.toMatch(/\/\s*500/);            // never a fabricated ceiling
  });

  test("a known limit still shows used / limit and the progress bar", () => {
    const job = realShapedJob(JSON.stringify({ metrics: { quota_units_total: 30, quota_limit: 120 } }));
    const html = render(job);
    expect(html).toContain("30 / 120");
  });
});
