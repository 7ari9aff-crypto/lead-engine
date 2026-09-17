import { describe, expect, it } from "vitest";
import { cn, formatNumber, formatUsd, truncate, relativeTime } from "@/lib/utils";

describe("cn", () => {
  it("joins truthy class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("drops falsy values so conditional classes read cleanly", () => {
    expect(cn("a", false, null, undefined, "", "b")).toBe("a b");
  });

  it("lets later tailwind classes win over earlier ones", () => {
    // tailwind-merge must collapse px-2 + px-4 down to px-4
    expect(cn("px-2", "px-4")).toBe("px-4");
  });
});

describe("formatNumber", () => {
  it("renders null/undefined as an em dash, not a fake 0", () => {
    // Honest UI contract, shared with formatUsd/formatDate/relativeTime:
    // "no data" must never be displayed as a real zero.
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
  });

  it("still renders a real zero as 0", () => {
    expect(formatNumber(0)).toBe("0");
  });

  it("formats thousands with a locale separator", () => {
    const out = formatNumber(12345);
    expect(out.replace(/[^\d]/g, "")).toBe("12345");
  });

  it("honours the digits argument", () => {
    expect(formatNumber(3.14159, 2)).toContain("3.14");
  });
});

describe("formatUsd", () => {
  it("renders null as an em dash, not $0", () => {
    // Honest UI: "no data" is not "zero spend".
    expect(formatUsd(null)).toBe("—");
  });

  it("prefixes non-null amounts with a dollar sign", () => {
    expect(formatUsd(12.5)).toContain("$");
  });
});

describe("truncate", () => {
  it("keeps short strings untouched", () => {
    expect(truncate("hello", 10)).toBe("hello");
  });

  it("cuts long strings and marks the cut", () => {
    const out = truncate("x".repeat(100), 10);
    expect(out.length).toBeLessThanOrEqual(11);
    expect(out.endsWith("…")).toBe(true);
  });
});

describe("relativeTime", () => {
  it("returns a placeholder for missing input", () => {
    expect(typeof relativeTime(null)).toBe("string");
  });

  it("describes a recent timestamp as a short relative string", () => {
    const out = relativeTime(new Date().toISOString());
    expect(out.length).toBeGreaterThan(0);
    expect(out).not.toBe("NaN");
  });
});
