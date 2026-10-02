import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChartPost, ChartUnit, Me, OrgChart } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { OrganisationScreen } from "./OrganisationScreen";

const officer: Me = {
  id: 7,
  username: "hr.officer",
  name: "Natasha Khan",
  roles: ["hr_officer"],
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
};
const post = (fields: Partial<ChartPost>): ChartPost => ({
  id: 1,
  number: "AGR-001",
  title: "Head of Department, Agriculture",
  grade_name: "GS GS9, step 1",
  status: "approved",
  status_name: "Approved",
  fte: "1.00",
  filled: true,
  vacant: false,
  holder: "Michael Thomas",
  acting: null,
  has_acting: false,
  ...fields,
});
const livestock: ChartUnit = {
  id: 2,
  code: "LIV",
  name: "Livestock Unit",
  unit_type: "unit",
  unit_type_name: "Unit",
  head: "Ravi Singh",
  totals: { posts: 2, filled: 1, vacant: 1, frozen: 0 },
  posts: [
    post({ id: 5, number: "LIV-001", title: "Livestock Instructor", holder: "Ravi Singh" }),
    post({ id: 6, number: "LIV-002", title: "Farm Hand", fte: "0.50", filled: false, vacant: true, holder: null, acting: "Dev Narine", has_acting: true }),
  ],
  units: [],
};
const agriculture: ChartUnit = {
  id: 1,
  code: "AGR",
  name: "Department of Agriculture",
  unit_type: "department",
  unit_type_name: "Department",
  head: "Michael Thomas",
  totals: { posts: 4, filled: 2, vacant: 1, frozen: 1 },
  posts: [post({}), post({ id: 3, number: "AGR-009", title: "Soil Chemist", status: "frozen", status_name: "Frozen", filled: false, holder: null })],
  units: [livestock],
};
const chart: OrgChart = {
  as_at: "2026-10-01",
  campuses: [
    { id: 1, code: "MRP", name: "Mon Repos Campus", names: true, totals: agriculture.totals, units: [agriculture] },
    { id: 2, code: "ESQ", name: "Essequibo Campus", names: false, totals: { posts: 0, filled: 0, vacant: 0, frozen: 0 }, units: [] },
  ],
};

function show(campusId: number | null = null) {
  render(<OrganisationScreen me={officer} campusId={campusId} path="/organisation/chart" onNavigate={vi.fn()} />);
}

describe("organisation chart", () => {
  it("draws the units as they nest, with holders, vacancies, frozen and acting posts", async () => {
    fakeServer({ "GET /org/chart/": { body: chart } });
    show();
    const top = await screen.findByRole("list", { name: "Units on Mon Repos Campus" });
    expect(screen.getByRole("tab", { name: "Chart" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("As it stands on 1 October 2026.")).toBeInTheDocument();
    expect(screen.getByText("4 posts: 2 filled, 1 vacant, 1 frozen")).toBeInTheDocument();
    const posts = within(top).getByRole("list", { name: "Posts in Department of Agriculture" });
    expect(within(posts).getByText("Michael Thomas")).toBeInTheDocument();
    expect(within(posts).getByText("Frozen")).toBeInTheDocument();
    const under = within(top).getByRole("list", { name: "Units under Department of Agriculture" });
    const farmHands = within(under).getByRole("list", { name: "Posts in Livestock Unit" });
    expect(within(farmHands).getByText("Vacant")).toBeInTheDocument();
    expect(within(farmHands).getByText("Acting: Dev Narine")).toBeInTheDocument();
    expect(within(farmHands).getByText(/0\.5 of full time/)).toBeInTheDocument();
    expect(screen.queryByText("Essequibo Campus")).not.toBeInTheDocument(); // no units there to draw
  });

  it("finds a person, post or unit and marks it", async () => {
    fakeServer({ "GET /org/chart/?campus=1": { body: chart } });
    show(1);
    const user = userEvent.setup();
    const search = await screen.findByRole("searchbox", { name: "Find a person, post or unit" });
    await user.type(search, "dev");
    expect(screen.getByRole("status")).toHaveTextContent("1 match.");
    expect(screen.getByText("Dev", { selector: "mark" })).toBeInTheDocument();
    expect(screen.queryByText("Soil Chemist")).not.toBeInTheDocument();
    expect(screen.getByText("Department of Agriculture")).toBeInTheDocument(); // the way down to the match
    await user.clear(search);
    await user.type(search, "livestock");
    expect(screen.getByRole("status")).toHaveTextContent("2 matches."); // the unit and its instructor post
    expect(screen.getByText("Farm Hand")).toBeInTheDocument(); // a unit found shows all it holds
    await user.clear(search);
    await user.type(search, "zzz");
    expect(screen.getByRole("status")).toHaveTextContent("Nothing matches.");
  });

  it("closes and opens every unit, and prints the chart open", async () => {
    fakeServer({ "GET /org/chart/": { body: chart } });
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    show();
    const user = userEvent.setup();
    await screen.findByRole("list", { name: "Units on Mon Repos Campus" });
    const units = () => Array.from(document.querySelectorAll("details.org-unit"));
    expect(units().every((d) => d.hasAttribute("open"))).toBe(true);
    await user.click(screen.getByRole("button", { name: "Close all" }));
    expect(units().some((d) => d.hasAttribute("open"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Open all" }));
    expect(units().every((d) => d.hasAttribute("open"))).toBe(true);
    await user.click(screen.getByRole("button", { name: "Close all" }));
    await user.click(screen.getByRole("button", { name: "Print" }));
    expect(print).toHaveBeenCalled();
    expect(units().every((d) => d.hasAttribute("open"))).toBe(true);
    print.mockRestore();
  });

  it("says when names are kept to the staff directory's readers", async () => {
    const hidden: OrgChart = {
      ...chart,
      campuses: [
        {
          ...chart.campuses[0],
          names: false,
          units: [{ ...livestock, head: null, posts: [post({ number: "LIV-001", holder: null }), post({ id: 9, number: "LIV-003", filled: false, holder: null, acting: null, has_acting: true })] }],
        },
      ],
    };
    fakeServer({ "GET /org/chart/": { body: hidden } });
    show();
    expect(await screen.findByText(/Who holds each post shows to the roles that read the staff directory/)).toBeInTheDocument();
    expect(screen.getByText("Filled")).toBeInTheDocument();
    expect(screen.getByText("Someone acting")).toBeInTheDocument();
  });

  it("says when the chart cannot be loaded", async () => {
    fakeServer({ "GET /org/chart/": { status: 500, body: { code: "error", detail: "Server error." } } });
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });

  it("says when there are no units yet", async () => {
    fakeServer({ "GET /org/chart/": { body: { as_at: "2026-10-01", campuses: [{ ...chart.campuses[1] }] } } });
    show();
    expect(await screen.findByText("No units here yet.")).toBeInTheDocument();
  });
});
