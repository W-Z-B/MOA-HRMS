import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Appraisal, AppraisalCycle, Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { PerformanceScreen } from "./PerformanceScreen";

const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const person = (roles: string[]): Me => ({
  id: 3,
  username: "asha.persaud",
  name: "Asha Persaud",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: 1,
});

const cycle: AppraisalCycle = { id: 1, name: "Annual appraisal", year: 2026, starts: "2026-01-01", ends: "2026-12-31", is_open: true };

const draft: Appraisal = {
  id: 7,
  employee: 1,
  employee_name: "Asha Persaud",
  manager: 2,
  manager_name: "Natasha Khan",
  cycle: 1,
  cycle_name: "Annual appraisal 2026",
  kind: "annual",
  kind_name: "Annual appraisal",
  state: "draft",
  state_name: "Draft",
  decision_comment: "",
  self_assessment: "",
  self_assessed_at: null,
  manager_assessment: "",
  overall_rating: null,
  rated_at: null,
  signed_at: null,
  outcome: "",
  is_mine: true,
  is_rated_by_me: false,
  goals: [{ id: 1, employee: 1, cycle: 1, title: "Finish the farm survey", description: "", weight: 100, status: "in_progress", status_name: "In progress", position: 0 }],
  allowed_actions: [],
  created_at: "2026-01-02T09:00:00Z",
};

describe("performance (self-service)", () => {
  it("lets an employee write and submit their self-assessment", async () => {
    const withText: Appraisal = { ...draft, self_assessment: "I met my targets.", allowed_actions: ["submit_self_assessment"] };
    const submitted: Appraisal = { ...withText, state: "self_assessed", allowed_actions: [] };
    const server = fakeServer({
      "GET /performance/appraisals/": [page([draft]), page([withText]), page([submitted])],
      "GET /performance/cycles/": page([cycle]),
      "PATCH /performance/appraisals/7/self-assessment/": { body: withText },
      "POST /performance/appraisals/7/transition/": { body: submitted },
    });
    render(<PerformanceScreen me={person(["employee"])} path="/appraisals" onNavigate={vi.fn()} />);
    expect(await screen.findByText("Finish the farm survey")).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "Asha Persaud" });
    const user = userEvent.setup();
    await user.type(within(card).getByLabelText("Self-assessment"), "I met my targets.");
    await user.click(within(card).getByRole("button", { name: "Save" }));
    expect(server.calls.find((c) => c.path === "/performance/appraisals/7/self-assessment/")?.body).toEqual({
      self_assessment: "I met my targets.",
    });
    await user.click(await within(card).findByRole("button", { name: "Submit self-assessment" }));
    expect(server.calls.find((c) => c.path === "/performance/appraisals/7/transition/")?.body).toEqual({
      action: "submit_self_assessment",
      comment: undefined,
    });
    expect(await within(card).findByText("Self-assessment done")).toBeInTheDocument();
  });

  it("says there is nothing open when no appraisal is mine", async () => {
    fakeServer({ "GET /performance/appraisals/": page([]), "GET /performance/cycles/": page([]) });
    render(<PerformanceScreen me={person(["employee"])} path="/appraisals" onNavigate={vi.fn()} />);
    expect(await screen.findByText("No appraisal is open for you.")).toBeInTheDocument();
  });
});

describe("performance (manager and HR)", () => {
  it("lets a manager rate a self-assessed appraisal", async () => {
    const theirs: Appraisal = { ...draft, is_mine: false, is_rated_by_me: true, state: "self_assessed", self_assessment: "Busy year.", allowed_actions: [] };
    const rated: Appraisal = { ...theirs, manager_assessment: "Strong work.", overall_rating: 5, state: "rated" };
    const server = fakeServer({
      "GET /performance/appraisals/": [page([theirs]), page([rated]), page([rated])],
      "GET /performance/cycles/": page([cycle]),
      "PATCH /performance/appraisals/7/manager-assessment/": { body: rated },
      "POST /performance/appraisals/7/transition/": { body: rated },
    });
    render(<PerformanceScreen me={person(["supervisor"])} path="/appraisals?tab=team" onNavigate={vi.fn()} />);
    const card = await screen.findByRole("article", { name: "Asha Persaud" });
    const user = userEvent.setup();
    await user.type(within(card).getByLabelText("Manager's assessment"), "Strong work.");
    await user.click(within(card).getByRole("button", { name: "Save" }));
    expect(server.calls.find((c) => c.path === "/performance/appraisals/7/manager-assessment/")?.body).toEqual({
      manager_assessment: "Strong work.",
      overall_rating: 3,
      outcome: "",
    });
  });

  it("lets HR open a cycle and start an appraisal", async () => {
    const server = fakeServer({
      "GET /performance/appraisals/": page([]),
      "GET /performance/cycles/": [page([]), page([cycle])],
      "POST /performance/cycles/": { status: 201, body: cycle },
    });
    render(<PerformanceScreen me={person(["hr_officer"])} path="/appraisals?tab=setup" onNavigate={vi.fn()} />);
    const form = await screen.findByRole("form", { name: "Open a cycle" });
    const user = userEvent.setup();
    await user.click(within(form).getByRole("button", { name: "Open cycle" }));
    expect(server.calls.find((c) => c.method === "POST" && c.path === "/performance/cycles/")?.body).toMatchObject({
      name: "Annual appraisal",
    });
  });
});
