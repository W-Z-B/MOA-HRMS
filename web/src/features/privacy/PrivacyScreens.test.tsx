import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CorrectionRequest, OwnRecord, PrivacyNotice } from "../../api/types";
import { fakeServer, offline } from "../../test/fetch";
import { MyRecordScreen } from "./MyRecordScreen";
import { PrivacyNoticeScreen } from "./PrivacyNoticeScreen";

const notice: PrivacyNotice = {
  id: 1,
  version: 2,
  title: "How GSA uses your personal data",
  body: "GSA holds your staff record.\n\nYou may ask to see it.",
  created_at: "2026-09-30T09:00:00-04:00",
  published_at: "2026-10-01T09:00:00-04:00",
  published_by: "Hema Manager",
};
const record: OwnRecord = {
  produced_at: "2026-10-01T10:00:00-04:00",
  about: "What the GSA HRMS holds about you.",
  account: {
    username: "asha.persaud",
    name: "Asha Persaud",
    email: "asha.persaud@gsa.example",
    roles: [{ role: "Employee", where: "Mon Repos Campus", given: "2026-09-01T09:00:00-04:00", given_by: "Natasha Khan" }],
    last_sign_in: null,
    signed_in_on: [],
    privacy_notices_read: [],
  },
  staff_record: {
    personal: { employee_no: "E0001", first_name: "Asha", date_of_birth: "1990-03-14", nis_no: "A1234567", other_names: "" },
    appointments: [{ position: "Lecturer, Crop Science", start_date: "2019-09-02", acting: false }],
    contract_and_terms: { contract: { contract_type: "Open-ended", hours_per_week: "40.0" }, entitlements: [] },
    leave_balances: [],
    leave_requests: [],
    qualifications: [],
    work_before_gsa: [],
    dependants: [],
    emergency_contacts: [{ name: "Ravi Persaud", phone: "592-600-0001" }],
    bank_accounts: [{ bank: "Republic Bank (Guyana)", account_ending: "7890" }],
    documents: [],
    history_of_changes: [
      {
        at: "2026-10-01T09:30:00-04:00",
        actor: "Natasha Khan",
        action_name: "Changed",
        record: "Personal details",
        changes: [{ field: "Phone", before: "", after: "592-600-1234" }],
        reason: "New phone",
      },
    ],
  },
};
const answered: CorrectionRequest = {
  id: 7,
  employee: 1,
  employee_name: "Asha Persaud",
  employee_no: "E0001",
  subject: "personal",
  subject_name: "Personal details",
  wrong: "Date of birth",
  should_be: "14 March 1991",
  state: "declined",
  state_name: "Not changed",
  due_by: "2026-10-31",
  overdue: false,
  created_at: "2026-10-01T09:00:00-04:00",
  decided_by_name: "Natasha Khan",
  decided_at: "2026-10-01T11:00:00-04:00",
  decision_note: "The certificate on file says 1990.",
  is_mine: true,
};
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

