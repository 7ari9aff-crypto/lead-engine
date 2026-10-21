import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Arabic letters join, so letter-spacing breaks them apart (tracking-tight crushes,
// tracking-wider spreads) and `uppercase` is meaningless. index.css neutralises both
// for :lang(ar) in one rule instead of editing every utility class. This test pins
// that rule; the behaviour itself was measured in headless Chrome (getComputedStyle):
//   ar: tracking-tight -0.5px -> normal, uppercase+tracking-wider -> none/normal
//   en: unchanged;  font-mono / .tnum keep their spacing in both.
const css = readFileSync(join(import.meta.dirname, "..", "index.css"), "utf8");

describe("Arabic typography rule in index.css", () => {
  const rule = css.match(/:lang\(ar\)[^{]*\{[^}]*\}/)?.[0] ?? "";

  it("exists, scoped to Arabic", () => {
    expect(rule).not.toBe("");
    expect(rule).toMatch(/^:lang\(ar\)/);
  });
  it("zeroes letter-spacing and text-transform for tracking-* and uppercase", () => {
    expect(rule).toMatch(/tracking-/);
    expect(rule).toMatch(/\.uppercase/);
    expect(rule).toMatch(/letter-spacing:\s*0\s*!important/);
    expect(rule).toMatch(/text-transform:\s*none\s*!important/);
  });
  it("leaves monospace and numeric elements alone (2FA code field uses tracking-widest)", () => {
    expect(rule).toMatch(/:not\(\.font-mono\)/);
    expect(rule).toMatch(/:not\(\.tnum\)/);
  });
  it("is declared after the Tailwind utilities so it wins on order", () => {
    expect(css.indexOf(":lang(ar)")).toBeGreaterThan(css.indexOf("@tailwind utilities"));
  });
});
