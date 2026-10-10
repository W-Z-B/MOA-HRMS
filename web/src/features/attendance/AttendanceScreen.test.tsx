import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AttendanceRecord, Me, Paginated } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { AttendanceScreen } from "./AttendanceScreen";

function me(over: Partial<Me> = {}): Me {
  return {
    id: 1,
    username: "asha",
    name: "Asha Persaud",
    roles: ["employee"],
    mfa_required: false,
    mfa_verified: true,
    employee_id: 1,
    ...over,
  };
}

function record(over: Partial<AttendanceRecord> = {}): AttendanceRecord {
  return {
    id: 1,
    employee: 1,
    employee_name: "Asha Persaud",
    campus_name: "Mon Repos Campus",
    date: "2026-10-09",
    shift: null,
    scheduled_in: "08:00:00",
    scheduled_out: "16:30:00",
    time_in: null,
    time_out: null,
    hours: 0,
    overtime_hours: 0,
    source: "self",
    source_display: "Self-service check-in",
    status: "present",
    status_display: "Present",
    leave_request: null,
    note: "",
    resolved: false,
    is_mine: true,
    ...over,
  };
}

function paginated<T>(results: T[]): Paginated<T> {
  return { count: results.length, next: null, previous: null, results };
}

describe("attendance screen", () => {
  it("lets an employee check in, then check out", async () => {
    fakeServer({
      "GET /attendance/records/mine/": { status: 204 },
      "GET /attendance/records/": { body: paginated([]) },
      "POST /attendance/records/check_in/": {
        status: 201,
        body: record({ time_in: "08:05:00", status: "present" }),
      },
      "POST /attendance/records/check_out/": {
        status: 200,
        body: record({ time_in: "08:05:00", time_out: "16:40:00", status: "present" }),
      },
    });
    render(<AttendanceScreen me={me()} path="/attendance" onNavigate={() => undefined} />);

    expect(await screen.findByText("You have not checked in today.")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Check in" }));
    expect(await screen.findByText(/Checked in at 08:05/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check out" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Check out" }));
    expect(await screen.findByText(/Checked out at 16:40/)).toBeInTheDocument();
  });

  it("shows a refusal when checking in again the same day", async () => {
    fakeServer({
      "GET /attendance/records/mine/": { status: 204 },
      "GET /attendance/records/": { body: paginated([]) },
      "POST /attendance/records/check_in/": {
        status: 409,
        body: { code: "already_checked_in", detail: "You have already checked in today." },
      },
    });
    render(<AttendanceScreen me={me()} path="/attendance" onNavigate={() => undefined} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Check in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You have already checked in today.");
  });

  it("does not offer tabs or exceptions to a plain employee", async () => {
    fakeServer({
      "GET /attendance/records/mine/": { status: 204 },
      "GET /attendance/records/": { body: paginated([]) },
    });
    render(<AttendanceScreen me={me()} path="/attendance" onNavigate={() => undefined} />);
    await screen.findByText("You have not checked in today.");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("lets Human Resources correct an exception, with a reason", async () => {
    const exception = record({
      id: 7,
      date: "2026-10-08",
      time_in: "08:00:00",
      time_out: null,
      status: "missing_checkout",
      status_display: "Checked in, not checked out",
      is_mine: false,
    });
    fakeServer({
      "GET /attendance/records/": { body: paginated([exception]) },
      "POST /attendance/records/7/correct/": {
        status: 200,
        body: { ...exception, status: "present", resolved: true },
      },
    });
    const hr = me({ roles: ["hr_officer"], employee_id: null });
    render(<AttendanceScreen me={hr} path="/attendance?tab=exceptions" onNavigate={() => undefined} />);

    expect(await screen.findByText("Asha Persaud")).toBeInTheDocument();
    const row = screen.getByRole("article", { name: /Asha Persaud/ });
    await userEvent.setup().click(within(row).getByRole("button", { name: "Save" }));
    // The note is required, so nothing is sent and the row explains why.
    expect(within(row).getByRole("alert")).toHaveTextContent("Say why this day is being corrected");

    const user = userEvent.setup();
    await user.type(within(row).getByLabelText("Why this is being corrected"), "Confirmed with the supervisor");
    fireEvent.change(within(row).getByLabelText("Checked out"), { target: { value: "16:30" } });
    await user.click(within(row).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });
});
