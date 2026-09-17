import { describe, expect, it } from "vitest";
import { computeWindowRange, type WindowRangeInput } from "@/lib/windowRange";

/**
 * `computeWindowRange` is the only part of the leads table virtualiser that can
 * be reasoned about without a DOM, so it carries the weight of the guarantee:
 * "a 10k-row table renders only what fits on screen". These tests pin the slice
 * AND the spacer arithmetic (the spacers are what keep the scrollbar honest).
 */
const base: WindowRangeInput = {
  count: 10_000,
  scrollY: 0,
  viewportHeight: 800,
  containerTop: 0,
  rowHeight: 48,
};

describe("computeWindowRange", () => {
  it("renders only the viewport slice, not the whole list", () => {
    const r = computeWindowRange(base);
    // 800px viewport / 48px rows = 17 rows, plus the default overscan of 8.
    expect(r.end - r.start).toBeLessThan(40);
    expect(r.end).toBeLessThan(10_000);
  });

  it("keeps the spacers equal to the rows that are not rendered", () => {
    const r = computeWindowRange(base);
    const rendered = r.end - r.start;
    expect(rendered * base.rowHeight + r.padTop + r.padBottom).toBe(
      base.count * base.rowHeight
    );
  });

  it("starts at zero and pads only the bottom when scrolled to the top", () => {
    const r = computeWindowRange(base);
    expect(r.start).toBe(0);
    expect(r.padTop).toBe(0);
    expect(r.padBottom).toBeGreaterThan(0);
  });

  it("advances the slice as the page scrolls", () => {
    const top = computeWindowRange(base);
    const scrolled = computeWindowRange({ ...base, scrollY: 24_000 });
    expect(scrolled.start).toBeGreaterThan(top.start);
    expect(scrolled.padTop).toBeGreaterThan(0);
  });

  it("never runs past the end of the list", () => {
    const r = computeWindowRange({ ...base, scrollY: 10_000 * 48 });
    expect(r.end).toBeLessThanOrEqual(base.count);
    expect(r.padBottom).toBe(0);
  });

  it("treats containerTop as the scroll origin of the table", () => {
    // A table that starts 4800px down the page has not scrolled at all when the
    // page is at 4800px — the naive (scrollY / rowHeight) guess would skip 100
    // rows that are still on screen.
    const naive = computeWindowRange({ ...base, scrollY: 4_800 });
    const measured = computeWindowRange({ ...base, scrollY: 4_800, containerTop: 4_800 });
    expect(measured.start).toBe(0);
    expect(measured.start).toBeLessThan(naive.start);
  });

  it("honours an explicit overscan", () => {
    const wide = computeWindowRange({ ...base, overscan: 40 });
    const narrow = computeWindowRange({ ...base, overscan: 0 });
    expect(wide.end - wide.start).toBeGreaterThan(narrow.end - narrow.start);
  });

  it("returns an empty, spacer-free range for an empty list", () => {
    const r = computeWindowRange({ ...base, count: 0 });
    expect(r).toEqual({ start: 0, end: 0, padTop: 0, padBottom: 0 });
  });

  it("degrades safely on a non-positive row height", () => {
    // A bad estimate must not produce NaN gaps in the table body.
    const r = computeWindowRange({ ...base, rowHeight: 0 });
    expect(Number.isFinite(r.padTop)).toBe(true);
    expect(Number.isFinite(r.padBottom)).toBe(true);
    expect(r.start).toBe(0);
  });

  it("shows the whole list when it fits in the viewport", () => {
    const r = computeWindowRange({ ...base, count: 3 });
    expect(r.start).toBe(0);
    expect(r.end).toBe(3);
    expect(r.padTop).toBe(0);
    expect(r.padBottom).toBe(0);
  });
});
