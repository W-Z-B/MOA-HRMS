import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AccessReview, Me, ReportRow } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { AccessReviewTab } from "./AccessReviewTab";
import { AdminScreen } from "./AdminScreen";

const person = (roles: string[]): Me => ({
  id: 5,
  username: "hr.manager",
  name: "Hema Manager",
  roles,
  mfa_required: true,
  mfa_verified: true,
  employee_id: null,
});
const row = (over: Partial<Record<string, string | number>> = {}): ReportRow => ({
  employee_id: 10,
  employee_no: "E0010",
  name: "Kemal Bacchus",
  username: "kemal.bacchus",
  role: "Employee",
  where: "Mon Repos Campus",
  given: "01/10/2026",
  given_by: "Natasha Khan",
  last_signed_in: "Never",
  authenticator: "No",
  to_check: "Never signed in",
  ...over,
});
const fine = row({
  employee_id: "",
  employee_no: "",
  name: "Audit Visitor",
  username: "audit.visitor",
  given: "30/09/2026",
  given_by: "",
  to_check: "",
  last_signed_in: "30/09/2026",
});
const signedOff: AccessReview = {
  id: 1,
  reviewed_by_name: "Hema Manager",
  reviewed_at: "2026-09-01T10:00:00-04:00",
  accounts: 12,
  notes: "Took away a supervisor role",
};
const reviews = (results: AccessReview[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const report = { body: { key: "access-review", name: "Who can see what", rows: [row(), fine] } };

describe("access review", () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: new Date("2026-10-05T12:00:00-04:00"), shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("lists every role, links people to their file, and narrows to what needs a look", async () => {
    fakeServer({ "GET /reports/access-review/": report, "GET /access-reviews/": reviews([signedOff]) });
    const onNavigate = vi.fn();
    render(<AccessReviewTab me={person(["auditor"])} campusId={null} onNavigate={onNavigate} />);
    const table = await screen.findByRole("table", { name: "Every role every account holds" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("01/10/2026 by Natasha Khan")).toBeInTheDocument();
    expect(screen.getByText(/Last signed off on .* by Hema Manager, with 12 accounts\. Next due by 02\/12\/2026\./)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign off the review" })).not.toBeInTheDocument(); // an auditor reads only

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(within(table).getByRole("link", { name: "Kemal Bacchus" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/10");
    await user.click(screen.getByLabelText(/Only what needs a look \(1\)/));
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);
  });

  it("is signed off with notes, and says when it is overdue", async () => {
    const overdue = { ...signedOff, reviewed_at: "2026-06-01T10:00:00-04:00" };
    const server = fakeServer({
      "GET /reports/access-review/?campus=1": report,
      "GET /access-reviews/": [reviews([overdue]), reviews([{ ...signedOff, id: 2, reviewed_at: "2026-10-05T12:00:00-04:00" }, overdue])],
      "POST /access-reviews/": { status: 201, body: { ...signedOff, id: 2, accounts: 14 } },
    });
    render(<AccessReviewTab me={person(["hr_manager"])} campusId={1} onNavigate={vi.fn()} />);
    expect(await screen.findByText(/It was due by 01\/09\/2026\./)).toBeInTheDocument();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.type(screen.getByLabelText("What you changed or asked about (optional)"), "Nothing to change");
    await user.click(screen.getByRole("button", { name: "Sign off the review" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Signed off: 14 accounts reviewed.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ notes: "Nothing to change" });
    expect(await screen.findByText(/Next due by/)).toBeInTheDocument();
  });

  it("says when it has never been signed off, and when the list cannot be loaded", async () => {
    fakeServer({
      "GET /reports/access-review/": { status: 403, body: { code: "forbidden", detail: "Your role cannot run this report." } },
      "GET /access-reviews/": reviews([]),
    });
    render(<AccessReviewTab me={person(["hr_manager"])} campusId={null} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your role cannot run this report.");
    expect(await screen.findByText(/has not been signed off yet\. Read the list below and sign it off\./)).toBeInTheDocument();
  });
});

describe("the Admin screen", () => {
  it("shows each person only the tabs their roles may use, and opens the one in the address", async () => {
    fakeServer({ "GET /reports/access-review/": report, "GET /access-reviews/": reviews([]) });
    const onNavigate = vi.fn();
    render(<AdminScreen me={person(["auditor"])} campusId={null} path="/admin/review" onNavigate={onNavigate} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Accounts", "Access review", "Audit log"]);
    expect(screen.getByRole("tab", { name: "Access review" })).toHaveAttribute("aria-selected", "true");
    await screen.findByRole("table");
    await userEvent.setup().click(screen.getByRole("tab", { name: "Accounts" }));
    expect(onNavigate).toHaveBeenCalledWith("/admin");
  });

  it("tells someone with no accounts to look after", () => {
    render(<AdminScreen me={person(["supervisor"])} campusId={null} path="/admin" onNavigate={vi.fn()} />);
    expect(screen.getByText("Your role has no accounts to look after.")).toBeInTheDocument();
  });
});
