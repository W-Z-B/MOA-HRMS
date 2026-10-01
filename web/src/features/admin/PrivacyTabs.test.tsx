import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CorrectionRequest, Me, PrivacyNotice } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { CorrectionsTab } from "./CorrectionsTab";
import { NoticeTab } from "./NoticeTab";

const person = (roles: string[]): Me => ({
  id: 5,
  username: "hr.manager",
  name: "Hema Manager",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const open: CorrectionRequest = {
  id: 7,
  employee: 1,
  employee_name: "Asha Persaud",
  employee_no: "E0001",
  subject: "contact",
  subject_name: "Contact details",
  wrong: "Old phone",
  should_be: "592-600-1234",
  state: "open",
  state_name: "With Human Resources",
  due_by: "2026-10-31",
  overdue: false,
  created_at: "2026-10-01T09:00:00-04:00",
  decided_by_name: null,
  decided_at: null,
  decision_note: "",
  is_mine: false,
};
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const draft: PrivacyNotice = {
  id: 3,
  version: 3,
  title: "How GSA uses your data",
  body: "First paragraph.\n\nSecond paragraph.",
  created_at: "2026-10-01T09:00:00-04:00",
  published_at: null,
  published_by: null,
};
const inForce: PrivacyNotice = { ...draft, id: 2, version: 2, published_at: "2026-09-01T09:00:00-04:00", published_by: "Hema Manager" };

describe("correction requests", () => {
  it("answers a request: corrected straight away, or not changed with the reason", async () => {
    const devonsRequest = { ...open, id: 8, employee_name: "Devon Charles" };
    const server = fakeServer({
      "GET /privacy/corrections/?state=open": [page([open, devonsRequest]), page([devonsRequest]), page([])],
      "POST /privacy/corrections/7/decide/": { body: { ...open, state: "corrected" } },
      "POST /privacy/corrections/8/decide/": { body: { ...open, id: 8, state: "declined" } },
    });
    render(<CorrectionsTab onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Correction requests" });
    const [asha] = within(list).getAllByRole("listitem");
    expect(asha).toHaveTextContent("answer due by 31/10/2026");
    await user.click(within(asha).getByRole("button", { name: "Corrected" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha Persaud is told the record has been corrected.");
    expect(server.calls.find((c) => c.path === "/privacy/corrections/7/decide/")?.body).toEqual({ outcome: "corrected", note: "" });

    await vi.waitFor(() => expect(screen.queryByText("Asha Persaud")).not.toBeInTheDocument());
    const devon = within(screen.getByRole("list", { name: "Correction requests" })).getAllByRole("listitem")[0];
    const notChanged = within(devon).getByRole("button", { name: "Not changed" });
    expect(notChanged).toBeDisabled();
    await user.type(within(devon).getByLabelText("Answer to Devon Charles"), "The record is right");
    await user.click(notChanged);
    expect(server.calls.find((c) => c.path === "/privacy/corrections/8/decide/")?.body).toEqual({
      outcome: "declined",
      note: "The record is right",
    });
  });

  it("leaves a request about oneself to someone else, flags late ones, and opens the record", async () => {
    fakeServer({
      "GET /privacy/corrections/?state=open": page([
        { ...open, is_mine: true },
        { ...open, id: 9, employee: 4, employee_name: "Late Answer", overdue: true },
      ]),
    });
    const onNavigate = vi.fn();
    render(<CorrectionsTab onNavigate={onNavigate} />);
    const [mine, late] = within(await screen.findByRole("list", { name: "Correction requests" })).getAllByRole("listitem");
    expect(mine).toHaveTextContent("someone else in Human Resources answers it");
    expect(within(mine).queryByRole("button")).not.toBeInTheDocument();
    expect(late).toHaveTextContent("(overdue)");
    await userEvent.setup().click(within(late).getByRole("link", { name: "Open the record" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/4");
  });

  it("shows answered requests, and says when there are none", async () => {
    const server = fakeServer({
      "GET /privacy/corrections/?state=open": page([]),
      "GET /privacy/corrections/?state=declined": page([
        { ...open, state: "declined", state_name: "Not changed", decided_by_name: "Natasha Khan", decision_note: "Right as it is" },
      ]),
    });
    render(<CorrectionsTab onNavigate={vi.fn()} />);
    expect(await screen.findByText("No requests here.")).toBeInTheDocument();
    await userEvent.setup().selectOptions(screen.getByLabelText("Show"), "declined");
    expect(await screen.findByText(/answered by Natasha Khan: Right as it is/)).toBeInTheDocument();
    expect(server.calls.at(-1)?.path).toBe("/privacy/corrections/?state=declined");
  });
});

describe("the privacy notice", () => {
  it("writes a draft, then publishes it", async () => {
    const server = fakeServer({
      "GET /privacy/notices/": [page([inForce]), page([draft, inForce]), page([{ ...draft, published_at: "2026-10-01T12:00:00-04:00" }, inForce])],
      "POST /privacy/notices/": { status: 201, body: draft },
      "POST /privacy/notices/3/publish/": { body: { ...draft, published_at: "2026-10-01T12:00:00-04:00" } },
    });
    render(<NoticeTab me={person(["hr_manager"])} />);
    const user = userEvent.setup();
    expect(await screen.findByText("In force")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Write a new version" }));
    await user.type(screen.getByLabelText("Title"), draft.title);
    await user.type(screen.getByLabelText("Text (a blank line starts a new paragraph)"), "First paragraph.");
    await user.click(screen.getByRole("button", { name: "Save the draft" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Draft saved.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ title: draft.title, body: "First paragraph." });

    await user.click(await screen.findByRole("button", { name: "Publish version 3" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Version 3 is in force.");
  });

  it("edits a draft, and lets an auditor read without writing", async () => {
    const server = fakeServer({
      "GET /privacy/notices/": page([draft, inForce]),
      "PATCH /privacy/notices/3/": { body: { ...draft, title: "Changed" } },
    });
    const { unmount } = render(<NoticeTab me={person(["administrator"])} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit the draft" }));
    expect(screen.getByLabelText("Title")).toHaveValue(draft.title);
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Changed");
    await user.click(screen.getByRole("button", { name: "Save the draft" }));
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ title: "Changed" });
    unmount();

    fakeServer({ "GET /privacy/notices/": page([draft, inForce]) });
    render(<NoticeTab me={person(["auditor"])} />);
    expect(await screen.findByText("Draft")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says when no notice has been written, and when the list cannot be loaded", async () => {
    fakeServer({ "GET /privacy/notices/": page([]) });
    const { unmount } = render(<NoticeTab me={person(["hr_manager"])} />);
    expect(await screen.findByText(/No notice yet/)).toBeInTheDocument();
    unmount();
    fakeServer({ "GET /privacy/notices/": { status: 403, body: { code: "permission_denied", detail: "Not for your role." } } });
    render(<NoticeTab me={person(["hr_manager"])} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not for your role.");
  });
});
