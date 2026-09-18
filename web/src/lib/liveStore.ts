import { streamLive, type LiveSnapshot } from "@/lib/api";

export type LiveState = "connecting" | "live" | "polling" | "error";

type Listener = () => void;

type StoreState = {
  snapshot: LiveSnapshot | null;
  state: LiveState;
  error: Error | null;
  attempts: number;
};

/**
 * One SSE connection for the whole app.
 *
 * Every dashboard page wants the same live figures, so opening a stream per
 * hook would burn one of the browser's ~6 connections per origin and multiply
 * server work. Instead a single stream is owned here: it starts when the first
 * component subscribes, fans snapshots out to every subscriber, and shuts down
 * when the last one unsubscribes.
 *
 * Correctness rules:
 *  - `state` is only "live" while the stream is genuinely up. If it drops we
 *    switch to "polling" and let subscribers keep their own data fresh; we never
 *    show a fake live badge.
 *  - Reconnects use jittered exponential backoff and stop after maxAttempts.
 *  - Polling is delegated to subscribers via `registerPoll`, so the store stays
 *    free of page-specific fetchers.
 */
class LiveStore {
  private state: StoreState = {
    snapshot: null, state: "connecting", error: null, attempts: 0,
  };
  private listeners = new Set<Listener>();
  private pollers = new Set<() => Promise<LiveSnapshot>>();
  private abort: AbortController | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | undefined;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private failure = 0;
  private streaming = false;
  private started = false;
  private readonly pollMs = 5000;
  private readonly maxAttempts = 6;

  // ── Public API ──────────────────────────────────────────────────────────
  // These are *bound instance properties*, not prototype methods, on purpose.
  //
  // `subscribe` and `getSnapshotState` are handed to React as bare references
  // (`useSyncExternalStore(liveStore.subscribe, liveStore.getSnapshotState)` in
  // LiveBridge and CommandCenter) and React invokes them detached. ES modules
  // are always strict mode, so a prototype method would run with
  // `this === undefined` and throw
  // `TypeError: Cannot read properties of undefined (reading 'state')` on the
  // first dashboard paint — which is exactly the crash the app's ErrorBoundary
  // used to report as "حدث خطأ غير متوقع".
  //
  // Property syntax ALSO keeps each function's identity stable for the lifetime
  // of the store, which `useSyncExternalStore` requires: a fresh identity on
  // every render would tear down and re-open the SSE stream.

  subscribe = (listener: Listener): () => void => {
    this.listeners.add(listener);
    if (!this.started) {
      this.started = true;
      void this.openStream();
    }
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.stop();
    };
  };

  registerPoll = (poll: (() => Promise<LiveSnapshot>) | undefined): () => void => {
    if (!poll) return () => {};
    this.pollers.add(poll);
    // A poller arriving while we are not streaming should start the fallback now.
    if (!this.streaming && !this.pollTimer) this.schedulePoll();
    return () => { this.pollers.delete(poll); };
  };

  getSnapshotState = (): StoreState => this.state;

  private emit(patch: Partial<StoreState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  private schedulePoll(): void {
    if (this.pollTimer || this.streaming) return;
    this.pollTimer = setTimeout(() => {
      this.pollTimer = undefined;
      void this.doPoll();
    }, this.pollMs);
  }

  private async doPoll(): Promise<void> {
    if (this.streaming || this.pollers.size === 0) return;
    const poll = this.pollers.values().next().value as () => Promise<LiveSnapshot>;
    try {
      const value = await poll();
      if (!this.streaming) this.emit({ snapshot: value, error: null });
    } catch (e: unknown) {
      this.emit({ error: e instanceof Error ? e : new Error(String(e)) });
    } finally {
      if (!this.streaming && this.pollers.size > 0) this.schedulePoll();
    }
  }

  private async openStream(): Promise<void> {
    if (this.listeners.size === 0) return;
    this.abort = new AbortController();
    try {
      await streamLive(
        {
          onSnapshot: (snapshot) => {
            this.streaming = true;
            this.failure = 0;
            if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = undefined; }
            this.emit({ snapshot, error: null, state: "live", attempts: 0 });
          },
          onStateChange: (s) => {
            if (s === "connecting") {
              this.emit({ state: this.state.state === "live" ? "live" : "connecting" });
            }
          },
        },
        this.abort.signal
      );
    } catch (e: unknown) {
      this.streaming = false;
      this.failure += 1;
      this.emit({
        error: e instanceof Error ? e : new Error(String(e)),
        state: "polling",
        attempts: this.failure,
      });
    }
    // Stream closed or failed: fall back to polling, then try again.
    this.streaming = false;
    if (this.listeners.size === 0) return;
    this.schedulePoll();
    if (this.failure < this.maxAttempts) {
      const backoff = Math.min(30000, 1000 * 2 ** Math.max(0, this.failure - 1));
      this.retryTimer = setTimeout(() => {
        this.retryTimer = undefined;
        void this.openStream();
      }, backoff + Math.random() * 500);
    } else {
      this.emit({ state: "error" });
    }
  }

  /** Bound for the same reason as `subscribe` — callers pass it around freely. */
  refresh = (): void => {
    if (this.streaming) return;
    if (this.retryTimer) { clearTimeout(this.retryTimer); this.retryTimer = undefined; }
    this.failure = 0;
    this.emit({ state: "connecting", attempts: 0, error: null });
    void this.openStream();
  };

  private stop(): void {
    this.started = false;
    this.streaming = false;
    if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = undefined; }
    if (this.retryTimer) { clearTimeout(this.retryTimer); this.retryTimer = undefined; }
    this.abort?.abort();
    this.abort = null;
  }
}

export const liveStore = new LiveStore();
