// Connection-state logic for list surfaces — PURE functions (no React, no
// DOM) so they run under vitest's node environment and every branch is
// pinned by a test (web/src/lib/leadEngine/connState.test.js).
//
// The rule these encode: a failed refresh must never render as "no data"
// (gap register FAIL-01 — the audit trail once showed "0 حدث" while the
// endpoint was returning HTTP 500).

/**
 * Merge server activity rows with locally recorded actions.
 * Local rows win a dedupe by id and sort before server rows of the same
 * instant (the operator's action happened after the echo arrived). The
 * result is newest-first, the order every feed renders.
 *
 * @param {Array<{id: string, at: string}>} [serverRows]
 * @param {Array<{id: string, at: string}>} [localRows]
 * @returns {Array<object>} merged, newest first
 */
export function mergeActivity(serverRows, localRows) {
  const seen = new Set();
  const out = [];
  for (const row of [...(localRows || []), ...(serverRows || [])]) {
    if (!row || seen.has(row.id)) continue;
    seen.add(row.id);
    out.push(row);
  }
  return out.sort((a, b) => new Date(b.at) - new Date(a.at));
}

/**
 * Decide WHY a list is empty. The empty-state component must render a
 * different truth for each case — "no results yet" is a lie when the
 * server is unreachable, and "server unreachable" is a lie when the first
 * load is simply still in flight.
 *
 * @param {{connected: boolean, everLoaded: boolean, total: number, filtered: number, lastError?: string|null}} s
 * @returns {"filtered"|"backend-down"|"genuinely-empty"|"loading"}
 */
export function listEmptyKind({ connected, everLoaded, total, filtered, lastError }) {
  if (filtered === 0 && total > 0) return "filtered";
  // First load not finished yet: a failure would have set lastError. Without
  // one, the honest answer is "still loading", never "server down".
  if (!everLoaded) return lastError ? "backend-down" : "loading";
  if (!connected) return "backend-down";  // reachable before, not now
  return "genuinely-empty";               // a successful load of zero rows
}
