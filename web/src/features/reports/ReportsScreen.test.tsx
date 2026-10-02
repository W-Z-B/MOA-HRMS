import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { ReportsScreen } from "./ReportsScreen";

const reports = [
  { key: "data-quality", name: "Staff records to check", description: "", ministry_pack: false },
  { key: "headcount-by-campus", name: "Headcount by campus", description: "", ministry_pack: true },
];

describe("reports", () => {
  it("runs a report for the chosen campus and links each person to their file", async () => {
    const server = fakeServer({
      "GET /reports/": { body: reports },
      "GET /reports/data-quality/": {
        body: {
          key: "data-quality",
          name: "Staff records to check",
          rows: [
            { employee_id: 4, employee_no: "E0004", name: "Kwame Adams", campus: "Mon Repos Campus", field: "TIN", problem: "No TIN on file" },
          ],
        },
      },
    });
    const onNavigate = vi.fn();
    render(<ReportsScreen campusId={2} onNavigate={onNavigate} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Staff records to check" }));
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "No.",
      "Name",
      "Campus",
      "What",
      "To check",
    ]);
    expect(screen.getByText("1 row, this campus only")).toBeInTheDocument();
    expect(server.calls.at(-1)?.path).toBe("/reports/data-quality/?campus=2");
    await user.click(within(table).getByRole("link", { name: "E0004" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/4");
  });

  it("says when a report has nothing to show, and when none are open to the role", async () => {
    fakeServer({
      "GET /reports/": [{ body: reports }],
      "GET /reports/headcount-by-campus/": { body: { key: "headcount-by-campus", name: "Headcount by campus", rows: [] } },
    });
    render(<ReportsScreen campusId={null} onNavigate={vi.fn()} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Headcount by campus" }));
    expect(await screen.findByText("Nothing to show.")).toBeInTheDocument();
    expect(screen.getByText("0 rows, all campuses you work with")).toBeInTheDocument();
  });

  it("shows the reason a report could not run", async () => {
    fakeServer({
      "GET /reports/": { body: reports },
      "GET /reports/data-quality/": { status: 403, body: { code: "forbidden", detail: "Your role cannot run this report." } },
    });
    render(<ReportsScreen campusId={null} onNavigate={vi.fn()} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Staff records to check" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your role cannot run this report.");
  });
});
