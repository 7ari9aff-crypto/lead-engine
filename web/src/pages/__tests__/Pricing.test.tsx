import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { PricingPage, navHooks } from "@/pages/Pricing";
import { apiPost, ApiError } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return { ...orig, apiPost: { ...orig.apiPost, billingCheckout: vi.fn() } };
});

/** wouter's <Link> needs a Router context — the memory hook keeps the suite
 *  off the real browser history. */
function renderPricing() {
  const { hook } = memoryLocation({ path: "/pricing" });
  return render(
    <Router hook={hook}>
      <PricingPage />
    </Router>
  );
}

/**
 * Pricing checkout wiring: the Pro/Business CTAs must hit
 * POST /api/v1/billing/checkout (not a dead /chat link) and surface the
 * backend's 503 (billing unconfigured) as text instead of a silent no-op.
 */
describe("PricingPage checkout", () => {
  beforeEach(() => {
    vi.mocked(apiPost.billingCheckout).mockReset();
  });

  it("renders the three plan cards", () => {
    renderPricing();
    expect(screen.getByText("ابدأ Pro")).toBeInTheDocument();
    expect(screen.getByText("اشترك Business")).toBeInTheDocument();
    expect(screen.getByText("ابدأ التجربة")).toBeInTheDocument();
  });

  it("posts to checkout and redirects on success", async () => {
    const go = vi.spyOn(navHooks, "goCheckout").mockImplementation(() => {});
    vi.mocked(apiPost.billingCheckout).mockResolvedValue({ checkout_url: "https://stripe.test/c/1" });
    renderPricing();
    fireEvent.click(screen.getByText("ابدأ Pro"));
    await waitFor(() => expect(apiPost.billingCheckout).toHaveBeenCalledWith("pro"));
    expect(go).toHaveBeenCalledWith("https://stripe.test/c/1");
  });

  it("surfaces the backend error instead of navigating when billing is off", async () => {
    const go = vi.spyOn(navHooks, "goCheckout").mockImplementation(() => {});
    vi.mocked(apiPost.billingCheckout).mockRejectedValue(
      new ApiError("billing غير مُهيَّأ على هذا الخادم", 503, { detail: "billing غير مُهيَّأ على هذا الخادم" })
    );
    renderPricing();
    fireEvent.click(screen.getByText("اشترك Business"));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("billing غير مُهيَّأ على هذا الخادم")
    );
    expect(go).not.toHaveBeenCalled();
  });
});
