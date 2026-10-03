import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { HomeSummary, LeaveBalance, LeaveRequest, Me, MyTerms } from "../../api/types";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { HomeScreen } from "./HomeScreen";

const MRP = { id: 1, code: "MRP", name: "Mon Repos Campus" };
const ESQ = { id: 2, code: "ESQ", name: "Essequibo Campus" };
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

const person = (over: Partial<Me>): Me => ({
  id: 6,
  username: "natasha.khan",
  name: "Natasha Khan",
  roles: ["employee", "hr_officer", "supervisor"],
  mfa_required: false,
  mfa_verified: true,
  employee_id: 6,
  position: "Human Resources Officer",
  unit: "Administration",
  heads: ["Administration"],
  campus: "Mon Repos Campus",
  campuses: [ESQ, MRP],
  ...over,
});

const summary = (over: Partial<HomeSummary>): HomeSummary => ({
  persona: "hr",
  as_at: "2026-10-02",
  ending_days: 90,
  leave: { mine: 1, waiting: 3 },
  staff: {
    campuses: [
      { ...ESQ, active: 3, posts: 3, filled: 3, vacant: 0, frozen: 0 },
      { ...MRP, active: 8, posts: 10, filled: 8, vacant: 1, frozen: 1 },
    ],
    active: 11,
    posts: 13,
    filled: 11,
    vacant: 1,
    frozen: 1,
  },
  units: null,
  ending: [
    { employee: 9, name: "Troy Benjamin", position: "Field Instructor", campus: "Essequibo Campus", what: "contract", on: "2026-11-16" },
    { employee: 5, name: "Roxanne Williams", position: "Farm Attendant", campus: "Mon Repos Campus", what: "probation", on: "2026-12-31" },
  ],
  no_account: {
    count: 3,
    latest: [{ employee: 10, name: "Kemal Bacchus", position: "Farm Attendant", campus: "Mon Repos Campus", started: "2026-09-28" }],
  },
  team: null,
  ...over,
});

const request = (over: Partial<LeaveRequest>): LeaveRequest => ({
  id: 21,
  employee: 7,
  employee_name: "Devon Charles",
  is_mine: false,
  leave_type: 2,
  leave_type_code: "SIC",
  leave_type_name: "Sick leave",
  from_date: "2026-09-21",
  to_date: "2026-09-22",
  days: "2.00",
  days_beyond: "0.00",
  reason: "Medical certificate to follow",
  state: "supervisor_approved",
  evidence_name: "",
  evidence_required: false,
  has_evidence: false,
  manager_name: "Natasha Khan",
  decision_comment: "",
  decisions: [],
  allowed_actions: ["approve", "reject"],
  balance_after: "12.00",
  receipt: null,
  ...over,
});
const devon = request({});
const asha = request({
  id: 22,
  employee: 1,
  employee_name: "Asha Persaud",
  leave_type_code: "ANN",
  leave_type_name: "Annual leave",
  from_date: "2026-10-12",
  to_date: "2026-10-13",
  reason: "",
  state: "submitted",
  manager_name: "Michael Thomas",
  allowed_actions: ["reject"],
  balance_after: "8.00",
});

function show(me: Me, routes: Record<string, unknown>, campusId: number | null = null) {
  const server = fakeServer(routes as Parameters<typeof fakeServer>[0]);
  const frame = { setCrumb: vi.fn(), decided: vi.fn() };
  const onNavigate = vi.fn();
  render(
    <FrameContext.Provider value={frame}>
      <HomeScreen me={me} campusId={campusId} onNavigate={onNavigate} />
    </FrameContext.Provider>,
  );
  return { server, frame, onNavigate };
}

const figure = (label: string) => screen.getByText(label).closest(".figure") as HTMLElement;

