import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee, LetterTemplate, Me, Separation, Settlement } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { LeavingSection } from "./LeavingSection";

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

const figures: Settlement = {
  last_day: "2026-12-31",
  grade: "GS GS5, step 1",
  monthly: "250000.00",
  weekly: "57692.31",
  daily: "11538.46",
  service_from: "2019-09-02",
  completed_years: 7,
  lines: [
    { key: "leave", label: "Annual leave not taken: 7.5 days", amount: "86538.46" },
    { key: "notice", label: "Pay in lieu of notice: 1 days short of one month", amount: "8241.76" },
    { key: "severance", label: "Severance: 9 weeks' wages for 7 completed years of service", amount: "519230.77" },
  ],
  total: "614010.99",
  notes: ["The statutory minimum on the basic salary."],
};
const leavingSoon: Separation = {
  id: 5,
  employee: 1,
  employee_name: "Asha Persaud",
  reason: "redundancy",
  reason_name: "Redundancy",
  state: "leaving",
  state_name: "Leaving",
  notice_given_on: "2026-12-01",
  last_day: "2026-12-31",
  note: "The unit is closing",
  completed_at: null,
  withdrawn_reason: "",
  notice: {
    needed: true,
    given_by: "school",
    given_on: "2026-12-01",
    rule: "one month, employed a year or more",
    full_notice_ends: "2027-01-01",
    short_by_days: 1,
  },
  settlement: figures,
  recorded_by: "Natasha Khan",
  created_at: "2026-10-01T10:00:00Z",
  letter_template: "certificate_of_service",
  letter_answers: { last_day: "2026-12-31" },
};
const left: Separation = {
  ...leavingSoon,
  id: 6,
  reason: "dismissal",
  reason_name: "Dismissal for good and sufficient cause",
  state: "left",
  state_name: "Left",
  notice: { needed: false, why: "No notice is needed when employment ends this way." },
  settlement: { lines: [], total: "0.00", notes: ["The statutory minimum on the basic salary."] },
};
const withdrawn: Separation = {
  ...leavingSoon,
  id: 4,
  reason: "resignation",
  reason_name: "Resignation",
  state: "withdrawn",
  state_name: "Withdrawn",
  last_day: "2026-08-31",
  withdrawn_reason: "Resignation taken back",
};
const certificate = {
  id: 33,
  code: "certificate_of_service",
  name: "Certificate of service",
  is_active: true,
  asks: [{ key: "last_day", label: "Last day of service", type: "date" }],
} as LetterTemplate;

