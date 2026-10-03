import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ReportsScreen } from "./ReportsScreen";

const reports = [
  { key: "data-quality", name: "Staff records to check", description: "Identifiers missing or repeated", ministry_pack: false },
  { key: "headcount-by-campus", name: "Headcount by campus", description: "Active staff on each campus", ministry_pack: true },
  { key: "establishment-vs-actual", name: "Establishment versus actual", description: "", ministry_pack: true },
];
const me = {
  id: 6,
  username: "natasha.khan",
  name: "Natasha Khan",
  roles: ["hr_officer"],
  mfa_required: false,
  mfa_verified: true,
  employee_id: 6,
  campuses: [
    { id: 1, code: "MRP", name: "Mon Repos Campus" },
    { id: 2, code: "ESQ", name: "Essequibo Campus" },
  ],
} as Me;
const quality = {
  key: "data-quality",
  name: "Staff records to check",
  rows: [{ employee_id: 4, employee_no: "E0004", name: "Kwame Adams", campus: "Mon Repos Campus", field: "TIN", problem: "No TIN on file" }],
};

describe("reports", () => {
  it("offers each report as a card, runs the first, and runs another for the chosen campus", async () => {
    const server = fakeServer({
      "GET /reports/": { body: reports },
      "GET /reports/data-quality/": { body: quality },
      "GET /reports/headcount-by-campus/": { body: { key: "headcount-by-campus", name: "Headcount by campus", rows: [] } },
    });
    const onNavigate = vi.fn();
    render(<ReportsScreen me={me} campusId={2} onNavigate={onNavigate} />);
    const cards = await screen.findByRole("radiogroup", { name: "Report" });
    expect(within(cards).getAllByRole("radio").map((r) => r.textContent)).toEqual([
      "Staff records to checkIdentifiers missing or repeated",
      "Headcount by campusActive staff on each campus",
      "Establishment versus actual",
    ]);
    expect(within(cards).getByRole("radio", { name: /Staff records to check/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/^Figures as at \d\d\/\d\d\/\d{4} for Essequibo Campus\.$/)).toBeInTheDocument();
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["No.", "Name", "Campus", "What", "To check"]);
    expect(screen.getByText("1 row")).toBeInTheDocument();
    expect(server.calls.at(-1)?.path).toBe("/reports/data-quality/?campus=2");
    const user = userEvent.setup();
    await user.click(within(table).getByRole("link", { name: "E0004" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/4");
    await user.click(within(cards).getByRole("radio", { name: /Headcount by campus/ }));
    expect(await screen.findByText("Nothing to show.")).toBeInTheDocument();
    expect(screen.getByText("0 active staff on Essequibo Campus")).toBeInTheDocument();
  });

  it("draws headcount by appointment as bars, with a total, and the establishment with frozen posts", async () => {
    fakeServer({
      "GET /reports/": { body: [reports[1], reports[2]] },
      "GET /reports/headcount-by-campus/": {
        body: {
          key: "headcount-by-campus",
          name: "Headcount by campus",
          rows: [
            { campus: "Essequibo Campus", permanent: 1, temporary: 1, contract: 1, other: 0, active: 3, total: 3 },
            { campus: "Mon Repos Campus", permanent: 6, temporary: 2, contract: 0, other: 0, active: 8, total: 8 },
          ],
        },
      },
      "GET /reports/establishment-vs-actual/": {
        body: {
          key: "establishment-vs-actual",
          name: "Establishment versus actual",
          rows: [
            { campus: "Mon Repos Campus", unit: "Administration", approved: 2, filled: 2, vacant: 0, frozen: 1 },
            { campus: "Mon Repos Campus", unit: "Department of Agriculture", approved: 4, filled: 3, vacant: 1, frozen: 0 },
          ],
        },
      },
    });
    render(<ReportsScreen me={me} campusId={null} onNavigate={vi.fn()} />);
    expect(await screen.findByText("11 active staff on all campuses you work with")).toBeInTheDocument();
    expect([...document.querySelectorAll(".legend li")].map((li) => li.textContent)).toEqual([
      "Permanent",
      "Temporary",
      "Contract",
      "Other",
    ]);
    const bars = [...document.querySelectorAll(".chart-row")];
    expect(bars.map((b) => b.querySelector(".spread")?.textContent)).toEqual(["Essequibo Campus3 staff", "Mon Repos Campus8 staff"]);
    // The longest bar fills the width; the parts of a bar are in proportion to it.
    expect([...bars[1].querySelectorAll(".stack-bar span")].map((s) => (s as HTMLElement).style.width)).toEqual(["75%", "25%"]);
    const total = screen.getAllByRole("row").at(-1)!;
    expect(total).toHaveTextContent("Total73101111");
    expect(within(screen.getByRole("table")).getAllByRole("columnheader").at(-1)).toHaveTextContent("On the staff list");

    await userEvent.setup().click(screen.getByRole("radio", { name: /Establishment versus actual/ }));
    expect(await screen.findByText("5 of 6 approved posts filled · 1 vacant · 1 frozen")).toBeInTheDocument();
    expect([...document.querySelectorAll(".chart-row .spread")].map((s) => s.textContent)).toEqual([
      "Administration2 of 2 filled",
      "Department of Agriculture3 of 4 filled",
    ]);
  });

  it("says when none are open to the role, and why a report could not run", async () => {
    const first = fakeServer({ "GET /reports/": { body: [] } });
    const { unmount } = render(<ReportsScreen campusId={null} onNavigate={vi.fn()} />);
    expect(await screen.findByText("No reports are open to your role.")).toBeInTheDocument();
    expect(first.calls).toHaveLength(1);
    unmount();
    fakeServer({
      "GET /reports/": { body: reports },
      "GET /reports/data-quality/": { status: 403, body: { code: "forbidden", detail: "Your role cannot run this report." } },
    });
    render(<ReportsScreen campusId={null} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your role cannot run this report.");
  });
});
