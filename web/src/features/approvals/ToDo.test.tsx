import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Delegation, Employee, Me, WaitingItem } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ToDoScreen } from "./ToDoScreen";

const person = (roles: string[], employee_id: number | null = 4): Me => ({
  id: 3,
  username: "kwame.adams",
  name: "Kwame Adams",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

const leave: WaitingItem = {
  kind: "leave",
  kind_name: "Leave to decide",
  title: "Asha Persaud: annual leave, 05/10/2026 to 06/10/2026",
  since: "2026-10-01T10:00:00Z",
  waited_days: 4,
  overdue: true,
  link: "/leave/requests/12",
  for_whom: "standing in for Michael Thomas",
};
const signature: WaitingItem = {
  kind: "signature",
  kind_name: "To sign",
  title: "Letter of appointment: accept it",
  since: "2026-10-02T09:00:00Z",
  waited_days: 0,
  overdue: false,
  link: "/me",
  for_whom: "",
};
const delegation: Delegation = {
  id: 7,
  delegator: 4,
  delegator_name: "Kwame Adams",
  delegate: 3,
  delegate_name: "Shanta Ramdeen",
  starts: "2026-10-05",
  ends: "2026-10-09",
  reason: "Annual leave",
  cancelled: false,
  in_force: true,
  created_at: "2026-10-01T10:00:00Z",
};

describe("to do", () => {
  it("lists what waits, oldest first, says what is overdue and opens it", async () => {
    fakeServer({ "GET /approvals/waiting/": { body: [leave, signature] }, "GET /approvals/delegations/": page([]) });
    const onNavigate = vi.fn();
    render(<ToDoScreen me={person(["employee", "supervisor"])} onNavigate={onNavigate} />);
    const list = await screen.findByRole("list", { name: "Waiting for you" });
    const [first] = within(list).getAllByRole("listitem");
    expect(first).toHaveTextContent("Leave to decide");
    expect(first).toHaveTextContent("Waiting since 01/10/2026, 4 working days · standing in for Michael Thomas");
    expect(within(first).getByText(/Past its time limit/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Open: Letter of appointment: accept it" }));
    expect(onNavigate).toHaveBeenCalledWith("/me");
  });

  it("says when nothing waits, and shows staff with no one to decide for no stand-ins", async () => {
    fakeServer({ "GET /approvals/waiting/": { body: [] } });
    render(<ToDoScreen me={person(["employee"])} onNavigate={vi.fn()} />);
    expect(await screen.findByText("Nothing is waiting for you.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "While you are away" })).not.toBeInTheDocument();
  });

  it("names a stand-in from colleagues, never oneself, and ends one early", async () => {
    const staff = [
      { id: 4, full_name: "Kwame Adams" },
      { id: 3, full_name: "Shanta Ramdeen" },
    ] as Employee[];
    const server = fakeServer({
      "GET /approvals/waiting/": { body: [] },
      "GET /approvals/delegations/": [page([{ ...delegation, delegator: 2, delegator_name: "Michael Thomas", delegate: 4 }]), page([delegation])],
      "GET /employees/": page(staff),
      "POST /approvals/delegations/": { status: 201, body: delegation },
      "POST /approvals/delegations/7/end/": { body: { ...delegation, cancelled: true } },
    });
    render(<ToDoScreen me={person(["employee", "supervisor"])} onNavigate={vi.fn()} />);
    expect(await screen.findByText("You stand in for Michael Thomas until 09/10/2026.")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Name a stand-in" }));
    const form = screen.getByRole("form", { name: "Name a stand-in" });
    const who = within(form).getByLabelText("Who");
    await within(form).findByRole("option", { name: "Shanta Ramdeen" });
    expect(within(who).queryByRole("option", { name: "Kwame Adams" })).not.toBeInTheDocument();
    await user.selectOptions(who, "3");
    await user.type(within(form).getByLabelText("From"), "2026-10-05");
    await user.type(within(form).getByLabelText("Until"), "2026-10-09");
    await user.type(within(form).getByLabelText("Why (optional)"), "Annual leave");
    await user.click(within(form).getByRole("button", { name: "Name the stand-in" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Shanta Ramdeen stands in for you from 05/10/2026 to 09/10/2026, and is told.",
    );
    expect(server.calls.find((c) => c.path === "/approvals/delegations/" && c.method === "POST")?.body).toEqual({
      delegate: 3,
      starts: "2026-10-05",
      ends: "2026-10-09",
      reason: "Annual leave",
    });
    await user.click(await screen.findByRole("button", { name: "End Shanta Ramdeen standing in" }));
    expect(await screen.findByText("Shanta Ramdeen no longer stands in for you.")).toBeInTheDocument();
  });

  it("says when the list cannot be loaded", async () => {
    fakeServer({ "GET /approvals/waiting/": { status: 500, body: { code: "error", detail: "Server error." } } });
    render(<ToDoScreen me={person(["employee"])} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});
