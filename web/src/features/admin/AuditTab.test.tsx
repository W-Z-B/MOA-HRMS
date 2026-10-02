import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AuditChainState, AuditCheck, AuditEntry } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { AuditTab } from "./AuditTab";

const change: AuditEntry = {
  id: 41,
  at: "2026-10-01T10:15:00-04:00",
  actor: "Natasha Khan",
  actor_username: "natasha.khan",
  action: "update",
  action_name: "Changed",
  entity: "people.employee",
  record: "Personal details",
  entity_id: 1,
  subject: 1,
  employee_no: "E0001",
  reason: "New phone",
  source_ip: "190.80.1.2",
  changes: [{ field: "Phone", before: "", after: "592-600-1234" }],
  before: {},
  after: {},
  chain: "ab12",
};
const signIn: AuditEntry = {
  ...change,
  id: 40,
  action: "login",
  action_name: "Signed in",
  entity: "auth.user",
  record: "Account",
  entity_id: 7,
  employee_no: null,
  reason: "",
  changes: [],
  actor: "System",
  actor_username: null,
  source_ip: null,
};
const intact: AuditCheck = {
  id: 1,
  checked_at: "2026-10-01T03:30:00-04:00",
  checked_by: "The nightly check",
  rows: 40,
  intact: true,
  last_id: 40,
  first_broken_id: null,
  detail: "",
};
const chainState = (latest: AuditCheck | null): { body: AuditChainState } => ({
  body: { entries: 41, newest: 41, latest_check: latest },
});
const page = (results: AuditEntry[], next: string | null = null) => ({
  body: { count: results.length, next, previous: null, results },
});
const choices = {
  body: {
    actions: [
      { code: "update", name: "Changed" },
      { code: "login", name: "Signed in" },
    ],
    records: [{ code: "people.employee", name: "Personal details" }],
  },
};

describe("the audit log", () => {
  it("lists entries in words and says the log is intact", async () => {
    fakeServer({ "GET /audit/": page([change, signIn]), "GET /audit/chain/": chainState(intact), "GET /audit/choices/": choices });
    render(<AuditTab />);
    const list = await screen.findByRole("list", { name: "Audit entries" });
    const first = within(list).getAllByRole("listitem")[0];
    expect(first).toHaveTextContent("Personal details 1: changed");
    expect(first).toHaveTextContent("by Natasha Khan (natasha.khan)");
    expect(first).toHaveTextContent("About E0001");
    expect(first).toHaveTextContent("Reason: New phone");
    expect(first).toHaveTextContent("Phone changed from blank to 592-600-1234");
    expect(screen.getByText("2 entries")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Nothing changed or removed: 40 entries checked");
  });

  it("filters, and the download carries the same filters", async () => {
    const server = fakeServer({
      "GET /audit/": page([change]),
      "GET /audit/?action=update&employee_no=E0001&since=2026-10-01": page([change]),
      "GET /audit/chain/": chainState(intact),
      "GET /audit/choices/": choices,
    });
    render(<AuditTab />);
    const user = userEvent.setup();
    await screen.findByRole("list", { name: "Audit entries" });
    await user.selectOptions(screen.getByLabelText("What was done"), "update");
    await user.type(screen.getByLabelText("About employee number"), "E0001");
    await user.type(screen.getByLabelText("From"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Show" }));
    await screen.findByText("1 entry");
    expect(server.calls.at(-1)?.path).toBe("/audit/?action=update&employee_no=E0001&since=2026-10-01");
    expect(screen.getByRole("link", { name: "Download as a spreadsheet (CSV)" })).toHaveAttribute(
      "href",
      "/api/v1/audit/export/?action=update&employee_no=E0001&since=2026-10-01",
    );
  });

  it("checks the chain on request", async () => {
    const server = fakeServer({
      "GET /audit/": page([change]),
      "GET /audit/chain/": chainState(null),
      "POST /audit/chain/": chainState({ ...intact, rows: 41, checked_by: "Audit Reviewer" }),
      "GET /audit/choices/": choices,
    });
    render(<AuditTab />);
    expect(await screen.findByText(/has not been checked against its fingerprints yet/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Check every entry now" }));
    expect(await screen.findByRole("status")).toHaveTextContent("41 entries checked");
    expect(server.calls.some((c) => c.method === "POST" && c.path === "/audit/chain/")).toBe(true);
  });

  it("raises the alarm when the log has been altered", async () => {
    const broken = { ...intact, intact: false, first_broken_id: 17, detail: "Entry 17 no longer matches its fingerprint." };
    fakeServer({ "GET /audit/": page([]), "GET /audit/chain/": chainState(broken), "GET /audit/choices/": choices });
    render(<AuditTab />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The log has been altered. Entry 17 no longer matches");
    expect(screen.getByText("0 entries")).toBeInTheDocument();
  });

  it("shows more, and says when the log cannot be read", async () => {
    fakeServer({
      "GET /audit/": page([change], "http://hrms.localhost/api/v1/audit/?page=2"),
      "GET /audit/?page=2": page([signIn]),
      "GET /audit/chain/": chainState(intact),
      "GET /audit/choices/": choices,
    });
    const { unmount } = render(<AuditTab />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Show more" }));
    expect(await screen.findByText("Account 7: signed in")).toBeInTheDocument();
    unmount();

    fakeServer({
      "GET /audit/": { status: 403, body: { code: "permission_denied", detail: "You do not hold a role that permits this action." } },
      "GET /audit/chain/": { status: 403, body: { code: "permission_denied", detail: "No." } },
      "GET /audit/choices/": { status: 403, body: { code: "permission_denied", detail: "No." } },
    });
    render(<AuditTab />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not hold a role that permits this action.");
  });
});
