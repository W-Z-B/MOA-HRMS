import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { LeaveCheck, LeaveType } from "../../api/types";
import { pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { RequestForm } from "./RequestForm";

const TYPES: LeaveType[] = [
  { id: 1, code: "ANN", name: "Annual leave", requires_evidence: false, over_balance: "refuse", evidence_name: "Supporting document", is_paid: true },
  { id: 2, code: "SIC", name: "Sick leave", requires_evidence: false, over_balance: "evidence", evidence_name: "Doctor's note", is_paid: true },
];

const check = (over: Partial<LeaveCheck> = {}): LeaveCheck => ({
  days: 2,
  available: 10,
  remaining: 8,
  beyond: 0,
  evidence_required: false,
  evidence_name: "Supporting document",
  problems: [],
  ...over,
});

/** Choose a type and dates; date inputs take their value directly, as a phone's date picker does. */
async function fill(type: string, from: string, to: string) {
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("Leave type"), type);
  fireEvent.change(screen.getByLabelText("First day"), { target: { value: from } });
  fireEvent.change(screen.getByLabelText("Last day"), { target: { value: to } });
  return user;
}

describe("leave request form", () => {
  it("shows the days and what will be left before anything is sent", async () => {
    const server = fakeServer({ "POST /leave/requests/check/": { body: check() } });
    render(<RequestForm employeeId={1} types={TYPES} onSaved={vi.fn()} />);
    await fill("Annual leave", "2026-11-02", "2026-11-03");
    expect(await screen.findByText("2 days")).toBeInTheDocument();
    expect(screen.getByText("You will have 8 days of annual leave left.")).toBeInTheDocument();
    expect(server.calls[0].body).toEqual({ leave_type: 1, from_date: "2026-11-02", to_date: "2026-11-03" });
  });

  it("moves the last day forward when the first day passes it", async () => {
    fakeServer({ "POST /leave/requests/check/": { body: check({ days: 1 }) } });
    render(<RequestForm employeeId={1} types={TYPES} onSaved={vi.fn()} />);
    await fill("Annual leave", "2026-11-02", "2026-11-02");
    fireEvent.change(screen.getByLabelText("First day"), { target: { value: "2026-11-05" } });
    expect(screen.getByLabelText("Last day")).toHaveValue("2026-11-05");
  });

  it("blocks sending when the server finds a problem, and says what it is", async () => {
    fakeServer({
      "POST /leave/requests/check/": {
        body: check({ problems: [{ code: "overlap", field: "from_date", detail: "You already have leave on 02/11/2026." }] }),
      },
    });
    render(<RequestForm employeeId={1} types={TYPES} onSaved={vi.fn()} />);
    await fill("Annual leave", "2026-11-02", "2026-11-03");
    expect(await screen.findByText("You already have leave on 02/11/2026.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send request" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
  });

  it("asks for a doctor's note beyond the sick-leave balance and will not send without it", async () => {
    fakeServer({
      "POST /leave/requests/check/": {
        body: check({ days: 3, available: 1, beyond: 2, evidence_required: true, evidence_name: "Doctor's note" }),
      },
    });
    render(<RequestForm employeeId={1} types={TYPES} onSaved={vi.fn()} />);
    const user = await fill("Sick leave", "2026-11-02", "2026-11-04");
    expect(await screen.findByText("A doctor's note is needed.")).toBeInTheDocument();
    expect(screen.getByText("You have 1 day left; 2 days are beyond your balance.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Attach your doctor's note before sending.");
  });

  it("saves, attaches the note and sends to the manager", async () => {
    const server = fakeServer({
      "POST /leave/requests/check/": { body: check({ evidence_required: true, evidence_name: "Doctor's note" }) },
      "POST /leave/requests/": { status: 201, body: { id: 40 } },
      "POST /leave/requests/40/evidence/": { body: {} },
      "POST /leave/requests/40/transition/": { body: { id: 40, manager_name: "Michael Thomas" } },
    });
    const onSaved = vi.fn();
    render(<RequestForm employeeId={1} types={TYPES} onSaved={onSaved} />);
    const user = await fill("Sick leave", "2026-11-02", "2026-11-03");
    await user.upload(await screen.findByLabelText(/Doctor's note \(photo or PDF\)/), new File(["%PDF"], "note.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(onSaved).toHaveBeenCalledWith("Sent to Michael Thomas for approval.");
    expect(server.calls.map((c) => `${c.method} ${c.path}`).slice(-3)).toEqual([
      "POST /leave/requests/",
      "POST /leave/requests/40/evidence/",
      "POST /leave/requests/40/transition/",
    ]);
    expect(server.calls.at(-1)?.body).toEqual({ action: "submit" });
  });

  it("saves a draft without sending it", async () => {
    const server = fakeServer({
      "POST /leave/requests/check/": { body: check() },
      "POST /leave/requests/": { status: 201, body: { id: 41 } },
    });
    const onSaved = vi.fn();
    render(<RequestForm employeeId={1} types={TYPES} onSaved={onSaved} />);
    const user = await fill("Annual leave", "2026-11-02", "2026-11-03");
    await screen.findByText("2 days");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(onSaved).toHaveBeenCalledWith("Saved as a draft. Send it when you are ready.");
    expect(server.calls.some((c) => c.path.includes("transition"))).toBe(false);
  });

  it("keeps the request on the phone when there is no connection", async () => {
    fakeServer({ "POST /leave/requests/check/": offline, "POST /leave/requests/": offline });
    render(<RequestForm employeeId={1} types={TYPES} onSaved={vi.fn()} />);
    const user = await fill("Annual leave", "2026-11-02", "2026-11-03");
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByText(/No connection\. The request is saved on this phone/)).toBeInTheDocument();
    expect(pendingCount()).toBe(1);
  });

  it("reports a draft that was saved but not sent", async () => {
    fakeServer({
      "POST /leave/requests/check/": { body: check() },
      "POST /leave/requests/": { status: 201, body: { id: 42 } },
      "POST /leave/requests/42/transition/": { status: 409, body: { code: "overlap", detail: "Overlaps another request." } },
    });
    render(<RequestForm employeeId={1} types={TYPES} onSaved={vi.fn()} />);
    const user = await fill("Annual leave", "2026-11-02", "2026-11-03");
    await screen.findByText("2 days");
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Saved as a draft but not sent. Overlaps another request.");
  });
});
