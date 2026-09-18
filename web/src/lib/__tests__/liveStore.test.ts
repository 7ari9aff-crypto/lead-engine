/**
 * Regression tests for the live store's public API.
 *
 * Context — this is the bug that shipped: `subscribe` and `getSnapshotState`
 * are handed to React as *bare references*
 * (`useSyncExternalStore(liveStore.subscribe, liveStore.getSnapshotState)` in
 * LiveBridge, Topbar and CommandCenter). React invokes them with no receiver,
 * and ES modules are always strict mode, so while they were prototype methods
 * every dashboard mount threw
 * `TypeError: Cannot read properties of undefined (reading 'state')` and the
 * app's ErrorBoundary swallowed the whole dashboard behind
 * "حدث خطأ غير متوقع".
 *
 * These tests pin the detached-call contract, plus the identity stability
 * `useSyncExternalStore` needs (a fresh function identity per render would tear
 * the SSE stream down and re-open it on every render).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { streamLive } from "@/lib/api";
import { liveStore } from "@/lib/liveStore";

vi.mock("@/lib/api", () => ({
  streamLive: vi.fn(),
}));

beforeEach(() => {
  // Stream is unavailable → the store must fall back to polling, never throw.
  vi.mocked(streamLive).mockRejectedValue(new Error("stream unavailable"));
});

describe("liveStore detached references", () => {
  it("getSnapshotState survives a receiver-less call", () => {
    const { getSnapshotState } = liveStore;
    expect(() => getSnapshotState()).not.toThrow();
    expect(getSnapshotState()).toMatchObject({ snapshot: null, state: "connecting" });
  });

  it("subscribe survives a receiver-less call and its unsubscribe still works", () => {
    const { subscribe } = liveStore;
    const listener = vi.fn();
    let off: (() => void) | undefined;
    expect(() => { off = subscribe(listener); }).not.toThrow();
    expect(typeof off).toBe("function");
    expect(() => off?.()).not.toThrow();
  });

  it("registerPoll survives a receiver-less call", () => {
    const { registerPoll } = liveStore;
    let off: (() => void) | undefined;
    expect(() => { off = registerPoll(async () => ({}) as never); }).not.toThrow();
    expect(() => off?.()).not.toThrow();
  });

  it("refresh survives a receiver-less call", () => {
    const { refresh } = liveStore;
    expect(() => refresh()).not.toThrow();
    refresh();
  });

  it("keeps a stable function identity across accesses", () => {
    expect(liveStore.subscribe).toBe(liveStore.subscribe);
    expect(liveStore.registerPoll).toBe(liveStore.registerPoll);
    expect(liveStore.getSnapshotState).toBe(liveStore.getSnapshotState);
    expect(liveStore.refresh).toBe(liveStore.refresh);
  });

  it("returns the identical snapshot object until something is emitted", () => {
    // React bails out of re-rendering on identity, so this must hold.
    expect(liveStore.getSnapshotState()).toBe(liveStore.getSnapshotState());
  });
});