import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { BankAccount, Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { BankTab } from "./BankTab";

const person = (id: number, roles: string[]): Me => ({
  id,
  username: `user${id}`,
  name: `User ${id}`,
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const pending: BankAccount = {
  id: 3,
  employee: 1,
  bank_name: "Republic Bank (Guyana)",
  branch: "Water Street",
  account_name: "Asha Persaud",
  account_number_masked: "••••7890",
  state: "pending",
  state_name: "Waiting for approval",
  effective_from: null,
  requested_by: 10,
  requested_by_name: "Natasha Khan",
  decided_by_name: null,
  decided_at: null,
  decision_note: "",
  created_at: "2026-10-01T09:00:00-04:00",
};
const page = (results: BankAccount[]) => ({ body: { count: results.length, next: null, previous: null, results } });

describe("bank details", () => {
  it("lets a second person approve, and says the employee was told", async () => {
    const server = fakeServer({
      "GET /bank-accounts/": [page([pending]), page([{ ...pending, state: "active", state_name: "In use" }])],
      "POST /bank-accounts/3/approve/": { body: { ...pending, state: "active" } },
    });
    render(<BankTab employeeId={1} me={person(20, ["finance"])} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("status")).toHaveTextContent("the employee has been told");
    expect(server.calls.find((c) => c.path === "/bank-accounts/3/approve/")?.body).toEqual({ note: "" });
  });

  it("never offers the decision to the person who proposed the change", async () => {
    fakeServer({ "GET /bank-accounts/": page([pending]) });
    render(<BankTab employeeId={1} me={person(10, ["hr_manager"])} />);
    expect(await screen.findByText("You proposed this change, so someone else must decide it.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("needs a note to reject", async () => {
    const server = fakeServer({
      "GET /bank-accounts/": page([pending]),
      "POST /bank-accounts/3/reject/": { body: { ...pending, state: "rejected" } },
    });
    render(<BankTab employeeId={1} me={person(20, ["finance"])} />);
    const reject = await screen.findByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Note for Republic Bank (Guyana)"), "Name differs from bank letter");
    await user.click(reject);
    expect(server.calls.find((c) => c.path === "/bank-accounts/3/reject/")?.body).toEqual({
      note: "Name differs from bank letter",
    });
  });

  it("shows the full number only on request, and only to those who decide", async () => {
    fakeServer({
      "GET /bank-accounts/": page([{ ...pending, state: "active", state_name: "In use" }]),
      "POST /bank-accounts/3/reveal/": { body: { account_number: "1234567890" } },
    });
    const { unmount } = render(<BankTab employeeId={1} me={person(30, ["hr_officer"])} />);
    await screen.findByText("••••7890");
    expect(screen.queryByRole("button", { name: /Show the full account number/ })).not.toBeInTheDocument();
    unmount();

    render(<BankTab employeeId={1} me={person(20, ["finance"])} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Show the full account number/ }));
    expect(await screen.findByText("1234567890")).toBeInTheDocument();
  });

  it("lets HR propose new details when nothing is waiting", async () => {
    const server = fakeServer({
      "GET /bank-accounts/": [page([]), page([pending])],
      "POST /bank-accounts/": { status: 201, body: pending },
    });
    render(<BankTab employeeId={1} me={person(30, ["hr_officer"])} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Propose new bank details" }));
    const form = screen.getByRole("form", { name: "Propose new bank details" });
    await user.type(within(form).getByLabelText("Bank"), "Republic Bank (Guyana)");
    await user.type(within(form).getByLabelText("Name on the account"), "Asha Persaud");
    await user.type(within(form).getByLabelText("Account number"), "1234-5678-90");
    await user.click(within(form).getByRole("button", { name: "Propose" }));
    expect(await screen.findByRole("status")).toHaveTextContent("used once a second person approves it");
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({ employee: 1, account_number: "1234-5678-90" });
  });
});
