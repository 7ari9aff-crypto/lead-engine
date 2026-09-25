import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState } from "../ErrorState";

describe("ErrorState", () => {
  it("names the subject and offers a retry", () => {
    render(<ErrorState error={new Error("boom")} onRetry={vi.fn()} subject="سجل النشاط" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/سجل النشاط/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /إعادة المحاولة/ })).toBeInTheDocument();
  });

  it("never shows a raw HTTP status to the operator", () => {
    const err = Object.assign(new Error("HTTP 500"), { status: 500 });
    render(<ErrorState error={err} onRetry={vi.fn()} />);
    expect(screen.getByRole("alert").textContent).not.toMatch(/500/);
  });

  it("keeps the whole surface Arabic — English transport detail stays in the console", () => {
    const err = Object.assign(new Error("internal server error"), { status: 500 });
    render(<ErrorState error={err} onRetry={vi.fn()} subject="قائمة المهام" />);
    expect(screen.getByRole("alert").textContent).not.toMatch(/[A-Za-z]{3}/);
  });

  it("renders without a retry when the caller has none to offer", () => {
    render(<ErrorState error={new Error("boom")} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
