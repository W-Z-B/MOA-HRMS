import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CareerEvent, Employee, LetterTemplate, Me, Position } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { CareerSection } from "./CareerSection";

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
const asha = { id: 1, campus: 1, first_name: "Asha", full_name: "Asha Persaud" } as Employee;

const base: CareerEvent = {
  id: 1,
  employee: 1,
  kind: "transfer",
  kind_name: "Transfer",
  state: "applied",
  state_name: "In effect",
  effective_date: "2026-10-01",
  end_date: null,
  from_post: "LIV-001 Livestock Instructor",
  to_position: 12,
  to_post: "LIV-002 Farm Hand",
  from_grade_name: "GS GS5, step 1",
  to_grade_name: "GS GS5, step 1",
  reason: "Needs of the unit",
  problem: "",
  applied_at: "2026-10-01T10:00:00Z",
  recorded_by: "Natasha Khan",
  created_at: "2026-10-01T10:00:00Z",
  letter_template: "transfer",
  letter_answers: { previous_post: "Livestock Instructor", new_post: "Farm Hand", effective_date: "2026-10-01" },
  letters: [],
};
const increment: CareerEvent = {
  ...base,
  id: 2,
  kind: "increment",
  kind_name: "Increment",
  state: "scheduled",
  state_name: "Scheduled",
  effective_date: "2027-01-01",
  to_grade_name: "GS GS5, step 2",
  letter_template: "increment",
};
const acting: CareerEvent = {
  ...base,
  id: 3,
  kind: "acting",
  kind_name: "Acting appointment",
  state: "blocked",
  state_name: "Held up",
  to_post: "LIV-003 Senior Instructor",
  problem: "Someone already acts in post LIV-003.",
  letter_template: "acting",
  letters: [{ id: 50, reference: "GSA/HR/2026/0007", download_url: "/api/v1/letters/50/download/" }],
};
const confirmation: CareerEvent = {
  ...base,
  id: 4,
  kind: "confirmation",
  kind_name: "Confirmation in the post",
  state: "cancelled",
  state_name: "Cancelled",
  letter_template: "confirmation",
};
const vacant = { id: 12, number: "LIV-002", title: "Farm Hand", grade_name: "GS GS5, step 1", is_vacant: true } as Position;
const filled = { id: 13, number: "LIV-003", title: "Senior Instructor", grade_name: "GS GS7, step 1", is_vacant: false } as Position;
const transferTemplate = {
  id: 30,
  code: "transfer",
  name: "Transfer",
  is_active: true,
  asks: [
    { key: "previous_post", label: "The post held until now", type: "text" },
    { key: "new_post", label: "The new post", type: "text" },
    { key: "effective_date", label: "Takes effect on", type: "date" },
  ],
} as LetterTemplate;

