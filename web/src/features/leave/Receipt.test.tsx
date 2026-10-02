import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { LeaveReceipt } from "../../api/types";
import { Receipt } from "./Receipt";

const receipt: LeaveReceipt = {
  number: "LV-2026-00012",
  issued_at: "2026-10-01T15:20:00-04:00",
  employee_no: "E0001",
  employee_name: "Asha Persaud",
  position: "Lecturer, Crop Science",
  campus: "Mon Repos",
  leave_type: "Sick leave",
  paid: true,
  from_date: "2026-11-02",
  to_date: "2026-11-04",
  return_date: "2026-11-05",
  days: "3.00",
  days_beyond: "1.00",
  evidence: "Doctor's note",
  approvals: [
    { step: "Manager", name: "Michael Thomas", decided_at: "2026-10-01T10:00:00-04:00" },
    { step: "Human Resources", name: "Natasha Khan", decided_at: "2026-10-01T15:20:00-04:00" },
  ],
  balances: [
    { code: "ANN", name: "Annual leave", remaining: "10.00", pending: "2.00" },
    { code: "SIC", name: "Sick leave", remaining: "0.00", pending: "0.00" },
  ],
};

describe("leave receipt", () => {
  it("shows the dates, the days left and who approved, as they stood on the day", () => {
    render(<Receipt receipt={receipt} onBack={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Leave approved" })).toBeInTheDocument();
    expect(screen.getByText(/Receipt LV-2026-00012/)).toBeInTheDocument();
    expect(screen.getByText("Asha Persaud (E0001)")).toBeInTheDocument();
    expect(screen.getByText(/02\/11\/2026 to 04\/11\/2026/)).toBeInTheDocument();
    expect(screen.getByText("05/11/2026")).toBeInTheDocument();
    expect(screen.getByText("1 day, supported by a doctor's note")).toBeInTheDocument();
    const annual = screen.getByText("Annual leave", { selector: ".tile span" }).closest(".tile") as HTMLElement;
    expect(within(annual).getByText("10")).toBeInTheDocument();
    expect(within(annual).getByText("2 days more awaiting a decision")).toBeInTheDocument();
    expect(screen.getByText("Michael Thomas")).toBeInTheDocument();
    expect(screen.getByText("Natasha Khan")).toBeInTheDocument();
  });

  it("leaves out the evidence line when nothing went beyond the entitlement", () => {
    render(<Receipt receipt={{ ...receipt, days_beyond: "0.00" }} onBack={vi.fn()} />);
    expect(screen.queryByText("Beyond the entitlement")).not.toBeInTheDocument();
  });

  it("goes back to the leave page", async () => {
    const onBack = vi.fn();
    render(<Receipt receipt={receipt} onBack={onBack} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Back to leave" }));
    expect(onBack).toHaveBeenCalled();
  });
});
