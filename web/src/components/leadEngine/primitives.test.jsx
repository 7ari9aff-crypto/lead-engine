// ScoreRing: colour must distinguish reviewable scores from junk, and bad input
// must not produce NaN geometry.
import React from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, test, vi } from "vitest";

vi.hoisted(() => {
  if (typeof globalThis.window === "undefined") {
    const w = { location: { href: "http://localhost/", origin: "http://localhost", pathname: "/", search: "" },
      matchMedia: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }),
      addEventListener() {}, removeEventListener() {}, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
    w.self = w; w.top = w; globalThis.window = w;
  }
});
const { scoreTone, ScoreRing } = await import("./primitives");

describe("scoreTone", () => {
  test.each([[95, "success"], [80, "success"], [79.9, "warning"], [60, "warning"], [50, "warning"],
    [49, "info"], [30, "info"], [25, "info"], [24, "danger"], [6.7, "danger"], [0, "danger"]])(
    "%s -> %s", (score, tone) => expect(scoreTone(score)).toBe(tone));

  test("a reviewable 60 is not the same colour as junk 6.7 (the original bug)", () => {
    expect(scoreTone(60)).not.toBe(scoreTone(6.7));
  });

  test.each([[null], [undefined], ["abc"], [NaN]])("non-numeric %s is muted, not danger", (v) =>
    expect(scoreTone(v)).toBe("muted"));
});

describe("ScoreRing render", () => {
  test("prints the score once and never NaN geometry", () => {
    for (const v of [55, 0, 100, null, undefined, "x", 250, -5]) {
      const html = renderToString(<ScoreRing score={v} size={36} />);
      expect(html).not.toMatch(/NaN/);
    }
  });
});
