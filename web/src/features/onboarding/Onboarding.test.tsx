import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Hire, Me, Onboarding } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { MyOnboardingScreen } from "./MyOnboardingScreen";
import { OnboardingScreen } from "./OnboardingScreen";

const person = (roles: string[]): Me => ({
  id: 9,
  username: "hr.officer",
  name: "HR Officer",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

const hire: Hire = {
  id: 4,
  application: 4,
  vacancy: 2,
  vacancy_title: "Farm Hand",
  candidate: 4,
  candidate_name: "Keron Fraser",
  start_date: "2026-10-20",
  employee: null,
  notes: "",
};

const record: Onboarding = {
  id: 1,
  hire: 4,
  employee: 10,
  employee_name: "Keron Fraser",
  state: "in_progress",
  state_name: "In progress",
  started_on: "2026-10-10",
  completed_at: null,
  note: "",
  decision_comment: "",
  steps: [
    { id: 1, code: "documents", label: "Required documents collected", who: "HR", state: "open", state_name: "To do", note: "", cleared_at: null, cleared_by_name: null },
    { id: 2, code: "account", label: "Sign-in account opened", who: "HR", state: "open", state_name: "To do", note: "", cleared_at: null, cleared_by_name: null },
    { id: 3, code: "equipment", label: "Keys and equipment issued", who: "HR", state: "open", state_name: "To do", note: "", cleared_at: null, cleared_by_name: null },
    { id: 4, code: "induction", label: "Induction given", who: "The head of the unit", state: "open", state_name: "To do", note: "", cleared_at: null, cleared_by_name: null },
  ],
  allowed_actions: ["submit_documents", "complete", "cancel"],
  created_at: "2026-10-10T09:00:00Z",
};
const withEquipmentDone: Onboarding = {
  ...record,
  steps: record.steps.map((s) => (s.code === "equipment" ? { ...s, state: "done", state_name: "Done" } : s)),
};
const submitted: Onboarding = { ...record, state: "documents_submitted", state_name: "Documents submitted, awaiting HR", allowed_actions: ["confirm_documents", "send_back"] };
const withAccountDone: Onboarding = {
  ...record,
  steps: record.steps.map((s) => (s.code === "account" ? { ...s, state: "done", state_name: "Done" } : s)),
};

describe("onboarding (HR)", () => {
  it("starts onboarding from an accepted hire, and marks a step done", async () => {
    const server = fakeServer({
      "GET /onboarding/": [page([]), page([record]), page([withEquipmentDone])],
      "GET /recruitment/hires/": page([hire]),
      "POST /onboarding/start/": { status: 201, body: record },
      "POST /onboarding/1/steps/equipment/clear/": { body: withEquipmentDone },
    });
    render(<OnboardingScreen me={person(["hr_officer"])} onNavigate={vi.fn()} />);
    expect(await screen.findByText("Nobody is onboarding at the moment.")).toBeInTheDocument();
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Start onboarding" });
    await user.selectOptions(within(form).getByLabelText("Accepted hire"), "4");
    await user.type(within(form).getByLabelText("Employee number"), "E0777");
    await user.type(within(form).getByLabelText("Date of birth"), "1995-04-02");
    await user.click(within(form).getByRole("button", { name: "Start onboarding" }));
    expect(server.calls.find((c) => c.path === "/onboarding/start/")?.body).toEqual({
      hire: 4,
      employee_no: "E0777",
      date_of_birth: "1995-04-02",
      gender: "X",
      appointment_type: "permanent",
      start_date: expect.any(String),
    });
    expect(await screen.findByText("Onboarding started: the staff record and checklist are ready.")).toBeInTheDocument();
    const card = await screen.findByRole("article", { name: "Keron Fraser" });
    await user.click(within(card).getAllByRole("button", { name: "Mark done" })[0]);
    expect(server.calls.find((c) => c.path === "/onboarding/1/steps/equipment/clear/")?.body).toEqual({ done: true });
    expect(await within(card).findByText("Done")).toBeInTheDocument();
  });

  it("confirms documents once a new hire submits them, and opens the account", async () => {
    fakeServer({
      "GET /onboarding/": [page([submitted]), page([record]), page([withAccountDone])],
      "POST /onboarding/1/transition/": { body: record },
      "POST /onboarding/1/open-account/": { body: withAccountDone },
    });
    render(<OnboardingScreen me={person(["hr_officer"])} onNavigate={vi.fn()} />);
    const card = await screen.findByRole("article", { name: "Keron Fraser" });
    expect(within(card).getByText("Documents submitted, awaiting HR")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(within(card).getByRole("button", { name: "Confirm documents" }));
    expect(await within(card).findByText("In progress")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Open account" }));
    expect(await within(card).findByText("Done")).toBeInTheDocument();
  });
});

describe("onboarding (self-service)", () => {
  it("lets a new hire upload a document and submit it for review", async () => {
    const server = fakeServer({
      "GET /onboarding/": [page([record]), page([record]), page([submitted])],
      "POST /onboarding/1/documents/": { status: 201, body: record },
      "POST /onboarding/1/transition/": { body: submitted },
    });
    render(<MyOnboardingScreen />);
    expect(await screen.findByText("Required documents collected")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("What is it?"), "id_copy");
    await user.upload(screen.getByLabelText("File"), new File(["id"], "id.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Upload" }));
    const uploaded = (await vi.waitFor(() => {
      const call = server.calls.find((c) => c.path === "/onboarding/1/documents/");
      if (!call) throw new Error("not sent yet");
      return call;
    })).body as FormData;
    expect(uploaded.get("doc_type")).toBe("id_copy");
    await user.click(await screen.findByRole("button", { name: "I have uploaded everything asked for" }));
    expect(server.calls.find((c) => c.path === "/onboarding/1/transition/")?.body).toEqual({ action: "submit_documents" });
    expect(await screen.findByText("Submitted, waiting for Human Resources")).toBeInTheDocument();
  });

  it("says there is no onboarding in progress", async () => {
    fakeServer({ "GET /onboarding/": page([]) });
    render(<MyOnboardingScreen />);
    expect(await screen.findByText("You have no onboarding in progress.")).toBeInTheDocument();
  });
});
