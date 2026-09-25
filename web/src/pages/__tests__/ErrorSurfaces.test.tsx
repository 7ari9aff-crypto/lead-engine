/**
 * A dead backend must never look like an empty product.
 *
 * Extends the Activity precedent (gap register FAIL-01 / FAIL-03) to every
 * remaining surface that fetches. Each case stubs `fetch` with a 500 — so the
 * real `request()` error path runs and `friendlyError()` produces the copy —
 * and asserts BOTH halves of the fix:
 *   1. the failure renders as a failure (role="alert", Arabic, no transport
 *      detail), and
 *   2. the exact sentence the page used to lie with is gone.
 *
 * Pages backed by `useLiveData` need no provider; the `useInstantQuery` ones
 * (Keys, Command Center) are wrapped with `retry: false` so the first 500
 * surfaces instead of burning the waitFor budget on react-query retries.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getAccessToken } from "@/lib/supabase";
import { AgentsPage } from "@/pages/Agents";
import { ResearchPage } from "@/pages/Research";
import { ReviewPage } from "@/pages/Review";
import { ConfigPage } from "@/pages/Config";
import { IcpPage } from "@/pages/Icp";
import { IntegrationsPage } from "@/pages/Integrations";
import { KeysPage } from "@/pages/Keys";
import { CommandCenterPage } from "@/pages/CommandCenter";

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

function withProvider(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.mocked(getAccessToken).mockResolvedValue(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function expectFailureToBeAFailure() {
  await waitFor(
    () => {
      expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    },
    { timeout: 4000 }
  );
  // No HTTP status, no English, no identifiers for a non-technical operator.
  const text = screen.getAllByRole("alert").map((n) => n.textContent).join(" ");
  expect(text).not.toMatch(/500|internal error|Error:/);
}

describe("Agents page", () => {
  it("shows a failure, not an empty registry, when every endpoint answers 500", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<AgentsPage />);
    await expectFailureToBeAFailure();
    expect(screen.getByText("تعذر تحميل الوكلاء والتشغيلات وطلبات الموافقة")).toBeInTheDocument();
    expect(screen.queryByText("لا وكلاء مسجلين")).not.toBeInTheDocument();
    expect(screen.queryByText("لا تشغيلات بعد")).not.toBeInTheDocument();
    // The reassuring "nothing pending" message must not survive either.
    expect(screen.queryByText(/مفيش موافقات مستنية/)).not.toBeInTheDocument();
  });
});

describe("Research page", () => {
  it("shows a failure, not an empty job list, when jobs cannot load", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<ResearchPage />);
    await expectFailureToBeAFailure();
    expect(screen.getByText("تعذر تحميل مهام البحث")).toBeInTheDocument();
    expect(screen.queryByText("لا توجد مهام بحث بعد")).not.toBeInTheDocument();
  });
});

describe("Review page", () => {
  it("shows a failure, not an empty review board, when pending leads cannot load", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<ReviewPage />);
    await expectFailureToBeAFailure();
    expect(screen.getByText("تعذر تحميل قائمة المراجعة")).toBeInTheDocument();
    expect(screen.queryByText("لا يوجد مرشحون بانتظار المراجعة")).not.toBeInTheDocument();
  });
});

describe("Config page", () => {
  it("refuses to render a form of hardcoded defaults when the config cannot load", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<ConfigPage />);
    await expectFailureToBeAFailure();
    expect(screen.getByText("تعذر تحميل ملفات الإعدادات")).toBeInTheDocument();
    expect(screen.queryByText(/أوزان تقييم العملاء/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ملف الاستهداف الحالي/)).not.toBeInTheDocument();
  });
});

describe("ICP page", () => {
  it("keeps the builder usable but stops claiming the criteria are missing", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<IcpPage />);
    await expectFailureToBeAFailure();
    // The version-history list says it failed...
    expect(screen.getByText("تعذر تحميل سجل الإصدارات")).toBeInTheDocument();
    // ...and the active-version claim becomes "unavailable" instead of the
    // dangerous "no active version — deterministic filtering is off".
    expect(screen.getByText(/غير متاح — تعذر جلب النسخة النشطة/)).toBeInTheDocument();
    expect(screen.queryByText(/لا يوجد نسخة نشطة/)).not.toBeInTheDocument();
    expect(screen.queryByText(/لا توجد إصدارات سابقة بعد/)).not.toBeInTheDocument();
    // Local editing stays available on purpose.
    expect(screen.getByText(/الخطوة 1: اختيار القطاع المستهدف/)).toBeInTheDocument();
  });
});

describe("Integrations page", () => {
  it("shows a failure instead of an empty suppression list and empty connections", async () => {
    // The MCP reachability probe is a separate fetch; keep it honest-but-down.
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<IntegrationsPage />);
    await expectFailureToBeAFailure();
    expect(screen.getByText("تعذر تحميل قائمة الحجب")).toBeInTheDocument();
    expect(screen.getByText("تعذر تحميل اتصالات المنصات")).toBeInTheDocument();
    // A suppression list that reads as empty is a compliance lie.
    expect(screen.queryByText(/القائمة فاضية/)).not.toBeInTheDocument();
    // Non-blocking: the static MCP section and the banner stay reachable.
    expect(screen.getByText("خادم MCP")).toBeInTheDocument();
    expect(screen.getByRole("status").textContent).toMatch(/بعض بيانات التكاملات/);
    expect(screen.getByText("غير متاح")).toBeInTheDocument(); // the usage total
  });
});

describe("Keys page", () => {
  it("shows a failure instead of 'no keys configured'", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    withProvider(<KeysPage />);
    await expectFailureToBeAFailure();
    expect(screen.getByText("تعذر تحميل المفاتيح والمزودون")).toBeInTheDocument();
    expect(screen.queryByText("مفاتيح مفعّلة")).not.toBeInTheDocument();
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
  });
});

describe("Command Center", () => {
  it("shows a failure instead of a dashboard of zeroes", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    withProvider(<CommandCenterPage />);
    await expectFailureToBeAFailure();
    expect(screen.getByText("تعذر تحميل مركز القيادة")).toBeInTheDocument();
    expect(screen.queryByText("لا نشاط مسجل بعد.")).not.toBeInTheDocument();
    expect(screen.queryByText("بحث حي")).not.toBeInTheDocument();
    expect(screen.queryByText("النظام: سليم")).not.toBeInTheDocument();
  });
});
