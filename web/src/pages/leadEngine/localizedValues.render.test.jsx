import { describe, it, expect, vi } from "vitest";
import React from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

// The store is the only thing these pages need: feed it production-shaped data
// (what engine.leads actually holds: city "Riyadh"/"Jeddah", industry "dental").
const lead = (id, location) => ({
  id,
  status: "NEW",
  company: { name: `Clinic ${id}`, rawName: `Clinic ${id}`, industry: "dental", location, domain: `c${id}.sa` },
  icpFit: { score: 80 },
  contact: { name: "—" },
  verification: "UNVERIFIED",
  updatedAt: new Date().toISOString(),
});
const leads = [lead(1, "Riyadh"), lead(2, "Jeddah")];

// Leads keeps its filter panel collapsed (useState(false)), so the industry <select> is not in
// the server render. Open it: showFilters is the only boolean state on this page.
vi.mock("react", async () => {
  const actual = await vi.importActual("react");
  return {
    ...actual,
    default: { ...actual.default, useState: (init) => actual.useState(init === false ? true : init) },
    useState: (init) => actual.useState(init === false ? true : init),
  };
});

let LANG = "ar";
vi.mock("@/lib/leadEngine/store", () => ({
  isLiveStatus: () => false,
  useLeadEngine: () => ({
    lang: LANG,
    t: (k) => k,
    leads,
    jobs: [],
    chat: [],
    connected: true,
    lastSuccessAt: Date.now(),
    everLoaded: true,
    lastError: null,
    refresh: () => {},
    currentUser: { name: "x" },
    activeJobId: null,
  }),
}));

// utils.js reads window.self/top at import time and the vitest env is `node`. renderToString
// needs no real DOM, so a minimal stub is enough and avoids adding jsdom to the lockfile.
globalThis.window = globalThis.window || { self: {}, top: {} };
globalThis.window.top = globalThis.window.self;
const { default: Leads } = await import("./Leads");

const html = (lang) => {
  LANG = lang;
  return renderToString(
    <MemoryRouter>
      <Leads />
    </MemoryRouter>,
  );
};

describe("Leads page shows DB values in the UI language", () => {
  it("Arabic: no raw English city/industry anywhere in the rendered page", () => {
    const out = html("ar");
    expect(out).toContain("طب الأسنان");
    expect(out).toContain("الرياض");
    expect(out).toContain("جدة");
    // the filter <option> is the easiest place to forget
    expect(out).toMatch(/<option[^>]*value="dental"[^>]*>طب الأسنان<\/option>/);
    expect(out).not.toMatch(/>\s*dental\s*</i);
    expect(out).not.toMatch(/>\s*(Riyadh|Jeddah)\s*[<·]/);
  });

  it("English: values are left exactly as stored", () => {
    const out = html("en");
    expect(out).toContain("dental");
    expect(out).toContain("Riyadh");
    expect(out).not.toContain("طب الأسنان");
  });

  it("the filter still matches on the stored value, not the label", () => {
    // translating the label must not change what the filter compares against
    expect(html("ar")).toMatch(/<option[^>]*value="dental"/);
  });
});
