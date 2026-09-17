import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { computeWindowRange, type WindowRange } from "@/lib/windowRange";

/**
 * Window-virtualise a long list against the *window* scroll (the leads table
 * lives inside the page, not in its own scroll box, so an element-level
 * virtualiser would not see the scroll at all).
 *
 * Returns the slice to render plus the spacer heights that keep the scrollbar
 * honest. Rendering is O(viewport), not O(rows), which is what makes a 10k-row
 * table feel the same as a 50-row one.
 */
export function useWindowVirtualRows({
  count,
  rowHeight,
  overscan = 8,
}: {
  count: number;
  rowHeight: number;
  overscan?: number;
}): WindowRange & { containerRef: (node: HTMLElement | null) => void } {
  const containerEl = useRef<HTMLElement | null>(null);
  const [containerTop, setContainerTop] = useState(0);
  const [range, setRange] = useState<WindowRange>(() =>
    computeWindowRange({
      count,
      scrollY: 0,
      viewportHeight: typeof window === "undefined" ? 800 : window.innerHeight,
      containerTop: 0,
      rowHeight,
      overscan,
    })
  );

  const measure = useCallback(() => {
    const viewportHeight = typeof window === "undefined" ? 800 : window.innerHeight;
    const scrollY = typeof window === "undefined" ? 0 : window.scrollY;
    const top = containerEl.current
      ? containerEl.current.getBoundingClientRect().top + scrollY
      : 0;
    setContainerTop(top);
    setRange(
      computeWindowRange({ count, scrollY, viewportHeight, containerTop: top, rowHeight, overscan })
    );
  }, [count, rowHeight, overscan]);

  // Recompute on scroll + resize; both listeners are passive so they never
  // block the browser's own scrolling.
  useEffect(() => {
    measure();
    window.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

  // Layout effect after the node attaches so the measured offset is real, not
  // the 0 we assume before mount.
  useLayoutEffect(() => {
    measure();
  }, [measure]);

  const containerRef = useCallback(
    (node: HTMLElement | null) => {
      containerEl.current = node;
      if (node) measure();
    },
    [measure]
  );

  // `containerTop` is surfaced for callers that need it; the slice is what
  // matters for rendering.
  void containerTop;
  return { ...range, containerRef };
}