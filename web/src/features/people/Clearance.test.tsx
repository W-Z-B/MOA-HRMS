import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Clearance, ClearanceStep, Employee, ExitInterview, IssuedItem, Me, Separation } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ClearancePanel } from "./ClearancePanel";
import { ItemsTab } from "./ItemsTab";

const person = (roles: string[]): Me => ({
  id: 3,
  username: "someone",
  name: "Someone",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const asha = { id: 1, campus: 1, first_name: "Asha", full_name: "Asha Persaud", status: "active" } as Employee;

const boots: IssuedItem = {
  id: 7,
  employee: 1,
  kind: "protective",
  kind_name: "Protective clothing or gear",
  description: "Rubber boots",
  tag: "",
  issued_on: "2026-01-12",
  returned_on: null,
  condition: "",
  condition_name: "",
  note: "",
  issued_by: "Kwame Adams",
};
const laptop: IssuedItem = {
  ...boots,
  id: 8,
  kind: "device",
  kind_name: "Computer, phone or other device",
  description: "Laptop",
  tag: "GSA-IT-0042",
  returned_on: "2026-09-30",
  condition: "worn",
  condition_name: "Worn with use",
};

describe("items issued", () => {
  it("lists what is still out first, issues an item and records one given back", async () => {
    const server = fakeServer({
      "GET /issued-items/": page([boots, laptop]),
      "POST /issued-items/": { status: 201, body: { ...boots, id: 9, description: "Key to the store" } },
      "POST /issued-items/7/return/": { body: { ...boots, returned_on: "2026-10-01", condition: "lost", condition_name: "Lost" } },
    });
    render(<ItemsTab employee={asha} me={person(["supervisor"])} />);
    const list = await screen.findByRole("list", { name: "Items issued" });
    expect(within(list).getByText("Still out")).toBeInTheDocument();
    expect(within(list).getByText(/GSA-IT-0042 · issued 12\/01\/2026 by Kwame Adams · given back 30\/09\/2026, worn with use/)).toBeInTheDocument();
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Issue an item" });
    await user.selectOptions(within(form).getByLabelText("Kind"), "key");
    await user.type(within(form).getByLabelText("What it is"), "Key to the store");
    await user.type(within(form).getByLabelText("Issued on"), "2026-10-01");
    await user.click(within(form).getByRole("button", { name: "Issue the item" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Key to the store issued.");
    expect(server.calls.find((c) => c.path === "/issued-items/" && c.method === "POST")?.body).toEqual({
      employee: 1,
      kind: "key",
      description: "Key to the store",
      tag: "",
      issued_on: "2026-10-01",
    });

    await user.click(screen.getByRole("button", { name: "Record Rubber boots as given back" }));
    const back = screen.getByRole("form", { name: "Given back: Rubber boots" });
    await user.type(within(back).getByLabelText("Given back on"), "2026-10-01");
    await user.selectOptions(within(back).getByLabelText("In what condition"), "lost");
    await user.click(within(back).getByRole("button", { name: "Record it" }));
    expect(await screen.findByText("Rubber boots: lost, recorded.")).toBeInTheDocument();
  });

  it("lets readers see the register without changing it, and says when nothing was issued", async () => {
    fakeServer({ "GET /issued-items/": page([]) });
    render(<ItemsTab employee={asha} me={person(["auditor"])} />);
    expect(await screen.findByText("Nothing has been issued.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Issue an item" })).not.toBeInTheDocument();
  });
});

const step = (code: string, label: string, state: ClearanceStep["state"] = "open"): ClearanceStep => ({
  id: code.length,
  code,
  label,
  who: "HR",
  state,
  state_name: state === "open" ? "To do" : state === "done" ? "Done" : "Not needed",
  note: state === "open" ? "" : "Confirmed by Kwame Adams",
  cleared_at: state === "open" ? null : "2026-10-01T14:00:00Z",
  cleared_by_name: state === "open" ? null : "Natasha Khan",
});
const steps = [
  step("items", "Everything issued given back"),
  step("handover", "Work handed over"),
  step("money", "Money owed to the School settled", "not_needed"),
  step("interview", "Exit interview offered"),
  step("account", "Sign-in account switched off"),
];
const separation = { id: 5, state: "leaving" } as Separation;

describe("clearance", () => {
  it("holds the items step while anything is out, closes a step with a note, and records the interview", async () => {
    const saved: ExitInterview = {
      held_on: "2026-10-01",
      declined: false,
      main_reason: "pay",
      main_reason_name: "Pay and benefits",
      would_recommend: "yes",
      would_recommend_name: "Yes",
      rating_pay: 2,
      rating_supervision: 4,
      rating_training: null,
      rating_workload: null,
      rating_conditions: null,
      keep: "The farm work",
      change: "Pay on time",
    };
    const server = fakeServer({
      "GET /separations/5/clearance/": [
        { body: { steps, outstanding_items: [boots] } satisfies Clearance },
        { body: { steps: steps.map((s) => (s.code === "interview" ? step("interview", s.label, "done") : s)), outstanding_items: [boots] } },
      ],
      "GET /separations/5/exit-interview/": [{ status: 404, body: { code: "not_found", detail: "No exit interview is recorded." } }, { body: saved }],
      "POST /separations/5/clearance/handover/": {
        body: { steps: steps.map((s) => (s.code === "handover" ? step("handover", s.label, "done") : s)), outstanding_items: [boots] },
      },
      "POST /separations/5/exit-interview/": { body: saved },
    });
    const onChanged = vi.fn();
    render(<ClearancePanel separation={separation} me={person(["hr_officer"])} onChanged={onChanged} />);
    expect(await screen.findByText("Clearance: 1 of 5 steps closed")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Clearance steps" });
    expect(within(list).getByRole("list", { name: "Still out" })).toHaveTextContent("Rubber boots, issued 12/01/2026");
    expect(within(list).getByText("Record each item given back, or lost, under Items issued.")).toBeInTheDocument();
    expect(within(list).getByText(/Natasha Khan, .*: Confirmed by Kwame Adams/)).toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: "Close the step: Sign-in account switched off" })).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(within(list).getByRole("button", { name: "Close the step: Work handed over" }));
    await user.type(screen.getByLabelText(/Note \(who confirmed it/), "Confirmed by Kwame Adams");
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Clearance: 2 of 5 steps closed")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/separations/5/clearance/handover/")?.body).toEqual({ done: true, note: "Confirmed by Kwame Adams" });
    expect(onChanged).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Record the exit interview" }));
    const form = screen.getByRole("form", { name: "Exit interview" });
    await user.type(within(form).getByLabelText("Held, or offered, on"), "2026-10-01");
    await user.selectOptions(within(form).getByLabelText("The main reason for leaving"), "pay");
    await user.selectOptions(within(form).getByLabelText(/Would they recommend/), "yes");
    await user.selectOptions(within(form).getByLabelText(/Pay and benefits, from 1/), "2");
    await user.selectOptions(within(form).getByLabelText(/Supervision, from 1/), "4");
    await user.type(within(form).getByLabelText("What the School should keep"), "The farm work");
    await user.type(within(form).getByLabelText("What the School should change"), "Pay on time");
    await user.click(within(form).getByRole("button", { name: "Save the exit interview" }));
    expect(await screen.findByText("Pay and benefits 2, Supervision 4")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/separations/5/exit-interview/" && c.method === "POST")?.body).toMatchObject({
      main_reason: "pay",
      would_recommend: "yes",
      rating_pay: 2,
      rating_supervision: 4,
      rating_training: null,
      keep: "The farm work",
    });
  });

  it("records a declined interview, and shows the Principal the clearance without actions", async () => {
    fakeServer({
      "GET /separations/5/clearance/": { body: { steps, outstanding_items: [] } },
      "GET /separations/5/exit-interview/": [
        { status: 404, body: { code: "not_found", detail: "None" } },
        { body: { held_on: "2026-10-01", declined: true } },
      ],
      "POST /separations/5/exit-interview/": { body: { held_on: "2026-10-01", declined: true } },
    });
    const { unmount } = render(<ClearancePanel separation={separation} me={person(["hr_manager"])} onChanged={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Record the exit interview" }));
    const form = screen.getByRole("form", { name: "Exit interview" });
    await user.type(within(form).getByLabelText("Held, or offered, on"), "2026-10-01");
    await user.click(within(form).getByLabelText("Offered, and declined"));
    expect(within(form).queryByLabelText("The main reason for leaving")).not.toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Save the exit interview" }));
    expect(await screen.findByText("Exit interview offered on 01/10/2026, and declined.")).toBeInTheDocument();
    unmount();

    render(<ClearancePanel separation={separation} me={person(["principal"])} onChanged={vi.fn()} />);
    expect(await screen.findByText("Clearance: 1 of 5 steps closed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Close the step/ })).not.toBeInTheDocument();
    expect(await screen.findByText("Exit interview offered on 01/10/2026, and declined.")).toBeInTheDocument();
  });
});
