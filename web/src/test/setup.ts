/**
 * Vitest global setup.
 *
 * Runs once per test file (jsdom environment). Keeps three things honest:
 *   1. `@testing-library/jest-dom` matchers (toBeInTheDocument, ...).
 *   2. `localStorage` is cleared between tests — several modules (lastGood,
 *      saved searches, theme) persist there and leaking state across tests
 *      produces order-dependent passes.
 *   3. `matchMedia` / `ResizeObserver` shims, which jsdom does not implement
 *      but recharts and the theme hook call unconditionally.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

if (!("ResizeObserver" in window)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Object.defineProperty(window, "ResizeObserver", {
    writable: true,
    value: ResizeObserverStub,
  });
}
