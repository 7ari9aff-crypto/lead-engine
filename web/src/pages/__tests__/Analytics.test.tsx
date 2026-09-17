import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnalyticsPage } from "@/pages/Analytics";
import { apiGet } from "@/lib/api";

/** Analytics answers "trend" — it must fetch the shared endpoints and never
 *  render a fake flat line when the backend has no data in the window. */
vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...orig,
    apiGet: { ...orig.apiGet, status: vi.fn(), analytics: vi.fn() },
  };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AnalyticsPage />
    </QueryClientProvider>
  );
}

// NOTE: vitest is configured with `restoreMocks: true`, which wipes any
// mockResolvedValue set inside the mock factory above — so the resolved
// payloads must be (re)installed here, per test, or the query fns resolve
// to undefined and TanStack warns "Query data cannot be undefined".
beforeEach(() => {
  vi.mocked(apiGet.status).mockResolvedValue({ providers: [], jobs_by_state: {} } as never);
  vi.mocked(apiGet.analytics).mockResolvedValue({
    leads_over_time: [],
    jobs_over_time: [],
    usage_over_time: [],
  } as never);
});

describe("AnalyticsPage honesty", () => {
  it("queries the shared status+analytics endpoints", async () => {
    renderPage();
    await screen.findByText("التحليلات");
    expect(apiGet.status).toHaveBeenCalled();
    expect(apiGet.analytics).toHaveBeenCalled();
  });

  it("renders an honest empty state, not a fake flat line, with no data", async () => {
    renderPage();
    // Empty windows explain themselves instead of drawing a zero line.
    const empties = await screen.findAllByText("لا بيانات في هذا النطاق بعد.");
    expect(empties.length).toBeGreaterThan(0);
  });

  it("offers the 7/30/90 day windows", async () => {
    renderPage();
    await screen.findByText("التحليلات");
    expect(screen.getByText("٧ أيام")).toBeInTheDocument();
    expect(screen.getByText("٣٠ يوم")).toBeInTheDocument();
    expect(screen.getByText("٩٠ يوم")).toBeInTheDocument();
  });
});
