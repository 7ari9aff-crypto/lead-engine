import { useEffect, useRef, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { liveStore } from "@/lib/liveStore";
import { apiGet, normalizeProvider } from "@/lib/api";
import { writeLastGood } from "@/lib/lastGood";

/**
 * The one live connection of the dashboard → the react-query cache.
 *
 * The SSE stream (`/api/live/stream`) pushes frames that are byte-identical to
 * `GET /api/status`, so a connected dashboard updates the instant the server
 * sees a change — no polling, no extra round trips, one connection per tab
 * (not per hook). If the stream is down, the store's fallback poller keeps the
 * numbers moving and the badge stays honest ("جارٍ الاتصال").
 */
export function LiveBridge() {
  const qc = useQueryClient();
  const { snapshot } = useSyncExternalStore(
    liveStore.subscribe,
    liveStore.getSnapshotState
  );

  // Fallback poller — only runs while the stream is actually down.
  useEffect(
    () =>
      liveStore.registerPoll(async () => {
        const status = await apiGet.status();
        return status as never;
      }),
    []
  );

  const prevSignature = useRef<string>("");

  useEffect(() => {
    if (!snapshot) return;
    const status = {
      ...snapshot,
      providers: (snapshot.providers ?? []).map(normalizeProvider),
    };
    qc.setQueryData(["status"], status);
    writeLastGood(["status"], status);

    // Derived series only need a refresh when the underlying counts moved.
    const signature = JSON.stringify([
      status.jobs_by_state ?? {},
      status.leads_by_stage ?? {},
      (status.providers ?? []).length,
    ]);
    if (signature !== prevSignature.current) {
      prevSignature.current = signature;
      void qc.invalidateQueries({ queryKey: ["analytics"] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
    }
  }, [snapshot, qc]);

  return null;
}