describe("career changes", () => {
  it("tells each change in words, with its state, and records a transfer for a later day", async () => {
    const server = fakeServer({
      "GET /career-events/": page([base, increment, acting, confirmation]),
      "GET /org/positions/": page([vacant, filled]),
      "POST /career-events/": { status: 201, body: { ...base, id: 9, state: "scheduled", state_name: "Scheduled", effective_date: "2026-11-01" } },
    });
    const onChanged = vi.fn();
    render(<CareerSection employee={asha} me={person(["hr_officer"])} onChanged={onChanged} />);
    const list = await screen.findByRole("list", { name: "Career changes" });
    expect(within(list).getByText("From LIV-001 Livestock Instructor to LIV-002 Farm Hand, from 01/10/2026")).toBeInTheDocument();
    expect(within(list).getByText("From GS GS5, step 1 to GS GS5, step 2, from 01/01/2027")).toBeInTheDocument();
    expect(within(list).getByText("Acting in LIV-003 Senior Instructor from 01/10/2026, until further notice")).toBeInTheDocument();
    expect(within(list).getByText("Someone already acts in post LIV-003.")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "GSA/HR/2026/0007" })).toHaveAttribute("href", "/api/v1/letters/50/download/");
    expect(within(list).getByText("Confirmed in LIV-001 Livestock Instructor from 01/10/2026")).toBeInTheDocument();
    expect(within(list).getAllByRole("button", { name: "Cancel this change" })).toHaveLength(2); // scheduled and held up

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Record a change" }));
    const form = screen.getByRole("form", { name: "Record a change" });
    await user.selectOptions(within(form).getByLabelText("To the post"), "12");
    expect(within(form).getByRole("option", { name: /LIV-003 Senior Instructor .*filled/ })).toBeDisabled();
    await user.type(within(form).getByLabelText("Takes effect on"), "2026-11-01");
    await user.type(within(form).getByLabelText("Why"), "Needs of the unit");
    await user.click(within(form).getByRole("button", { name: "Record the change" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Transfer recorded: it takes effect on 01/11/2026.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      employee: 1,
      kind: "transfer",
      effective_date: "2026-11-01",
      reason: "Needs of the unit",
      to_position: 12,
    });
    expect(onChanged).toHaveBeenCalled();
  });

  it("lets a filled post be acted in, with or without an end, and says why a change is refused", async () => {
    const server = fakeServer({
      "GET /career-events/": page([]),
      "GET /org/positions/": page([vacant, filled]),
      "POST /career-events/": { status: 409, body: { code: "acting_taken", detail: "Someone already acts in post LIV-003 for part of that time." } },
    });
    render(<CareerSection employee={asha} me={person(["hr_manager"])} onChanged={vi.fn()} />);
    expect(await screen.findByText("No changes recorded.")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Record a change" }));
    const form = screen.getByRole("form", { name: "Record a change" });
    await user.selectOptions(within(form).getByLabelText("Change"), "acting");
    await user.selectOptions(within(form).getByLabelText("Post acted in"), "13");
    await user.type(within(form).getByLabelText("Acting from"), "2026-10-05");
    await user.type(within(form).getByLabelText(/Acting until/), "2026-12-31");
    await user.type(within(form).getByLabelText("Why"), "Cover while the holder studies");
    await user.click(within(form).getByRole("button", { name: "Record the change" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Someone already acts in post LIV-003");
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({ kind: "acting", to_position: 13, end_date: "2026-12-31" });
    await user.selectOptions(within(form).getByLabelText("Change"), "increment");
    expect(within(form).queryByLabelText("To the post")).not.toBeInTheDocument(); // an increment names no post
    await user.click(within(form).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Record a change" })).toBeInTheDocument();
  });

  it("writes a change's letter with the change's answers, and cancels a scheduled change", async () => {
    const server = fakeServer({
      "GET /career-events/": page([base, increment]),
      "GET /letters/templates/": page([transferTemplate]),
      "POST /letters/preview/": {
        body: { subject: "Transfer to the post of Farm Hand", addressed: true, blocks: [], values: { full_name: "Asha Persaud" }, missing: [], classification: "confidential" },
      },
      "POST /letters/": { status: 201, body: { id: 51, reference: "GSA/HR/2026/0008", template_name: "Transfer", download_url: "/api/v1/letters/51/download/" } },
      "POST /career-events/2/cancel/": { body: { ...increment, state: "cancelled" } },
    });
    render(<CareerSection employee={asha} me={person(["hr_officer"])} onChanged={vi.fn()} />);
    const user = userEvent.setup();
    const [transfer] = await screen.findAllByRole("button", { name: "Write the letter" });
    await user.click(transfer);
    expect(await screen.findByRole("heading", { name: "Write the letter for the transfer" })).toBeInTheDocument();
    expect(await screen.findByLabelText("The new post")).toHaveValue("Farm Hand");
    expect(screen.getByLabelText("Takes effect on")).toHaveValue("2026-10-01");
    await user.click(screen.getByRole("button", { name: "Read the letter" }));
    await user.click(await screen.findByRole("button", { name: "Issue the letter" }));
    expect(await screen.findByText(/GSA\/HR\/2026\/0008 is issued/)).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/letters/")?.body).toEqual({
      employee: 1,
      template: 30,
      answers: { previous_post: "Livestock Instructor", new_post: "Farm Hand", effective_date: "2026-10-01" },
      career_event: 1,
    });
    await user.click(screen.getByRole("button", { name: "Close" }));

    await user.click(screen.getByRole("button", { name: "Cancel this change" }));
    const cancel = screen.getByRole("form", { name: "Cancel the increment" });
    await user.type(within(cancel).getByLabelText("Why cancel it"), "Put back to next year");
    await user.click(within(cancel).getByRole("button", { name: "Cancel the change" }));
    expect(await screen.findByText("Increment cancelled.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/career-events/2/cancel/")?.body).toEqual({ reason: "Put back to next year" });
  });

  it("says when no template is in use for a change's letter, and shows readers no actions", async () => {
    fakeServer({ "GET /career-events/": page([base]), "GET /letters/templates/": page([]) });
    const { unmount } = render(<CareerSection employee={asha} me={person(["hr_officer"])} onChanged={vi.fn()} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Write the letter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No letter template is in use for the transfer.");
    unmount();

    render(<CareerSection employee={asha} me={person(["supervisor"])} onChanged={vi.fn()} />);
    expect(await screen.findByRole("list", { name: "Career changes" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Write the letter" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record a change" })).not.toBeInTheDocument();
  });
});
