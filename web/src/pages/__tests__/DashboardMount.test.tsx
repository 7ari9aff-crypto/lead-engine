/**
 * End-to-end mount test for the signed-in dashboard.
 *
 * This is the test that was missing when the crash shipped. With a session
 * present, `/` renders `DashboardLayout`, which mounts `LiveBridge` (and
 * `Topbar`, and `CommandCenterPage`) — all three of which read the shared live
 * store through
 * `useSyncExternalStore(liveStore.subscribe, liveStore.getSnapshotState)`.
 * Those two were prototype methods, so React invoked them detached, `this` was
 * `undefined`, and the first dashboard paint threw
 * `TypeError: Cannot read properties of undefined (reading 'state')`. The
 * ErrorBoundary caught it and the deployed app showed "حدث خطأ غير متوقع"
 * instead of the dashboard.
 *
 * The assertions are deliberately about the *shell* (`<main>` from
 * DashboardLayout) rather than page internals: the shell can only render when
 * no descendant threw during render, which is exactly what regressed.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { apiGet, apiGetExtra, streamLive } from "@/lib/api";

vi.mock("@/lib/supabase", () => ({
  supabaseConfigured: false,
  getSupabase: vi.fn(),
  getAccessToken: vi.fn().mockResolvedValue(null),
  onAuthChange: vi.fn().mockResolvedValue(() => {}),
  currentSession: vi.fn().mockResolvedValue(null),
  signInWithPassword: vi.fn(),
  signUpWithPassword: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...orig,
    streamLive: vi.fn(),
    apiGet: {
      ...orig.apiGet,
      authSession: vi.fn(),
      status: vi.fn(),
      activity: vi.fn(),
      slo: vi.fn(),
      entitlements: vi.fn(),
      leads: vi.fn(),
    },
    apiGetExtra: {
      ...orig.apiGetExtra,
      conflicts: vi.fn(),
    },
  };
});

const STATUS_FIXTURE = {
  version: "1.0.0",
  system: { python: "3.12", supabase_configured: true, db_path: "data/lead_engine.sqlite3" },
  providers: [],
  jobs_by_state: {},
  leads_by_stage: {},
  leads_total: 0,
};

/** The healthy-path wiring: endpoints answer, stream is down → polling fallback. */
function stubHappyBackend() {
  vi.mocked(apiGet.authSession).mockResolvedValue({
    authenticated: true,
    mode: "supabase",
    org_id: "org-1",
  } as never);
  vi.mocked(apiGet.status).mockResolvedValue(STATUS_FIXTURE as never);
  vi.mocked(apiGet.activity).mockResolvedValue({ events: [] } as never);
  vi.mocked(apiGet.slo).mockResolvedValue(null as never);
  vi.mocked(apiGet.entitlements).mockResolvedValue({ plan: "free" } as never);
  vi.mocked(apiGet.leads).mockResolvedValue([] as never);
  vi.mocked(apiGetExtra.conflicts).mockResolvedValue({ conflicts: [] } as never);
  vi.mocked(streamLive).mockRejectedValue(new Error("stream unavailable"));
}

function renderApp() {
  window.history.pushState({}, "", "/");
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  );
}

async function expectDashboardShell() {
  await waitFor(() => {
    expect(document.querySelector("main")).not.toBeNull();
  }, { timeout: 8000 });
  // The crash guard itself: no ErrorBoundary takeover.
  expect(screen.queryByText("حدث خطأ غير متوقع")).toBeNull();
}

beforeEach(() => {
  stubHappyBackend();
});

describe("signed-in dashboard mount", () => {
  it("renders the dashboard shell instead of the ErrorBoundary", async () => {
    renderApp();
    await expectDashboardShell();
  });

  it("keeps rendering when the session is valid but every endpoint answers 401", async () => {
    // Production shape: Supabase says "signed in", the backend rejects the
    // token. Pages must degrade to error states — never take the whole app down.
    const unauthorized = () => Promise.reject(new Error("authentication required"));
    vi.mocked(apiGet.status).mockImplementation(unauthorized as never);
    vi.mocked(apiGet.activity).mockImplementation(unauthorized as never);
    vi.mocked(apiGet.slo).mockImplementation(unauthorized as never);
    vi.mocked(apiGet.entitlements).mockImplementation(unauthorized as never);
    vi.mocked(apiGetExtra.conflicts).mockImplementation(unauthorized as never);

    renderApp();
    await expectDashboardShell();
  });
});