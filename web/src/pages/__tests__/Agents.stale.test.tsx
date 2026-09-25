/**
 * The /agents flip defect (gap register FAIL-03 / A11Y-01): the page painted
 * confident zeros ("0 وكلاء", "لا وكلاء مسجلين", "مفيش موافقات") while the
 * first load was still in flight, then flipped to real counts ~30 s later with
 * no live-region announcement.
 *
 * These tests pin the two fixes: pending state shows "غير متاح" tiles and
 * spinners instead of zeros/empties, and the stats grid is an aria-live
 * region so the flip is announced. The stale-refresh banner path is the same
 * page's other truth: real data stays visible behind a warning.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import AgentsPage from "@/pages/Agents";
import { getAccessToken } from "@/lib/supabase";

vi.mock("@/lib/supabase", () => ({
  supabaseConfigured: false,
  getSupabase: vi.fn(),
  getAccessToken: vi.fn().mockResolvedValue(null),
  onAuthChange: vi.fn().mockResolvedValue(() => {}),
  currentSession: vi.fn().mockResolvedValue(null),
}));

beforeEach(() => {
  vi.mocked(getAccessToken).mockResolvedValue(null);
});

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function payloadFor(url: string) {
  if (url.includes("/api/agents")) return { agents: [{ slug: "sdr", name: "SDR", description: "d", status: "active", current_version: "v1" }] };
  if (url.includes("/api/tools")) return { tools: [] };
  if (url.includes("/api/approvals")) return { approvals: [] };
  return { runs: [] };
}

describe("Agents page", () => {
  it("never paints confident zeros while the first load is in flight", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<AgentsPage />);

    expect(screen.getByText("وكلاء مسجلون")).toBeInTheDocument();
    // All four tiles say غير متاح while pending — getAll because there are 4.
    expect(screen.getAllByText("غير متاح")).toHaveLength(4);
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
    expect(screen.queryByText("لا وكلاء مسجلين")).not.toBeInTheDocument();
    expect(screen.queryByText("مفيش موافقات مستنية")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("announces the counts flip via an aria-live region", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(jsonResponse(payloadFor(String(input))))));
    render(<AgentsPage />);
    await waitFor(() => {
      expect(screen.getByText("1")).toBeInTheDocument();
    }, { timeout: 3000 });
    const live = screen.getByText("وكلاء مسجلون").closest("[aria-live]");
    expect(live).not.toBeNull();
    expect(live).toHaveAttribute("aria-live", "polite");
    vi.unstubAllGlobals();
  });

  it("keeps loaded data visible behind a stale banner when a refresh fails", async () => {
    let failRefresh = false;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (failRefresh) {
        return Promise.resolve(new Response(JSON.stringify({ detail: "boom" }), { status: 500 }));
      }
      return Promise.resolve(jsonResponse(payloadFor(String(input))));
    }));
    render(<AgentsPage />);
    await waitFor(() => {
      expect(screen.getByText("SDR")).toBeInTheDocument();
    }, { timeout: 3000 });

    failRefresh = true;
    fireEvent.click(screen.getByRole("button", { name: /تحديث/ }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    }, { timeout: 3000 });
    expect(screen.getByText(/لم تُحدّث/)).toBeInTheDocument();
    // the stale agent stays on screen — the banner exists precisely so it can
    expect(screen.getByText("SDR")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
