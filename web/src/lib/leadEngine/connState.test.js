// Connection-state logic for list surfaces — PURE functions, unit-tested in
// node env (no DOM). These encode the rule the v12 rewrite lost:
//
//   a failed refresh must NEVER render as "no data".
//
// Three distinct truths are kept apart:
//   "backend-down"  → the server is unreachable (or never answered once):
//                     the list may be stale/empty — say THAT, not "nothing
//                     exists yet" (gap register FAIL-01: a compliance surface
//                     reporting "nothing happened" while the server is broken).
//   "filtered"      → rows exist on screen, the current query/filter hides them.
//   "genuinely-empty" → a successful load returned zero rows. The only case
//                     where an empty-state message like "no leads yet" is true.
import { describe, it, expect } from "vitest";
import { mergeActivity, listEmptyKind } from "./connState";

describe("mergeActivity", () => {
  const srv = (id, at) => ({ id, actor: "SYSTEM", action: "job.completed", target: id, at, detail: "" });

  it("puts local rows before server rows of the same instant", () => {
    const at = "2026-10-13T10:00:00.000Z";
    const out = mergeActivity([srv("s1", at)], [{ id: "l1", actor: "you", action: "decision", at, target: "l", detail: "" }]);
    expect(out.map((e) => e.id)).toEqual(["l1", "s1"]);
  });

  it("sorts newest first across both sources", () => {
    const out = mergeActivity(
      [srv("s1", "2026-10-13T08:00:00.000Z"), srv("s2", "2026-10-13T12:00:00.000Z")],
      [{ id: "l1", actor: "you", action: "x", at: "2026-10-13T10:00:00.000Z" }],
    );
    expect(out.map((e) => e.id)).toEqual(["s2", "l1", "s1"]);
  });

  it("dedupes by id so an event echoed back by the server is not doubled", () => {
    const at = "2026-10-13T10:00:00.000Z";
    const out = mergeActivity([srv("dup", at)], [{ id: "dup", actor: "you", action: "x", at }]);
    expect(out).toHaveLength(1);
  });

  it("keeps locally recorded actions visible when the backend poll fails", () => {
    // The store keeps stale server rows on failure; local rows must survive
    // alongside them (they are the operator's own audit trail).
    const out = mergeActivity([srv("s1", "2026-10-13T08:00:00.000Z")], [
      { id: "l1", actor: "you", action: "approve", at: "2026-10-13T09:00:00.000Z" },
    ]);
    expect(out.map((e) => e.id)).toEqual(["l1", "s1"]);
  });

  it("tolerates missing inputs", () => {
    expect(mergeActivity(undefined, undefined)).toEqual([]);
    expect(mergeActivity([srv("s1", "2026-10-13T08:00:00.000Z")], [])).toHaveLength(1);
  });
});

describe("listEmptyKind", () => {
  const base = { connected: true, everLoaded: true, total: 0, filtered: 0 };

  it("is genuinely-empty only after a successful load of zero rows", () => {
    expect(listEmptyKind(base)).toBe("genuinely-empty");
  });

  it("is filtered when rows exist but the current filter hides them", () => {
    expect(listEmptyKind({ ...base, total: 12, filtered: 0 })).toBe("filtered");
  });

  it("is loading while the first load is in flight with no tracked failure", () => {
    // everLoaded=false and no tracked error at all (the exact shape the store
    // passes on its very first refresh) = the request is out, not failed.
    // Refined over the earlier "backend-down" rule, which showed a false
    // failure on every cold page load (found by the browser walk).
    expect(listEmptyKind({ ...base, everLoaded: false, lastError: undefined })).toBe("loading");
  });

  it("is backend-down when a load fails after earlier success", () => {
    expect(listEmptyKind({ ...base, connected: false })).toBe("backend-down");
  });

  it("is loading while the first load is still in flight", () => {
    // everLoaded=false with no error yet = the request is out, not failed.
    // The old rule rendered "server unreachable" here — a false failure on
    // every cold page load (found by the browser walk).
    expect(listEmptyKind({ ...base, everLoaded: false, lastError: null })).toBe("loading");
  });

  it("is backend-down when the first load already failed", () => {
    expect(listEmptyKind({ ...base, everLoaded: false, lastError: "HTTP 500" })).toBe("backend-down");
  });
});
