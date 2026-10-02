import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CaseRecord, Employee, Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { CasesScreen } from "./CasesScreen";

const person = (roles: string[]): Me => ({
  id: 3,
  username: "natasha.khan",
  name: "Natasha Khan",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: 6,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

const open: CaseRecord = {
  id: 1,
  reference: "DC-2026-001",
  kind: "discipline",
  kind_name: "Discipline",
  employee: 1,
  employee_name: "Asha Persaud",
  employee_no: "E0001",
  summary: "Absent without leave on 28 and 29 September",
  opened_on: "2026-10-01",
  state: "open",
  state_name: "Open",
  outcome: "",
  outcome_name: "",
  outcome_reasons: "",
  decided_on: null,
  decided_by_name: null,
  lapses_on: null,
  appeal_lodged_on: null,
  appeal_grounds: "",
  appeal_outcome: "",
  appeal_outcome_name: "",
  appeal_reasons: "",
  appeal_decided_on: null,
  appeal_decided_by_name: null,
  closed_on: null,
  officers: [{ id: 1, user: 3, name: "Natasha Khan", part: "Opened the case", named_by_name: "Natasha Khan", named_at: "2026-10-01T10:00:00Z" }],
  entries: [],
  fair_steps: { allegation: false, answered: false },
};
const staff = [
  { id: 1, full_name: "Asha Persaud", employee_no: "E0001", user: 10 },
  { id: 4, full_name: "Kwame Adams", employee_no: "E0004", user: 11 },
  { id: 6, full_name: "Natasha Khan", employee_no: "E0006", user: 3 },
] as Employee[];

describe("cases", () => {
  it("opens a case and shows it", async () => {
    const server = fakeServer({
      "GET /cases/": [page([]), page([open])],
      "GET /employees/": page(staff),
      "POST /cases/": { status: 201, body: open },
    });
    const onNavigate = vi.fn();
    render(<CasesScreen me={person(["hr_officer"])} caseId={null} onNavigate={onNavigate} />);
    expect(await screen.findByText("No case is open to you.")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Open a case" }));
    const form = screen.getByRole("form", { name: "Open a case" });
    await within(form).findByRole("option", { name: "Asha Persaud (E0001)" });
    await user.selectOptions(within(form).getByLabelText("About"), "1");
    await user.type(within(form).getByLabelText("Opened on"), "2026-10-01");
    await user.type(within(form).getByLabelText("The allegation"), "Absent without leave");
    await user.click(within(form).getByRole("button", { name: "Open the case" }));
    expect(onNavigate).toHaveBeenCalledWith("/cases/1");
    expect(server.calls.find((c) => c.path === "/cases/" && c.method === "POST")?.body).toEqual({
      kind: "discipline",
      employee: 1,
      summary: "Absent without leave",
      opened_on: "2026-10-01",
    });
    expect(await screen.findByRole("table", { name: "Cases" })).toHaveTextContent("DC-2026-001");
  });

  it("names someone, records steps, hears the refusal, then decides, takes an appeal and closes", async () => {
    const withSteps = {
      ...open,
      entries: [{ id: 1, kind: "allegation", kind_name: "Allegation put in writing", on: "2026-10-02", text: "Letter of 2 October", by: "Natasha Khan", created_at: "2026-10-02T10:00:00Z" }],
      fair_steps: { allegation: true, answered: false },
    };
    const decided = { ...withSteps, state: "decided" as const, state_name: "Decided", outcome: "written_warning", outcome_name: "Written warning", outcome_reasons: "Not explained", decided_on: "2026-10-20", decided_by_name: "Natasha Khan", lapses_on: "2027-10-20" };
    const server = fakeServer({
      "GET /cases/": page([open]),
      "GET /cases/1/": { body: open },
      "GET /employees/": page(staff),
      "POST /cases/1/officers/": { body: { ...open, officers: [...open.officers, { id: 2, user: 11, name: "Kwame Adams", part: "Chair of the hearing", named_by_name: "Natasha Khan", named_at: "2026-10-02T10:00:00Z" }] } },
      "POST /cases/1/entries/": { body: withSteps },
      "POST /cases/1/decide/": [
        { status: 400, body: { code: "unfair", detail: "Before a dismissal, the employee is heard: record their response, or the hearing." } },
        { body: decided },
      ],
      "POST /cases/1/appeal/": { body: { ...decided, state: "appeal", state_name: "Under appeal", appeal_lodged_on: "2026-10-30", appeal_grounds: "I was sick" } },
      "POST /cases/1/appeal-decision/": { body: { ...decided, appeal_lodged_on: "2026-10-30", appeal_grounds: "I was sick", appeal_outcome_name: "Decision confirmed", appeal_decided_on: "2026-11-05", appeal_decided_by_name: "Hema Manager", appeal_reasons: "No sick note" } },
      "POST /cases/1/close/": { body: { ...decided, state: "closed", state_name: "Closed" } },
    });
    render(<CasesScreen me={person(["hr_officer"])} caseId={1} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "DC-2026-001: Asha Persaud" })).toBeInTheDocument();
    expect(screen.getByLabelText("Fair steps")).toHaveTextContent("The allegation is not yet put in writing. The employee has not yet been heard.");
    const user = userEvent.setup();

    const name = screen.getByRole("form", { name: "Name someone on the case" });
    const who = within(name).getByLabelText("Who");
    await within(name).findByRole("option", { name: "Kwame Adams" });
    expect(within(who).queryByRole("option", { name: "Asha Persaud" })).not.toBeInTheDocument(); // never on her own case
    expect(within(who).queryByRole("option", { name: "Natasha Khan" })).not.toBeInTheDocument(); // already named
    await user.selectOptions(who, "11");
    await user.type(within(name).getByLabelText("As"), "Chair of the hearing");
    await user.click(within(name).getByRole("button", { name: "Name someone on the case" }));
    expect(await screen.findByRole("list", { name: "Named on the case" })).toHaveTextContent("Kwame Adams, chair of the hearing");

    const step = screen.getByRole("form", { name: "Record a step" });
    await user.type(within(step).getByLabelText("On"), "2026-10-02");
    await user.type(within(step).getByLabelText("What happened"), "Letter of 2 October");
    await user.click(within(step).getByRole("button", { name: "Record a step" }));
    expect(await screen.findByRole("list", { name: "Steps" })).toHaveTextContent("Allegation put in writing, 02/10/2026");

    const decision = screen.getByRole("form", { name: "Record the decision" });
    await user.selectOptions(within(decision).getByLabelText("Outcome"), "dismissal");
    await user.type(within(decision).getByLabelText("Decided on"), "2026-10-20");
    await user.type(within(decision).getByLabelText("Reasons"), "Not explained");
    await user.click(within(decision).getByRole("button", { name: "Record the decision" }));
    expect(await within(decision).findByRole("alert")).toHaveTextContent("the employee is heard");
    await user.selectOptions(within(decision).getByLabelText("Outcome"), "written_warning");
    await user.click(within(decision).getByRole("button", { name: "Record the decision" }));
    expect(await screen.findByText(/It lapses on 20\/10\/2027/)).toBeInTheDocument();
    expect(server.calls.filter((c) => c.path === "/cases/1/decide/").at(-1)?.body).toEqual({
      outcome: "written_warning",
      reasons: "Not explained",
      decided_on: "2026-10-20",
    });

    const appeal = screen.getByRole("form", { name: "Record an appeal" });
    await user.type(within(appeal).getByLabelText("Lodged on"), "2026-10-30");
    await user.type(within(appeal).getByLabelText("Grounds"), "I was sick");
    await user.click(within(appeal).getByRole("button", { name: "Record an appeal" }));
    const heard = await screen.findByRole("form", { name: "Record the appeal decision" });
    await user.type(within(heard).getByLabelText("Heard on"), "2026-11-05");
    await user.type(within(heard).getByLabelText("Reasons"), "No sick note");
    await user.click(within(heard).getByRole("button", { name: "Record the appeal decision" }));
    expect(await screen.findByText(/Heard 05\/11\/2026 by Hema Manager: Decision confirmed/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close the case" }));
    expect(await screen.findByText("The case is closed.")).toBeInTheDocument();
  });

  it("offers no opening to those who cannot open cases, and says when a case is not theirs to see", async () => {
    fakeServer({
      "GET /cases/": page([]),
      "GET /cases/9/": { status: 404, body: { code: "not_found", detail: "Not found." } },
    });
    render(<CasesScreen me={person(["supervisor"])} caseId={9} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
    expect(screen.queryByRole("button", { name: "Open a case" })).not.toBeInTheDocument();
  });
});
