import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Me, Paginated, PayRun, Payslip } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { PayrollScreen } from "./PayrollScreen";

function me(over: Partial<Me> = {}): Me {
  return {
    id: 1,
    username: "asha",
    name: "Asha Persaud",
    roles: ["employee"],
    mfa_required: false,
    mfa_verified: true,
    employee_id: 1,
    ...over,
  };
}

function payslip(over: Partial<Payslip> = {}): Payslip {
  return {
    id: 1,
    pay_run: 1,
    period: "2026-11",
    pay_run_state: "disbursed",
    employee: 1,
    employee_name: "Asha Persaud",
    employee_no: "E0001",
    gross: "150000.00",
    unpaid_days: 0,
    unpaid_deduction: "0.00",
    nis_employee: "8400.00",
    nis_employer: "12600.00",
    paye: "400.00",
    net: "141200.00",
    breakdown: {},
    has_document: true,
    ...over,
  };
}

function run(over: Partial<PayRun> = {}): PayRun {
  return {
    id: 1,
    period: "2026-11",
    state: "draft",
    calculated_at: null,
    approved_at: null,
    disbursed_at: null,
    total_gross: 0,
    total_nis_employee: 0,
    total_nis_employer: 0,
    total_paye: 0,
    total_net: 0,
    allowed_actions: ["calculate"],
    ...over,
  };
}

function paginated<T>(results: T[]): Paginated<T> {
  return { count: results.length, next: null, previous: null, results };
}

describe("payroll screen", () => {
  it("shows an employee their own payslips, with no tabs and no pay-run data fetched", async () => {
    fakeServer({ "GET /payroll/payslips/": { body: paginated([payslip()]) } });
    render(<PayrollScreen me={me()} path="/payroll" onNavigate={() => undefined} />);
    expect(await screen.findByText("2026-11")).toBeInTheDocument();
    expect(screen.getByText("G$141,200.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute(
      "href",
      "/api/v1/payroll/payslips/1/download/",
    );
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("says nothing has been disbursed yet when there are no payslips", async () => {
    fakeServer({ "GET /payroll/payslips/": { body: paginated([]) } });
    render(<PayrollScreen me={me()} path="/payroll" onNavigate={() => undefined} />);
    expect(await screen.findByText("Nothing has been disbursed to you yet.")).toBeInTheDocument();
  });

  it("lets Finance start a run, calculate it, and shows the net pay it found", async () => {
    const calculated = run({ state: "calculated", total_net: 141200, allowed_actions: ["recalculate", "approve", "reopen"] });
    fakeServer({
      "GET /payroll/payslips/": { body: paginated([]) },
      "GET /payroll/runs/": [
        { body: paginated([run()]) },
        { body: paginated([run()]) },
        { body: paginated([calculated]) },
      ],
      "POST /payroll/runs/": { status: 201, body: run() },
      "POST /payroll/runs/1/transition/": { body: calculated },
    });
    const finance = me({ roles: ["finance"], employee_id: null });
    render(<PayrollScreen me={finance} path="/payroll?tab=runs" onNavigate={() => undefined} />);

    const form = await screen.findByRole("form", { name: "Start a pay run" });
    await userEvent.setup().type(form.querySelector("input")!, "2026-11");
    await userEvent.setup().click(within(form).getByRole("button", { name: "Start" }));
    expect(await screen.findByText(/Pay run for 2026-11 created/)).toBeInTheDocument();

    const card = await screen.findByRole("article", { name: "Pay run 2026-11" });
    await userEvent.setup().click(within(card).getByRole("button", { name: "Calculate" }));
    expect(await screen.findByText(/Someone else must approve it/)).toBeInTheDocument();
  });

  it("does not offer the Pay runs tab, or fetch runs, to a plain employee", async () => {
    fakeServer({ "GET /payroll/payslips/": { body: paginated([]) } });
    render(<PayrollScreen me={me()} path="/payroll" onNavigate={() => undefined} />);
    await screen.findByText("Nothing has been disbursed to you yet.");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });
});
