import { describe, expect, it } from "vitest";
import {
  clearLastGood,
  lastGoodAt,
  readLastGood,
  writeLastGood,
} from "@/lib/lastGood";

describe("lastGood cache", () => {
  const key = ["status"] as const;

  it("returns null when nothing was cached", () => {
    expect(readLastGood(key)).toBeNull();
    expect(lastGoodAt(key)).toBe(0);
  });

  it("round-trips a payload", () => {
    writeLastGood(key, { leads_total: 42 });
    expect(readLastGood(key)).toEqual({ leads_total: 42 });
    expect(lastGoodAt(key)).toBeGreaterThan(0);
  });

  it("namespaces keys per query so different queries never collide", () => {
    writeLastGood(["status"], { a: 1 });
    writeLastGood(["analytics"], { b: 2 });
    expect(readLastGood(["status"])).toEqual({ a: 1 });
    expect(readLastGood(["analytics"])).toEqual({ b: 2 });
  });

  it("survives corrupted storage without throwing", () => {
    localStorage.setItem("leadEngine.lastGood:[\"status\"]", "{not json");
    expect(readLastGood(key)).toBeNull();
    expect(lastGoodAt(key)).toBe(0);
  });

  it("refuses oversized payloads (bounded cache)", () => {
    // 200_000 byte cap — anything larger must be silently dropped.
    writeLastGood(key, "x".repeat(250_000));
    expect(readLastGood(key)).toBeNull();
  });

  it("clearLastGood wipes only its own namespace", () => {
    writeLastGood(["status"], { a: 1 });
    localStorage.setItem("unrelated", "keep me");
    clearLastGood();
    expect(readLastGood(["status"])).toBeNull();
    expect(localStorage.getItem("unrelated")).toBe("keep me");
  });
});