describe("the privacy notice after sign-in", () => {
  it("shows the notice in paragraphs and records that it was read", async () => {
    const server = fakeServer({
      "GET /privacy/notice/": { body: { notice, acknowledged: false } },
      "POST /privacy/notice/acknowledge/": { body: { notice, acknowledged: true } },
    });
    const onAcknowledged = vi.fn();
    render(<PrivacyNoticeScreen onAcknowledged={onAcknowledged} onSignOut={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: notice.title })).toBeInTheDocument();
    expect(screen.getByText("GSA holds your staff record.")).toBeInTheDocument();
    expect(screen.getByText("You may ask to see it.")).toBeInTheDocument();
    expect(screen.getByText(/Version 2, in force from 01\/10\/2026/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "I have read this notice" }));
    expect(onAcknowledged).toHaveBeenCalled();
    expect(server.calls.at(-1)?.body).toEqual({ version: 2 });
  });

  it("moves straight on when there is nothing to read", async () => {
    fakeServer({ "GET /privacy/notice/": { body: { notice: null, acknowledged: false } } });
    const onAcknowledged = vi.fn();
    render(<PrivacyNoticeScreen onAcknowledged={onAcknowledged} onSignOut={vi.fn()} />);
    await vi.waitFor(() => expect(onAcknowledged).toHaveBeenCalled());
  });

  it("says when the notice changed meanwhile, and lets the person sign out", async () => {
    fakeServer({
      "GET /privacy/notice/": { body: { notice, acknowledged: false } },
      "POST /privacy/notice/acknowledge/": { status: 409, body: { code: "not_current", detail: "That is not the notice in force." } },
    });
    const onSignOut = vi.fn();
    render(<PrivacyNoticeScreen onAcknowledged={vi.fn()} onSignOut={onSignOut} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "I have read this notice" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That is not the notice in force.");
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalled();
  });

  it("says plainly when the server cannot be reached", async () => {
    fakeServer({ "GET /privacy/notice/": offline });
    render(<PrivacyNoticeScreen onAcknowledged={vi.fn()} onSignOut={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });
});

describe("my record", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const routes = (over: Record<string, unknown> = {}) =>
    fakeServer({
      "GET /privacy/my-record/": { body: record },
      "GET /privacy/notice/": { body: { notice, acknowledged: true } },
      "GET /privacy/corrections/": page([answered]),
      ...over,
    } as Parameters<typeof fakeServer>[0]);

  it("shows every part of the record in words", async () => {
    routes();
    render(<MyRecordScreen />);
    const personal = await screen.findByRole("region", { name: "Personal details" });
    expect(within(personal).getByText("NIS number").nextSibling).toHaveTextContent("A1234567");
    expect(within(personal).getByText("Date of birth").nextSibling).toHaveTextContent("14/03/1990");
    expect(within(personal).getByText("Other names").nextSibling).toHaveTextContent("—");
    const bank = screen.getByRole("region", { name: "Bank accounts" });
    expect(within(bank).getByText("7890")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Qualifications" })).toHaveTextContent("None on file.");
    const changes = screen.getByRole("region", { name: "Changes made to your record" });
    expect(changes).toHaveTextContent("Phone: — → 592-600-1234");
    expect(screen.getByRole("region", { name: "Contract and terms" })).toHaveTextContent("Contract type: Open-ended");
    expect(screen.getByRole("region", { name: "Your account" })).toHaveTextContent("Role: Employee, Where: Mon Repos Campus");
    expect(screen.getByRole("region", { name: "Appointments" })).toHaveTextContent("No");
  });

  it("downloads the record as a file and reads the notice again", async () => {
    routes();
    const createObjectURL = vi.fn(() => "blob:record");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<MyRecordScreen />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Download as a file" }));
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Read the privacy notice" }));
    expect(screen.getByRole("region", { name: "Privacy notice" })).toHaveTextContent("GSA holds your staff record.");
    click.mockRestore();
  });

  it("sends a correction request and lists the answers", async () => {
    const server = routes({
      "POST /privacy/corrections/": { status: 201, body: { ...answered, id: 8, state: "open", state_name: "With Human Resources" } },
    });
    render(<MyRecordScreen />);
    const answers = await screen.findByRole("list", { name: "Your correction requests" });
    expect(answers).toHaveTextContent("Not changed");
    expect(answers).toHaveTextContent("answered by Natasha Khan: The certificate on file says 1990.");
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("What is it about"), "contact");
    await user.type(screen.getByLabelText("What is wrong"), "My phone number is old");
    await user.type(screen.getByLabelText("What it should say"), "592-600-1234");
    await user.click(screen.getByRole("button", { name: "Send to Human Resources" }));
    expect(await screen.findByRole("status")).toHaveTextContent("They answer by 31/10/2026");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      subject: "contact",
      wrong: "My phone number is old",
      should_be: "592-600-1234",
    });
  });

  it("holds only the account for someone not on the staff, and says when the record cannot be loaded", async () => {
    routes({ "GET /privacy/my-record/": { body: { ...record, staff_record: null } } });
    const { unmount } = render(<MyRecordScreen />);
    expect(await screen.findByText(/not linked to a staff record/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Ask for a correction" })).not.toBeInTheDocument();
    unmount();

    routes({ "GET /privacy/my-record/": { status: 500, body: { code: "error", detail: "Server error." } } });
    render(<MyRecordScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});
