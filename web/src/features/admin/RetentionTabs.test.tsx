import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Breach, DisposalRun, Me, RetentionRule } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { BreachesTab } from "./BreachesTab";
import { RetentionTab } from "./RetentionTab";

const person = (roles: string[]): Me => ({
  id: 5,
  username: "hr.manager",
  name: "Hema Manager",
  roles,
  mfa_required: true,
  mfa_verified: true,
  employee_id: null,
});
const notes: RetentionRule = {
  id: 1,
  code: "doctors-notes",
  name: "Doctor's notes and other medical evidence for leave",
  keep_months: 24,
  counted_from: "the end of the leave they support",
  action: "delete",
  action_name: "Delete",
  automatic: false,
  confirmed: false,
  confirmed_by_name: null,
  confirmed_at: null,
  note: "Proposal in the impact assessment; GSA to confirm",
  open_run: null,
};
const logs: RetentionRule = {
  ...notes,
  id: 4,
  code: "sign-in-records",
  name: "Sign-in attempts and requests for a password link",
  keep_months: 12,
  automatic: true,
  confirmed: true,
  confirmed_by_name: "Hema Manager",
  confirmed_at: "2026-10-01T09:00:00-04:00",
};
const dated: RetentionRule = { ...notes, id: 3, code: "dated-documents", name: "Documents given a date", keep_months: null };
const proposed: DisposalRun = {
  id: 9,
  rule: 1,
  rule_name: notes.name,
  state: "proposed",
  state_name: "Waiting for a second person",
  created_at: "2026-10-01T10:00:00-04:00",
  proposed_by: "Natasha Khan",
  approved_by_name: null,
  approved_at: null,
  proposed_by_me: false,
  items: [
    {
      id: 21,
      description: "Doctor's note: sick leave 2024 (E0007 Devon Charles)",
      employee: 7,
      employee_no: "E0007",
      due_since: "2026-09-22",
      keep_reason: "",
      disposed_at: null,
    },
  ],
};
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

