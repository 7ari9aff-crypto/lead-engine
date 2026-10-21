import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { trCity, trIndustry, trCountry, trLocation, matchesLocation } from "./dataLabels";

describe("data labels (DB values shown in an Arabic-first UI)", () => {
  it("translates the values production actually stores", () => {
    expect(trCity("Riyadh", "ar")).toBe("الرياض");
    expect(trCity("Jeddah", "ar")).toBe("جدة");
    expect(trIndustry("dental", "ar")).toBe("طب الأسنان");
    expect(trCountry("SA", "ar")).toBe("السعودية");
  });

  it("is case/space insensitive but exact (never a substring rewrite)", () => {
    expect(trCity("  RIYADH ", "ar")).toBe("الرياض");
    expect(trIndustry("Dental Riyadh Group", "ar")).toBe("Dental Riyadh Group");
    expect(trCity("Riyadh Region", "ar")).toBe("Riyadh Region");
  });

  it("leaves unknown values, English mode, and non-strings untouched", () => {
    expect(trCity("Atlantis", "ar")).toBe("Atlantis");
    expect(trCity("Riyadh", "en")).toBe("Riyadh");
    expect(trIndustry("dental", "en")).toBe("dental");
    expect(trCity(null, "ar")).toBe(null);
    expect(trCity(undefined, "ar")).toBe(undefined);
    expect(trCountry(42, "ar")).toBe(42);
  });

  it("translates each part of a combined location", () => {
    expect(trLocation("Riyadh, Saudi Arabia", "ar")).toBe("الرياض، السعودية");
    expect(trLocation("Jeddah", "ar")).toBe("جدة");
    expect(trLocation("Riyadh, Saudi Arabia", "en")).toBe("Riyadh, Saudi Arabia");
    // already Arabic: unchanged apart from the separator
    expect(trLocation("الرياض، السعودية", "ar")).toBe("الرياض، السعودية");
  });

  it("every city/industry/country the DB can hold has an Arabic label", () => {
    // values present in engine.leads on 2026-10-21; extend when a new market is added
    for (const c of ["Riyadh", "Jeddah"]) expect(trCity(c, "ar")).not.toBe(c);
    expect(trIndustry("dental", "ar")).not.toBe("dental");
    expect(trCountry("SA", "ar")).not.toBe("SA");
  });
});

describe("search finds what the user sees", () => {
  it("an Arabic query finds the English-stored city (and vice versa)", () => {
    expect(matchesLocation("Riyadh", "الرياض")).toBe(true);
    expect(matchesLocation("Jeddah", "جدة")).toBe(true);
    expect(matchesLocation("Riyadh", "riyadh")).toBe(true);
    expect(matchesLocation("Riyadh", "ري")).toBe(true);        // partial Arabic
  });
  it("does not over-match and tolerates empty values", () => {
    expect(matchesLocation("Riyadh", "جدة")).toBe(false);
    expect(matchesLocation(null, "الرياض")).toBe(false);
    expect(matchesLocation("Riyadh", "")).toBe(true);
  });
});

describe("no page prints a raw DB city/industry/location", () => {
  const dir = join(import.meta.dirname, "..", "..", "pages", "leadEngine");
  const files = readdirSync(dir).filter((f) => f.endsWith(".jsx") && statSync(join(dir, f)).isFile());
  // every `a.b.location|industry|city` value expression (window.location is browser API)
  const EXPR = /(?<![\w.])(?!window\.)[A-Za-z_][\w?]*(?:\.[A-Za-z_][\w?]*)*\.(?:location|industry|city)\b/g;
  const TRANSLATED = /(?:tr(?:Industry|Location|City|Country)|matchesLocation)\(\s*(?:tr\(\s*)?$/;   // text right before the expr
  const ASTEXT_WITH_TRANSLATOR = /asText\(\s*$/;

  it.each(files)("%s: each shown value is wrapped by a dataLabels translator", (f) => {
    const src = readFileSync(join(dir, f), "utf8");
    const bad = [];
    for (const m of src.matchAll(EXPR)) {
      const before = src.slice(Math.max(0, m.index - 40), m.index);
      const after = src.slice(m.index + m[0].length, m.index + m[0].length + 40);
      const wrapped = TRANSLATED.test(before);
      // asText(x.industry, trIndustry, lang): the translator is passed as an argument
      const passed = ASTEXT_WITH_TRANSLATOR.test(before) && /^\s*,\s*tr(Industry|Location|City)\b/.test(after);
      // comparisons / set-building are logic on the stored value, not display
      const logic = /^\s*(===|!==|\)\s*\))/.test(after) || /!==\s*$/.test(before) || /map\(\([a-z]+\)\s*=>\s*$/.test(before);
      if (!wrapped && !passed && !logic) {
        const line = src.slice(0, m.index).split("\n").length;
        bad.push(`${f}:${line}: ${m[0]}`);
      }
    }
    expect(bad, bad.join("\n")).toEqual([]);
  });
});
