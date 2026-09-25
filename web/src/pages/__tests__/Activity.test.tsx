/**
 * The Activity page is the audit trail. When its endpoint fails, "no data" is
 * an actively false statement — so a 500 must render as a failure.
 *
 * Reproduced live (gap register FAIL-01/FAIL-03): `GET /api/activity` returned
 * 500 while the store held 9 jobs, 4 agent runs and 1 approval, and the page
 * showed "0 حدث" / "لا توجد أحداث" with zero console errors.
 *
 * `fetch` is stubbed rather than `apiGet.activity`, so the real `request()`
 * error path runs: a 500 becomes an `ApiError` carrying `status: 500`, exactly
 * as it does in production, and `friendlyError()` is what turns it into copy.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import ActivityPage from "@/pages/Activity";
import { getAccessToken } from "@/lib/supabase";

// Supabase is configured by web/.env.local, which vitest also loads — without
// this mock every API call would spin up a real SDK client before fetching.
vi.mock("@/lib/supabase", () => ({
  supabaseConfigured: false,
  getSupabase: vi.fn(),
  getAccessToken: vi.fn().mockResolvedValue(null),
  onAuthChange: vi.fn().mockResolvedValue(() => {}),
  currentSession: vi.fn().mockResolvedValue(null),
}));

/** A fresh Response per call: a body stream can only be read once. */
function respond(status: number, body: unknown) {
  return vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      })
    )
  );
}

// `restoreMocks: true` strips factory-level implementations between tests, so
// re-install the no-token auth stub for every case.
beforeEach(() => {
  vi.mocked(getAccessToken).mockResolvedValue(null);
});

describe("Activity page", () => {
  it("shows a failure, not an empty feed, when the API returns 500", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<ActivityPage />);
    await waitFor(
      () => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
    expect(screen.getByText("تعذر تحميل سجل النشاط")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /إعادة المحاولة/ })).toBeInTheDocument();
    // The two lies this fix exists to stop.
    expect(screen.queryByText("لا توجد أحداث")).not.toBeInTheDocument();
    expect(screen.queryByText(/ستظهر هنا أحداث النظام/)).not.toBeInTheDocument();
    expect(screen.queryByText("0 حدث")).not.toBeInTheDocument();
    expect(screen.getByText("غير متاح")).toBeInTheDocument();
    // ...and no transport detail leaks to a non-technical operator.
    expect(screen.getByRole("alert").textContent).not.toMatch(/500|internal error/);
    vi.unstubAllGlobals();
  });

  it("shows the empty feed when the API genuinely returns none", async () => {
    vi.stubGlobal("fetch", respond(200, { events: [] }));
    render(<ActivityPage />);
    await waitFor(
      () => {
        expect(screen.getByText("لا توجد أحداث")).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("0 حدث")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("renders real events and never an error surface when the API is healthy", async () => {
    vi.stubGlobal(
      "fetch",
      respond(200, {
        events: [
          { id: 1, kind: "job.completed", ts: new Date().toISOString(), payload: { job_id: "j1" }, correlation_id: null },
        ],
      })
    );
    render(<ActivityPage />);
    await waitFor(
      () => {
        expect(screen.getByText("اكتملت مهمة")).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("لا توجد أحداث")).not.toBeInTheDocument();
    expect(screen.getByText("1 حدث")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