describe("Home for Human Resources", () => {
  const routes = {
    "GET /home/": { body: summary({}) },
    "GET /leave/requests/?state=submitted": page([asha]),
    "GET /leave/requests/?state=supervisor_approved": page([devon]),
  };

  it("shows the day and campuses, shortcuts with counts, and the figures for every campus", async () => {
    show(person({}), routes);
    expect(await screen.findByText("Friday 2 October 2026 · All campuses")).toBeInTheDocument();
    const shortcuts = screen.getByRole("navigation", { name: "Shortcuts" });
    expect(within(shortcuts).getAllByRole("link").map((a) => a.querySelector(".shortcut-title")?.textContent)).toEqual([
      "People",
      "Leave requests",
      "Letters",
      "Organisation",
      "Reports",
      "Admin",
    ]);
    expect(within(shortcuts).getByRole("link", { name: /People/ })).toHaveTextContent("11 staff files");
    expect(figure("Active staff")).toHaveTextContent("11Essequibo 3 · Mon Repos 8");
    expect(figure("Leave awaiting a decision")).toHaveTextContent("31 is yours to decide");
    expect(figure("Posts filled")).toHaveTextContent("11 of 131 vacant · 1 frozen");
    expect(figure("Contracts ending in 90 days")).toHaveTextContent("1Troy Benjamin, 16/11/2026");
    const headcount = screen.getByRole("region", { name: "Headcount by campus" });
    expect(within(headcount).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Essequibo Campus3 approved posts3 staff",
      "Mon Repos Campus10 approved posts8 staff",
    ]);
  });

  it("approves leave on the spot, and tells the frame so the To do count moves", async () => {
    const { server, frame } = show(person({}), {
      ...routes,
      "POST /leave/requests/21/transition/": { body: { ...devon, state: "approved" } },
    });
    const panel = await screen.findByRole("region", { name: "Waiting for a decision" });
    const row = (await within(panel).findByText("Devon Charles")).closest("li")!;
    expect(row).toHaveTextContent("Sick leave · Medical certificate to follow");
    expect(row).toHaveTextContent("21/09/2026 to 22/09/2026");
    expect(row).toHaveTextContent("2 days · leaves 12 days of sick leave");
    // Still with a manager: shown, but not this officer's to approve here.
    const other = within(panel).getByText("Asha Persaud").closest("li")!;
    expect(other).toHaveTextContent("With Michael Thomas");
    expect(within(other).queryByRole("button")).not.toBeInTheDocument();
    await userEvent.setup().click(within(row).getByRole("button", { name: "Approve sick leave for Devon Charles" }));
    expect(await within(row).findByRole("status")).toHaveTextContent("Approved. Devon has been sent a receipt.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ action: "approve", comment: "" });
    expect(frame.decided).toHaveBeenCalled();
  });

  it("asks for the reason before rejecting, and can go back", async () => {
    const { server } = show(person({}), {
      ...routes,
      "POST /leave/requests/21/transition/": { body: { ...devon, state: "rejected" } },
    });
    const user = userEvent.setup();
    const row = (await screen.findByText("Devon Charles")).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "Reject sick leave for Devon Charles" }));
    const form = within(row).getByRole("form", { name: "Reject sick leave for Devon Charles" });
    expect(within(form).getByRole("button", { name: "Reject request" })).toBeDisabled();
    await user.click(within(form).getByRole("button", { name: "Back" }));
    expect(within(row).queryByRole("form")).not.toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Reject sick leave for Devon Charles" }));
    await user.type(within(row).getByLabelText("Reason for rejecting. Devon will see it."), "Cover is needed that week");
    await user.click(within(row).getByRole("button", { name: "Reject request" }));
    expect(await within(row).findByRole("status")).toHaveTextContent("Rejected. Devon has been told why.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ action: "reject", comment: "Cover is needed that week" });
  });

  it("says when a decision did not go through", async () => {
    show(person({}), {
      ...routes,
      "POST /leave/requests/21/transition/": { status: 409, body: { code: "conflict", detail: "Already decided." } },
    });
    const row = (await screen.findByText("Devon Charles")).closest("li")!;
    await userEvent.setup().click(within(row).getByRole("button", { name: /^Approve/ }));
    expect(await within(row).findByRole("alert")).toHaveTextContent("Already decided.");
  });

  it("lists what needs attention: contracts and probation ending, and new starters to invite", async () => {
    const { onNavigate, server } = show(person({}), {
      ...routes,
      "POST /accounts/": { status: 201, body: { email: "kemal.bacchus@gsa.example", emailed: true } },
    });
    const panel = await screen.findByRole("region", { name: "Needs attention" });
    const rows = within(panel).getAllByRole("listitem");
    expect(rows.map((li) => li.querySelector(".item-tag")?.textContent)).toEqual([
      "Contract ends 16/11/2026",
      "Probation ends 31/12/2026",
      "No account yet",
    ]);
    const user = userEvent.setup();
    await user.click(within(panel).getByRole("button", { name: "Open file: Troy Benjamin" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/9");
    await user.click(within(panel).getByRole("button", { name: "Invite: Kemal Bacchus" }));
    expect(await within(panel).findByRole("status")).toHaveTextContent("Invited. The link went to kemal.bacchus@gsa.example");
    expect(server.calls.find((c) => c.path === "/accounts/")?.body).toEqual({ employee: 10 });
    await user.click(within(panel).getByRole("link", { name: "2 more members of staff have no account" }));
    expect(onNavigate).toHaveBeenCalledWith("/admin/staff");
  });

  it("counts one campus when the switch is set, and says when an invitation fails", async () => {
    const { server } = show(
      person({}),
      {
        ...routes,
        "GET /home/": { body: summary({ staff: null, ending: [], no_account: { count: 1, latest: summary({}).no_account!.latest } }) },
        "POST /accounts/": { status: 400, body: { code: "invalid", detail: "That person already has an account." } },
      },
      2,
    );
    expect(await screen.findByText("Friday 2 October 2026 · Essequibo Campus")).toBeInTheDocument();
    expect(server.calls.some((c) => c.path === "/home/?campus=2")).toBe(true);
    await userEvent.setup().click(screen.getByRole("button", { name: "Invite: Kemal Bacchus" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That person already has an account.");
  });

  it("says when Home cannot be loaded", async () => {
    show(person({}), { "GET /home/": { status: 500, body: { code: "error", detail: "Server error." } } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
    expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
  });
});

describe("Home for a head of unit", () => {
  it("shows their unit, the leave waiting for them, and their team with what ends soon", async () => {
    const kwame = person({
      name: "Kwame Adams",
      roles: ["employee", "supervisor"],
      position: "Livestock Instructor",
      unit: "Livestock Unit",
      heads: ["Livestock Unit"],
      campuses: [MRP],
    });
    const roxanne = request({ id: 30, employee: 5, employee_name: "Roxanne Williams", state: "submitted", leave_type_name: "Annual leave" });
    const { onNavigate } = show(kwame, {
      "GET /home/": {
        body: summary({
          persona: "manager",
          leave: { mine: 1, waiting: null },
          staff: null,
          no_account: null,
          ending: [summary({}).ending![1]],
          team: [
            { employee: 4, name: "Kwame Adams", position: "Livestock Instructor", appointment: "Permanent", started: "2014-03-03", ends: null, probation_end: null, is_me: true },
            { employee: 5, name: "Roxanne Williams", position: "Farm Attendant", appointment: "Temporary", started: "2026-07-01", ends: null, probation_end: "2026-12-31", is_me: false },
            { employee: 10, name: "Kemal Bacchus", position: "Farm Attendant", appointment: "Temporary", started: "2026-09-28", ends: null, probation_end: null, is_me: false },
          ],
        }),
      },
      "GET /leave/requests/?state=submitted": page([roxanne]),
      "GET /leave/requests/?state=supervisor_approved": page([]),
    });
    expect(await screen.findByText("Friday 2 October 2026 · Livestock Unit")).toBeInTheDocument();
    expect(figure("Staff in your unit")).toHaveTextContent("3Livestock Unit");
    expect(await screen.findByText("Roxanne", { selector: ".figure-note" })).toBeInTheDocument();
    expect(figure("Probation ending")).toHaveTextContent("1Roxanne Williams, 31/12/2026");
    expect(screen.getByRole("region", { name: "Waiting for your decision" })).toBeInTheDocument();
    const team = screen.getByRole("region", { name: "Your team" });
    expect(within(team).getAllByRole("listitem").map((li) => li.querySelector(".item-tag")?.textContent)).toEqual([
      "You, head of unit",
      "Probation ends 31/12/2026",
      "Started 28/09/2026",
    ]);
    expect(within(team).getAllByRole("button")).toHaveLength(2);
    await userEvent.setup().click(within(team).getByRole("button", { name: "Open file: Kemal Bacchus" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/10");
  });
});

describe("Home for an employee", () => {
  const balances: LeaveBalance[] = [
    { leave_type: 1, code: "ANN", name: "Annual leave", balance: "10.00", entitlement: "14.00", pending: "2.00", available: "8.00", limited: true },
    { leave_type: 2, code: "SIC", name: "Sick leave", balance: "13.00", entitlement: "14.00", pending: "0.00", available: "13.00", limited: true },
    { leave_type: 3, code: "STU", name: "Study leave", balance: "0.00", entitlement: "0.00", pending: "0.00", available: "0.00", limited: false },
  ];
  const terms = {
    employee_no: "E0001",
    name: "Asha Persaud",
    campus: "Mon Repos Campus",
    position: "Lecturer, Crop Science",
    unit: "Department of Agriculture",
    manager: "Michael Thomas",
    appointment_type: "Permanent",
    start_date: "2019-09-02",
    end_date: null,
    probation_end: null,
    contract: null,
    entitlements: [],
  } as MyTerms;

  it("shows days left, the request in progress, their post, and Request leave", async () => {
    const mine = { ...asha, is_mine: true, allowed_actions: ["cancel"] };
    const { onNavigate } = show(person({ name: "Asha Persaud", roles: ["employee"], employee_id: 1, heads: [], campuses: [MRP] }), {
      "GET /home/": { body: summary({ persona: "employee", leave: { mine: 0, waiting: null }, staff: null, ending: null, no_account: null }) },
      "GET /leave/ledger/balances/": { body: { employee: 1, balances } },
      "GET /leave/requests/?employee=1": page([mine, { ...mine, id: 3, state: "approved" }]),
      "GET /contracts/mine/": { body: terms },
    });
    expect(await screen.findByText("Friday 2 October 2026")).toBeInTheDocument();
    expect(await screen.findByText("8 days of annual leave left")).toBeInTheDocument();
    expect(figure("Annual leave left")).toHaveTextContent("8 days2 days awaiting a decision");
    expect(figure("Sick leave left")).toHaveTextContent("13 daysNothing awaiting a decision");
    expect(screen.queryByText("Study leave left")).not.toBeInTheDocument();
    const requests = screen.getByRole("region", { name: "Your requests" });
    expect(within(requests).getAllByRole("listitem", { name: undefined }).length).toBeGreaterThan(0);
    expect(requests).toHaveTextContent("Annual leave12/10/2026 to 13/10/2026 · 2 daysWith the manager");
    expect(within(requests).getByRole("list", { name: "Progress" })).toHaveTextContent("SentManagerMichael ThomasHuman Resources");
    const employment = await screen.findByRole("region", { name: "Your employment" });
    expect(employment).toHaveTextContent("Lecturer, Crop Science");
    expect(employment).toHaveTextContent("Since 02/09/2019");
    expect(employment).toHaveTextContent("Michael Thomas");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Request leave" }));
    expect(onNavigate).toHaveBeenCalledWith("/leave");
    await user.click(within(employment).getByRole("button", { name: "My contract: Permanent" }));
    expect(onNavigate).toHaveBeenCalledWith("/me");
  });
});

describe("Home for the Principal and other office roles", () => {
  it("shows the Principal each unit's establishment, what ends soon, and the reports", async () => {
    const { onNavigate } = show(person({ name: "Office of the Principal", roles: ["principal"], employee_id: null, heads: [] }), {
      "GET /home/": {
        body: summary({
          persona: "principal",
          leave: { mine: 0, waiting: 2 },
          no_account: null,
          units: [
            { id: 1, name: "Department of Agriculture", campus: "Mon Repos Campus", posts: 4, filled: 3, vacant: 1, frozen: 0 },
            { id: 3, name: "Administration", campus: "Mon Repos Campus", posts: 3, filled: 2, vacant: 0, frozen: 1 },
          ],
        }),
      },
    });
    const units = await screen.findByRole("region", { name: "Establishment by unit" });
    expect(within(units).getAllByRole("listitem").map((li) => li.querySelector(".bar-summary")?.textContent)).toEqual([
      "3 of 4 filled · 1 vacant",
      "2 of 3 filled · 1 frozen",
    ]);
    expect(figure("Leave awaiting a decision")).toHaveTextContent("2With managers and HR");
    expect(screen.queryByRole("region", { name: "Waiting for a decision" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Ending soon" })).toHaveTextContent("Troy Benjamin");
    await userEvent.setup().click(screen.getByRole("button", { name: "Open: Headcount by campus" }));
    expect(onNavigate).toHaveBeenCalledWith("/reports");
  });

  it("gives another office role the pages it opens, and figures only if it reads the staff list", async () => {
    show(person({ name: "Privacy Officer", roles: ["data_protection_officer"], employee_id: null, heads: [], campuses: [ESQ, MRP] }), {
      "GET /home/": { body: summary({ persona: "office", leave: { mine: 0, waiting: null }, staff: null, ending: null, no_account: null }) },
    });
    const shortcuts = await screen.findByRole("navigation", { name: "Shortcuts" });
    expect(within(shortcuts).getAllByRole("link").map((a) => a.querySelector(".shortcut-title")?.textContent)).toEqual([
      "People",
      "Organisation",
      "Reports",
      "Admin",
    ]);
    expect(screen.queryByRole("region", { name: "Figures" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Ending soon" })).not.toBeInTheDocument();
  });
});
