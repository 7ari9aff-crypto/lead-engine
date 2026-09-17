/**
 * Pure windowing math for long tables.
 *
 * The leads table renders one `<tr>` per lead. At a few hundred rows that is
 * fine; at 10k the browser spends seconds laying out DOM nobody is looking at.
 * This function answers one question — given the scroll position, which slice of
 * rows must exist right now — and is deliberately pure so it can be unit
 * tested without a DOM.
 *
 * The caller renders `padTop`/`padBottom` as spacer rows so the scrollbar keeps
 * representing the full list while only `end - start` rows are in the DOM.
 */

export type WindowRangeInput = {
  /** Total number of rows in the list. */
  count: number;
  /** Current vertical scroll offset of the scrolling context. */
  scrollY: number;
  /** Height of the visible viewport of that scrolling context. */
  viewportHeight: number;
  /** Distance from the top of the scroll origin to the first table row. */
  containerTop: number;
  /** Estimated height of a single row, in pixels. */
  rowHeight: number;
  /** Extra rows rendered above and below the viewport to absorb fast scrolls. */
  overscan?: number;
};

export type WindowRange = {
  start: number;
  end: number;
  padTop: number;
  padBottom: number;
};

export function computeWindowRange({
  count,
  scrollY,
  viewportHeight,
  containerTop,
  rowHeight,
  overscan = 8,
}: WindowRangeInput): WindowRange {
  // Degenerate inputs must never produce NaN spacers or a negative slice.
  if (count <= 0 || rowHeight <= 0) {
    return { start: 0, end: Math.max(0, count), padTop: 0, padBottom: 0 };
  }

  const firstVisible = Math.floor((scrollY - containerTop) / rowHeight);
  const visibleRows = Math.ceil(viewportHeight / rowHeight);

  const start = Math.max(0, Math.min(count - 1, firstVisible - overscan));
  const end = Math.max(start, Math.min(count, firstVisible + visibleRows + overscan));

  return {
    start,
    end,
    padTop: start * rowHeight,
    padBottom: (count - end) * rowHeight,
  };
}
