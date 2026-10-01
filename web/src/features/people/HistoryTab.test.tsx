import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { HistoryEntry } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { HistoryTab } from "./HistoryTab";

const change: HistoryEntry = {
  id: 1,
  at: "2026-10-01T10:15:00-04:00",
  actor: "Natasha Khan",
  action: "update",
  action_name: "Changed",
  record: "Personal details",
  record_id: 1,
  changes: [
    { field: "Phone", before: "", after: "600-0001" },
    { field: "NIS number", before: "(hidden)", after: "(hidden)" },
  ],
  reason: "Form signed 30/09/2026",
  source_ip: "190.80.1.2",
};

describe("history of a file", () => {
  it("lists each change with who, when and why, in plain words", async () => {
    fakeServer({ "GET /employees/1/history/": { body: [change] } });
    render(<HistoryTab employeeId={1} />);
    expect(await screen.findByText("Personal details: changed")).toBeInTheDocument();
    expect(screen.getByText(/by Natasha Khan, 01\/10\/2026/)).toBeInTheDocument();
    expect(screen.getByText("Reason: Form signed 30/09/2026")).toBeInTheDocument();
    expect(screen.getByText("Phone changed from blank to 600-0001")).toBeInTheDocument();
    expect(screen.getByText("NIS number changed from (hidden) to (hidden)")).toBeInTheDocument();
  });

  it("shows the record as it stood on a chosen day", async () => {
    const server = fakeServer({
      "GET /employees/1/history/": { body: [] },
      "GET /employees/1/as-at/": {
        body: { date: "2026-09-29", current: false, record: { first_name: "Asha", phone: "", date_of_birth: "1990-03-14", nis_no: "(hidden)" } },
      },
    });
    render(<HistoryTab employeeId={1} />);
    expect(await screen.findByText("No changes recorded yet.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Show the personal record as it stood on/), { target: { value: "2026-09-29" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByRole("heading", { name: "As it stood on 29/09/2026" })).toBeInTheDocument();
    expect(screen.getByText("14/03/1990")).toBeInTheDocument();
    expect(server.calls.at(-1)?.path).toBe("/employees/1/as-at/?date=2026-09-29");
  });

  it("explains when a day is before the person was on file", async () => {
    fakeServer({
      "GET /employees/1/history/": { body: [] },
      "GET /employees/1/as-at/": { status: 404, body: { code: "not_found", detail: "This person was not on file yet on that day." } },
    });
    render(<HistoryTab employeeId={1} />);
    fireEvent.change(await screen.findByLabelText(/Show the personal record as it stood on/), { target: { value: "2020-01-01" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This person was not on file yet on that day.");
  });
});
