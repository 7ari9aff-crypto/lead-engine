import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Database } from "lucide-react";
import { StatTile } from "@/components/ui/StatTile";

/** The delta badge is the only `rounded-full` span StatTile renders. */
function deltaBadge(container: HTMLElement): HTMLElement | null {
  return container.querySelector("span.rounded-full");
}

/**
 * StatTile is the dashboard's single metric primitive — every KPI row on every
 * page is built from it, so its rendering contract is worth pinning down:
 * numbers get formatted, missing values show the honest placeholder, the
 * sparkline stays decorative, and delta direction drives colour.
 */
describe("StatTile", () => {
  it("renders the label and a formatted value", () => {
    render(<StatTile icon={Database} label="إجمالي الـleads" value={1234} />);
    expect(screen.getByText("إجمالي الـleads")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
  });

  it("shows an em dash when the value is missing instead of a fake 0", () => {
    render(<StatTile icon={Database} label="تعارضات" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders the detail line when provided", () => {
    render(<StatTile icon={Database} label="مهام" value={3} detail="من 12 حملة" />);
    expect(screen.getByText("من 12 حملة")).toBeInTheDocument();
  });

  it("reports an upward delta with an up arrow", () => {
    const { container } = render(
      <StatTile icon={Database} label="نمو" value={10} delta={{ value: 5, label: "%" }} />
    );
    // The badge is one span holding arrow + magnitude + optional unit label,
    // so assert on its full text rather than a fragmented getByText.
    expect(deltaBadge(container)?.textContent).toBe("▲5%");
  });

  it("reports a downward delta with a down arrow", () => {
    const { container } = render(
      <StatTile icon={Database} label="انخفاض" value={10} delta={{ value: -3 }} />
    );
    expect(deltaBadge(container)?.textContent).toBe("▼3");
  });

  it("renders a flat delta neutrally", () => {
    const { container } = render(
      <StatTile icon={Database} label="ثابت" value={10} delta={{ value: 0 }} />
    );
    expect(deltaBadge(container)?.textContent).toBe("—0");
  });

  it("hides the delta while loading so a stale badge never shows", () => {
    const { container } = render(
      <StatTile icon={Database} label="تحميل" value={10} delta={{ value: 5 }} loading />
    );
    expect(deltaBadge(container)).toBeNull();
  });

  it("swaps the value for a skeleton while loading", () => {
    const { container } = render(
      <StatTile icon={Database} label="تحميل" value={999} loading />
    );
    expect(screen.queryByText("999")).not.toBeInTheDocument();
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
  });

  it("fires onClick when the tile is interactive", () => {
    const onClick = vi.fn();
    render(<StatTile icon={Database} label="اضغط" value={1} onClick={onClick} />);
    screen.getByText("اضغط").click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("keeps the sparkline out of the accessibility tree", () => {
    const { container } = render(
      <StatTile icon={Database} label="مخطط" value={5} spark={[1, 4, 2, 8]} />
    );
    const bars = container.querySelectorAll('[aria-hidden="true"]');
    expect(bars.length).toBeGreaterThan(0);
  });
});