describe("leaving", () => {
  it("checks the notice and the figures before HR records a resignation", async () => {
    const server = fakeServer({
      "GET /separations/": [page([withdrawn]), page([withdrawn, { ...leavingSoon, reason: "resignation", reason_name: "Resignation" }])],
      "POST /separations/preview/": {
        body: {
          notice: { needed: true, given_by: "employee", given_on: "2026-10-01", rule: "one month, employed a year or more", short_by_days: 17 },
          settlement: { ...figures, lines: figures.lines.slice(0, 1), total: "86538.46" },
        },
      },
      "POST /separations/": { status: 201, body: { ...leavingSoon, reason: "resignation" } },
    });
    const onChanged = vi.fn();
    render(<LeavingSection employee={asha} me={person(["hr_officer"])} onChanged={onChanged} />);
    expect(await screen.findByText("No leaving is recorded.")).toBeInTheDocument();
    expect(screen.getByText(/Withdrawn before: resignation for 31\/08\/2026 \(Resignation taken back\)/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Record leaving" }));
    const form = screen.getByRole("form", { name: "Record leaving" });
    await user.type(within(form).getByLabelText("Notice given on"), "2026-10-01");
    await user.type(within(form).getByLabelText("Last day"), "2026-10-15");
    await user.type(within(form).getByLabelText("In words"), "Taking up a post abroad");
    await user.click(within(form).getByRole("button", { name: "Check the notice and the figures" }));
    const check = await within(form).findByLabelText("The check");
    expect(check).toHaveTextContent(
      "Notice given by the employee on 01/10/2026; one month, employed a year or more is asked for. The last day leaves it 17 days short.",
    );
    expect(within(check).getByRole("table", { name: "Owed on leaving" })).toHaveTextContent("G$86,538.46");
    await user.click(within(check).getByRole("button", { name: "Record leaving" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Recorded: leaving on 31/12/2026.");
    expect(server.calls.find((c) => c.path === "/separations/")?.body).toEqual({
      employee: 1,
      reason: "resignation",
      last_day: "2026-10-15",
      note: "Taking up a post abroad",
      notice_given_on: "2026-10-01",
    });
    expect(onChanged).toHaveBeenCalled();
  });

  it("shows a leaving on its way with what is owed, and withdraws it", async () => {
    const server = fakeServer({
      "GET /separations/": [page([leavingSoon]), page([{ ...leavingSoon, state: "withdrawn", state_name: "Withdrawn", withdrawn_reason: "Unit kept open" }])],
      "POST /separations/5/withdraw/": { body: { ...leavingSoon, state: "withdrawn" } },
    });
    render(<LeavingSection employee={asha} me={person(["hr_manager"])} onChanged={vi.fn()} />);
    expect(await screen.findByText("Leaving on 31/12/2026")).toBeInTheDocument();
    expect(screen.getByText(/The last day leaves it 1 day short: the days short are paid in lieu\./)).toBeInTheDocument();
    const owed = screen.getByRole("table", { name: "Owed on leaving" });
    expect(within(owed).getByText("G$519,230.77")).toBeInTheDocument();
    expect(within(owed).getByText("G$614,010.99")).toBeInTheDocument();
    expect(screen.getByText(/On G\$250,000.00 a month \(GS GS5, step 1\), 7 completed years of service from 02\/09\/2019/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Withdraw the leaving" }));
    const form = screen.getByRole("form", { name: "Withdraw the leaving" });
    await user.type(within(form).getByLabelText("Why withdraw it"), "Unit kept open");
    await user.click(within(form).getByRole("button", { name: "Withdraw the leaving" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The leaving is withdrawn.");
    expect(server.calls.find((c) => c.path === "/separations/5/withdraw/")?.body).toEqual({ reason: "Unit kept open" });
  });

  it("writes the certificate of service for someone who has left", async () => {
    const server = fakeServer({
      "GET /separations/": page([left]),
      "GET /letters/templates/": page([certificate]),
      "POST /letters/preview/": {
        body: { subject: "Certificate of service: Asha Persaud", addressed: false, blocks: [], values: {}, missing: [], classification: "internal" },
      },
      "POST /letters/": { status: 201, body: { id: 61, reference: "GSA/HR/2026/0010", template_name: "Certificate of service", download_url: "/api/v1/letters/61/download/" } },
    });
    render(<LeavingSection employee={{ ...asha, status: "separated" }} me={person(["hr_officer"])} onChanged={vi.fn()} />);
    expect(await screen.findByText("Left on 31/12/2026")).toBeInTheDocument();
    expect(screen.getByText("No notice is needed when employment ends this way.")).toBeInTheDocument();
    expect(screen.getByText("Nothing is owed beyond the last pay.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw the leaving" })).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Write the certificate of service" }));
    expect(await screen.findByLabelText("Last day of service")).toHaveValue("2026-12-31");
    await user.click(screen.getByRole("button", { name: "Read the letter" }));
    await user.click(await screen.findByRole("button", { name: "Issue the letter" }));
    expect(await screen.findByText(/GSA\/HR\/2026\/0010 is issued/)).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/letters/")?.body).toEqual({
      employee: 1,
      template: 33,
      answers: { last_day: "2026-12-31" },
    });
  });

  it("shows the Principal the leaving without actions, and nothing at all to a supervisor", async () => {
    fakeServer({ "GET /separations/": page([leavingSoon]) });
    const { unmount } = render(<LeavingSection employee={asha} me={person(["principal"])} onChanged={vi.fn()} />);
    expect(await screen.findByText("Leaving on 31/12/2026")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw the leaving" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record leaving" })).not.toBeInTheDocument();
    unmount();
    const { container } = render(<LeavingSection employee={asha} me={person(["supervisor"])} onChanged={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