describe("the retention schedule", () => {
  it("shows each rule, whether GSA has agreed it, and changes and confirms a period", async () => {
    const server = fakeServer({
      "GET /privacy/retention-rules/": { body: [notes, dated, logs] },
      "GET /privacy/disposal-runs/": page([]),
      "PATCH /privacy/retention-rules/1/": { body: { ...notes, keep_months: 36 } },
      "POST /privacy/retention-rules/1/confirm/": { body: { ...notes, confirmed: true } },
    });
    render(<RetentionTab me={person(["hr_manager"])} />);
    const table = await screen.findByRole("table", { name: "The retention schedule" });
    const [, first, second, third] = within(table).getAllByRole("row");
    expect(first).toHaveTextContent("24 months");
    expect(first).toHaveTextContent("Not yet. Proposal in the impact assessment; GSA to confirm");
    expect(second).toHaveTextContent("Until the date on each record");
    expect(third).toHaveTextContent("Every night, by itself");
    expect(within(third).queryByRole("button", { name: /Find what is due/ })).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(`Months to keep ${notes.name}`), "36");
    await user.click(screen.getByRole("button", { name: `Save the period for ${notes.name}` }));
    expect(await screen.findByRole("status")).toHaveTextContent("now kept for 36 months");
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ keep_months: 36 });
    await user.click(screen.getByRole("button", { name: `Confirm the period for ${notes.name}` }));
    expect(await screen.findByRole("status")).toHaveTextContent("recorded as agreed by GSA");
  });

  it("lists what is due, keeps one record back with a reason, and approves the rest", async () => {
    const server = fakeServer({
      "GET /privacy/retention-rules/": { body: [notes] },
      "GET /privacy/disposal-runs/": page([proposed]),
      "POST /privacy/retention-rules/1/find/": { status: 201, body: { detail: "1 records are due.", run: proposed } },
      "POST /privacy/disposal-runs/9/keep/": { body: proposed },
      "POST /privacy/disposal-runs/9/approve/": {
        body: { ...proposed, state: "done", items: [{ ...proposed.items[0], disposed_at: "2026-10-01T11:00:00-04:00" }] },
      },
    });
    render(<RetentionTab me={person(["administrator"])} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: `Find what is due: ${notes.name}` }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 records are due.");

    const item = proposed.items[0].description;
    const keep = screen.getByRole("button", { name: `Keep ${item}` });
    expect(keep).toBeDisabled();
    await user.type(screen.getByLabelText(`Why keep ${item}`), "Needed for a hearing");
    await user.click(keep);
    expect(server.calls.find((c) => c.path === "/privacy/disposal-runs/9/keep/")?.body).toEqual({
      item: 21,
      reason: "Needed for a hearing",
    });
    await user.click(screen.getByRole("button", { name: "Approve and destroy" }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 record destroyed");
  });

  it("leaves the approval to someone else, cancels a run, and lets the auditor only read", async () => {
    const server = fakeServer({
      "GET /privacy/retention-rules/": { body: [notes] },
      "GET /privacy/disposal-runs/": page([{ ...proposed, proposed_by_me: true }]),
      "POST /privacy/disposal-runs/9/cancel/": { body: { ...proposed, state: "cancelled" } },
    });
    const { unmount } = render(<RetentionTab me={person(["hr_manager"])} />);
    expect(await screen.findByText("You listed these, so someone else approves.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve and destroy" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Cancel the run" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Nothing was destroyed.");
    expect(server.calls.some((c) => c.path === "/privacy/disposal-runs/9/cancel/")).toBe(true);
    unmount();

    fakeServer({
      "GET /privacy/retention-rules/": { body: [notes] },
      "GET /privacy/disposal-runs/": page([{ ...proposed, state: "done", state_name: "Disposed of", approved_by_name: "Sys Admin", approved_at: "2026-10-01T11:00:00-04:00" }]),
    });
    render(<RetentionTab me={person(["auditor"])} />);
    expect(await screen.findByText(/approved by Sys Admin/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says when the schedule cannot be loaded", async () => {
    fakeServer({
      "GET /privacy/retention-rules/": { status: 403, body: { code: "permission_denied", detail: "Not for your role." } },
      "GET /privacy/disposal-runs/": { status: 403, body: { code: "permission_denied", detail: "Not for your role." } },
    });
    render(<RetentionTab me={person(["hr_manager"])} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not for your role.");
  });
});

const breach: Breach = {
  id: 1,
  reference: "BR-2026-001",
  discovered_at: "2026-10-01T09:00:00-04:00",
  happened: "",
  summary: "A staff list was emailed to the wrong address.",
  data_affected: "Names and phones of 12 staff",
  people_affected: 12,
  risk: "medium",
  risk_name: "Medium",
  contained_at: null,
  commissioner_told_at: null,
  people_told_at: null,
  actions: "",
  closed_at: null,
  recorded_by: "Hema Manager",
  created_at: "2026-10-01T09:05:00-04:00",
};

describe("the breach register", () => {
  it("records a breach and says the administrators were told", async () => {
    const server = fakeServer({
      "GET /privacy/breaches/": [page([]), page([breach])],
      "POST /privacy/breaches/": { status: 201, body: breach },
    });
    render(<BreachesTab me={person(["hr_manager"])} />);
    const user = userEvent.setup();
    expect(await screen.findByText("No breaches recorded.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Record a breach" }));
    await user.type(screen.getByLabelText("Discovered"), "2026-10-01T09:00");
    await user.type(screen.getByLabelText("People affected, if known"), "12");
    await user.type(screen.getByLabelText("What happened"), breach.summary);
    await user.type(screen.getByLabelText("What personal data, and whose"), breach.data_affected);
    await user.click(screen.getByRole("button", { name: "Record it" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Recorded as BR-2026-001. The administrators have been told.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({
      discovered_at: "2026-10-01T09:00",
      people_affected: 12,
      risk: "medium",
    });
  });

  it("follows a breach up and closes it once contained", async () => {
    const contained = { ...breach, contained_at: "2026-10-01T11:00:00-04:00" };
    const server = fakeServer({
      "GET /privacy/breaches/": [page([breach]), page([contained]), page([{ ...contained, closed_at: "2026-10-01T12:00:00-04:00" }])],
      "PATCH /privacy/breaches/1/": { body: contained },
      "POST /privacy/breaches/1/close/": { body: { ...contained, closed_at: "2026-10-01T12:00:00-04:00" } },
    });
    render(<BreachesTab me={person(["administrator"])} />);
    const user = userEvent.setup();
    const close = await screen.findByRole("button", { name: "Close BR-2026-001" });
    expect(close).toBeDisabled();
    await user.type(screen.getByLabelText("Contained"), "2026-10-01T11:00");
    await user.type(screen.getByLabelText("What has been done"), "Recipient deleted it");
    await user.click(screen.getByRole("button", { name: "Save BR-2026-001" }));
    expect(await screen.findByRole("status")).toHaveTextContent("BR-2026-001 updated.");
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({
      contained_at: "2026-10-01T11:00",
      actions: "Recipient deleted it",
    });
    await user.click(await screen.findByRole("button", { name: "Close BR-2026-001" }));
    expect(await screen.findByRole("status")).toHaveTextContent("BR-2026-001 closed.");
    expect(await screen.findByText("Closed")).toBeInTheDocument();
  });

  it("lets the auditor read the register without changing it, and says when it cannot be loaded", async () => {
    fakeServer({ "GET /privacy/breaches/": page([breach]) });
    const { unmount } = render(<BreachesTab me={person(["auditor"])} />);
    expect(await screen.findByText("A staff list was emailed to the wrong address.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    unmount();
    fakeServer({ "GET /privacy/breaches/": { status: 500, body: { code: "error", detail: "Server error." } } });
    render(<BreachesTab me={person(["auditor"])} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});
