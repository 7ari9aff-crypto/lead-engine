/**
 * Route-chunk prefetching.
 *
 * Every dashboard page is a lazy chunk. Hovering a nav item warms that chunk
 * so the click paints immediately (this is what makes big dashboards feel
 * instant on navigation); on first idle we also warm the two most-used pages.
 * Failures are ignored — prefetching is an optimisation, never a dependency.
 */
export const ROUTE_CHUNKS: Record<string, () => Promise<unknown>> = {
  "/": () => import("@/pages/CommandCenter"),
  "/analytics": () => import("@/pages/Overview"),
  "/chat": () => import("@/pages/Chat"),
  "/jobs": () => import("@/pages/Jobs"),
  "/leads": () => import("@/pages/Leads"),
  "/research": () => import("@/pages/Research"),
  "/review": () => import("@/pages/Review"),
  "/verify": () => import("@/pages/Verify"),
  "/keys": () => import("@/pages/Keys"),
  "/integrations": () => import("@/pages/Integrations"),
  "/agents": () => import("@/pages/Agents"),
  "/activity": () => import("@/pages/Activity"),
  "/icp": () => import("@/pages/Icp"),
  "/config": () => import("@/pages/Config"),
  "/docs": () => import("@/pages/Docs"),
};

const warmed = new Set<string>();

export function prefetchRoute(href: string): void {
  const loader = ROUTE_CHUNKS[href];
  if (!loader || warmed.has(href)) return;
  warmed.add(href);
  void loader().catch(() => {});
}

/** Warm the default workspaces once the browser has spare time. */
export function prefetchCommonRoutes(): void {
  const idle =
    (window as unknown as { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number })
      .requestIdleCallback;
  const run = () => ["/jobs", "/leads", "/analytics"].forEach(prefetchRoute);
  if (typeof idle === "function") idle(run, { timeout: 2500 });
  else setTimeout(run, 1500);
}
