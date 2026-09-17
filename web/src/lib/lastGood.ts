/**
 * Last-good payload cache (localStorage).
 *
 * Big platforms feel instant because the UI paints the numbers it already
 * knows while the fresh ones load. This module is that layer for our
 * dashboard: every successful query stores its payload locally, and the next
 * session/page paints from it immediately (`initialData`) while react-query
 * refreshes in the background.
 *
 * Bounded by design: only small, high-traffic payloads are stored (status,
 * analytics summary, integrations), each with a size cap and a TTL.
 */
const PREFIX = "leadEngine.lastGood:";

const MAX_PAYLOAD_BYTES = 200_000;

function keyFor(queryKey: readonly unknown[]): string {
  return PREFIX + JSON.stringify(queryKey);
}

export function readLastGood<T>(queryKey: readonly unknown[]): T | null {
  try {
    const raw = localStorage.getItem(keyFor(queryKey));
    if (!raw) return null;
    const entry = JSON.parse(raw) as { at: number; data: T };
    if (!entry || typeof entry.at !== "number") return null;
    return entry.data;
  } catch {
    return null; // corrupted / quota exceeded / private mode — never fatal
  }
}

export function lastGoodAt(queryKey: readonly unknown[]): number {
  try {
    const raw = localStorage.getItem(keyFor(queryKey));
    if (!raw) return 0;
    return (JSON.parse(raw) as { at?: number }).at || 0;
  } catch {
    return 0;
  }
}

export function writeLastGood(queryKey: readonly unknown[], data: unknown): void {
  try {
    const payload = JSON.stringify(data);
    if (payload.length > MAX_PAYLOAD_BYTES) return;
    localStorage.setItem(keyFor(queryKey), JSON.stringify({ at: Date.now(), data }));
  } catch {
    /* storage full / private mode — instant paint is a bonus, not a guarantee */
  }
}

export function clearLastGood(): void {
  try {
    const doomed: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(PREFIX)) doomed.push(k);
    }
    doomed.forEach((k) => localStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}
