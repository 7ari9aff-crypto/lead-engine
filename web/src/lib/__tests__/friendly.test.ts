import { describe, expect, it } from "vitest";
import { friendlyError } from "@/lib/friendly";

/**
 * The dashboard is used by non-technical operators, so `friendlyError` is a
 * user-facing contract, not a formatter: no HTTP codes, no English internals and
 * no identifiers may reach the screen. Arabic messages that already came from
 * the backend must survive untouched (they are written for the operator too).
 */
describe("friendlyError", () => {
  it("never leaks the raw English message to the screen", () => {
    const raw = "TypeError: Failed to fetch";
    const out = friendlyError(new Error(raw));
    expect(out).not.toContain("Failed to fetch");
    expect(out).not.toContain("TypeError");
    expect(out.length).toBeGreaterThan(0);
  });

  it("maps a network failure to a connection message", () => {
    const out = friendlyError(new Error("Failed to fetch"));
    expect(out).not.toContain("HTTP");
    expect(out).not.toMatch(/[A-Za-z]{4,}/); // no English words at all
  });

  it("treats a 401 as an expired session regardless of the message", () => {
    const out = friendlyError({ status: 401, message: "Unauthorized" });
    expect(out).not.toContain("401");
    expect(out).not.toContain("Unauthorized");
  });

  it("treats the Supabase invalid-credentials text as a wrong password", () => {
    const wrongPass = friendlyError(new Error("Invalid login credentials"));
    const expired = friendlyError({ status: 401, message: "Unauthorized" });
    expect(wrongPass).not.toBe(expired);
  });

  it("passes an Arabic backend message straight through", () => {
    const arabic = "\u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u0646\u0627\u0642\u0635\u0629";
    expect(friendlyError({ status: 422, message: arabic })).toBe(arabic);
  });

  it("falls back to a generic Arabic message for anything unrecognised", () => {
    const out = friendlyError(new Error("weird internal failure xyz"));
    expect(out).not.toContain("weird internal failure xyz");
    expect(out).not.toMatch(/[A-Za-z]{4,}/);
  });

  it("survives being handed nothing at all", () => {
    expect(typeof friendlyError(undefined)).toBe("string");
    expect(typeof friendlyError(null)).toBe("string");
  });
});