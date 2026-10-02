import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Account, Me, RoleChoice } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { AccountsTab } from "./AccountsTab";

const person = (id: number, roles: string[]): Me => ({
  id,
  username: `user${id}`,
  name: `User ${id}`,
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const officer = person(30, ["hr_officer", "employee"]);
const administrator = person(1, ["administrator"]);

const employeeGrant = {
  id: 11,
  role: "employee",
  role_name: "Employee",
  campus: 1,
  where: "Mon Repos Campus",
  given_by: "Natasha Khan",
  given_at: "2026-10-01T09:00:00-04:00",
};
const kemal: Account = {
  id: 14,
  username: "kemal.bacchus",
  name: "Kemal Bacchus",
  email: "kemal.bacchus@gsa.example",
  is_active: true,
  state: "invited",
  last_login: null,
  date_joined: "2026-10-01T09:00:00-04:00",
  authenticator: false,
  employee: { id: 10, employee_no: "E0010", full_name: "Kemal Bacchus", campus: 1, campus_name: "Mon Repos Campus", status: "active" },
  roles: [employeeGrant],
  sessions: 0,
  pending_email: null,
};
const manager: Account = {
  ...kemal,
  id: 20,
  username: "hr.manager",
  name: "Hema Manager",
  state: "active",
  last_login: "2026-10-01T08:00:00-04:00",
  authenticator: true,
  employee: null,
  roles: [{ ...employeeGrant, id: 12, role: "hr_manager", role_name: "HR Manager", campus: null, where: "All campuses" }],
};
const roleChoices = (giveable: string[]): RoleChoice[] =>
  [
    ["administrator", "System Administrator", false],
    ["hr_manager", "HR Manager", false],
    ["hr_officer", "HR Officer", true],
    ["supervisor", "Supervisor / Head of Department", true],
    ["employee", "Employee", true],
  ].map(([code, name, needsCampus]) => ({
    code: code as string,
    name: name as string,
    may_give: giveable.includes(code as string),
    needs_campus: needsCampus as boolean,
  }));
const page = (results: Account[], next: string | null = null) => ({ body: { count: results.length, next, previous: null, results } });
const campuses = { body: { count: 2, next: null, previous: null, results: [{ id: 1, code: "MRP", name: "Mon Repos Campus" }, { id: 2, code: "ESQ", name: "Essequibo Campus" }] } };

function server(over: Record<string, unknown> = {}, giveable = ["employee", "supervisor"]) {
  return fakeServer({
    "GET /accounts/": page([kemal, manager]),
    "GET /accounts/roles/": { body: roleChoices(giveable) },
    "GET /org/campuses/": campuses,
    ...over,
  } as Parameters<typeof fakeServer>[0]);
}

const card = async (name: string) => (await screen.findByText(name)).closest("li") as HTMLElement;

describe("accounts", () => {
  it("offers changes only on accounts whose every role the person could give", async () => {
    server();
    render(<AccountsTab me={officer} campusId={null} />);
    const invited = await card("Kemal Bacchus");
    expect(within(invited).getByText("Invited")).toBeInTheDocument();
    expect(within(invited).getByText(/Never signed in/)).toBeInTheDocument();
    expect(within(invited).getByRole("button", { name: "Send the invitation again to Kemal Bacchus" })).toBeInTheDocument();
    const boss = await card("Hema Manager");
    expect(within(boss).getByText("HR Manager, All campuses")).toBeInTheDocument();
    expect(within(boss).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("2 accounts")).toBeInTheDocument();
  });

  it("sends the invitation again and says where it went", async () => {
    server({
      "POST /accounts/14/send-link/": { body: { kind: "invitation", emailed: true, email: "kemal.bacchus@gsa.example" } },
    });
    render(<AccountsTab me={officer} campusId={null} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Send the invitation again to Kemal Bacchus" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The invitation was sent to kemal.bacchus@gsa.example.");
  });

  it("changes a sign-in email with a reason, once the new address confirms it", async () => {
    const calls = server({
      "POST /accounts/14/email/": [
        { status: 409, body: { code: "taken", detail: "Another account uses that address." } },
        { body: { ...kemal, emailed: true, pending_email: "kemal.new@gsa.example" } },
      ],
    });
    render(<AccountsTab me={officer} campusId={null} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change the sign-in email of Kemal Bacchus" }));
    const form = screen.getByRole("form", { name: "Change the sign-in email of Kemal Bacchus" });
    await user.type(within(form).getByLabelText("New email address"), "kemal.new@gsa.example");
    await user.type(within(form).getByLabelText("Why"), "His old mailbox was closed");
    await user.click(within(form).getByRole("button", { name: "Send the link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another account uses that address.");
    await user.click(within(form).getByRole("button", { name: "Send the link" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "A link to confirm it was sent to kemal.new@gsa.example. The address changes when Kemal Bacchus follows it",
    );
    expect(calls.calls.filter((c) => c.path === "/accounts/14/email/").at(-1)?.body).toEqual({
      email: "kemal.new@gsa.example",
      reason: "His old mailbox was closed",
    });
    expect(screen.getByText(/changing to kemal.new@gsa.example once confirmed/)).toBeInTheDocument();
  });

  it("gives a role on a campus, and says the person is signed out", async () => {
    const supervisor = { ...employeeGrant, id: 13, role: "supervisor", role_name: "Supervisor / Head of Department" };
    const calls = server({ "POST /accounts/14/roles/": { status: 201, body: { ...kemal, roles: [employeeGrant, supervisor] } } });
    render(<AccountsTab me={officer} campusId={null} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Give a role to Kemal Bacchus" }));
    const form = screen.getByRole("form", { name: "Give a role to Kemal Bacchus" });
    const role = within(form).getByLabelText("Role");
    expect(within(role).queryByText("HR Officer")).not.toBeInTheDocument(); // an HR officer cannot give it
    await user.selectOptions(role, "supervisor");
    await user.selectOptions(within(form).getByLabelText("Campus"), "1");
    await user.click(within(form).getByRole("button", { name: "Give the role" }));
    expect(await screen.findByRole("status")).toHaveTextContent("is signed out, so it applies from their next sign-in");
    expect(calls.calls.find((c) => c.path === "/accounts/14/roles/")?.body).toEqual({ role: "supervisor", campus: 1 });
    expect(screen.getByText("Supervisor / Head of Department, Mon Repos Campus")).toBeInTheDocument();
  });

  it("takes a role away", async () => {
    const calls = server({ "DELETE /accounts/14/roles/11/": { body: { ...kemal, roles: [] } } });
    render(<AccountsTab me={officer} campusId={null} />);
    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: "Take away Employee, Mon Repos Campus, from Kemal Bacchus" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Employee (Mon Repos Campus) taken away.");
    expect(calls.calls.some((c) => c.method === "DELETE")).toBe(true);
    expect(within(await card("Kemal Bacchus")).getByText("No role")).toBeInTheDocument();
  });

  it("switches an account off only with a reason, and back on", async () => {
    const off = { ...kemal, is_active: false, state: "switched_off" as const };
    const calls = server({
      "POST /accounts/14/deactivate/": { body: off },
      "POST /accounts/14/reactivate/": { body: kemal },
    });
    render(<AccountsTab me={officer} campusId={null} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Switch off the account of Kemal Bacchus" }));
    const form = screen.getByRole("form", { name: "Switch off the account of Kemal Bacchus" });
    const confirm = within(form).getByRole("button", { name: "Switch off" });
    expect(confirm).toBeDisabled();
    await user.type(within(form).getByLabelText("Why switch it off?"), "Left GSA");
    await user.click(confirm);
    expect(await screen.findByRole("status")).toHaveTextContent("every session has ended");
    expect(calls.calls.find((c) => c.path === "/accounts/14/deactivate/")?.body).toEqual({ reason: "Left GSA" });
    expect(within(await card("Kemal Bacchus")).getByText("Switched off")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch on the account of Kemal Bacchus" }));
    await user.type(screen.getByLabelText("Why switch it on?"), "Back from leave");
    await user.click(screen.getByRole("button", { name: "Switch on" }));
    expect(await screen.findByRole("status")).toHaveTextContent("can sign in again");
  });

  it("lets an administrator reset a lost authenticator", async () => {
    const calls = server(
      { "POST /accounts/20/reset-authenticator/": { body: { ...manager, authenticator: false } } },
      ["administrator", "hr_manager", "hr_officer", "supervisor", "employee"],
    );
    render(<AccountsTab me={administrator} campusId={null} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Reset authenticator for Hema Manager" }));
    await user.type(screen.getByLabelText("Why reset the authenticator?"), "Lost phone");
    await user.click(screen.getByRole("button", { name: "Reset authenticator" }));
    expect(await screen.findByRole("status")).toHaveTextContent("sets up a new one at their next sign-in");
    expect(calls.calls.find((c) => c.path === "/accounts/20/reset-authenticator/")?.body).toEqual({ reason: "Lost phone" });
  });

  it("shows the server's refusal on the account it concerns", async () => {
    server({
      "POST /accounts/14/send-link/": {
        status: 403,
        body: { code: "permission_denied", detail: "This person holds a role you cannot give." },
      },
    });
    render(<AccountsTab me={officer} campusId={null} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Send the invitation again to Kemal Bacchus" }));
    expect(within(await card("Kemal Bacchus")).getByRole("alert")).toHaveTextContent("holds a role you cannot give");
  });

  it("finds accounts by name and state, on the campus chosen in the top bar, and shows more", async () => {
    const calls = server({
      "GET /accounts/": page([kemal], "http://hrms.localhost/api/v1/accounts/?page=2"),
      "GET /accounts/?page=2": page([manager]),
      "GET /accounts/?q=kemal&state=invited&campus=1": page([kemal]),
    });
    const { rerender } = render(<AccountsTab me={officer} campusId={null} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Show more" }));
    expect(await screen.findByText("Hema Manager")).toBeInTheDocument();

    rerender(<AccountsTab me={officer} campusId={1} />);
    await user.type(screen.getByLabelText("Find an account"), "kemal");
    await user.selectOptions(screen.getByLabelText("Show"), "invited");
    await user.click(screen.getByRole("button", { name: "Find" }));
    await screen.findByText("1 account");
    expect(calls.calls.at(-1)?.path).toBe("/accounts/?q=kemal&state=invited&campus=1");
  });

  it("says so when the list cannot be loaded", async () => {
    server({ "GET /accounts/": { status: 403, body: { code: "permission_denied", detail: "You do not hold a role that permits this action." } } });
    render(<AccountsTab me={officer} campusId={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not hold a role that permits this action.");
  });
});
