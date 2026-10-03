import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CampusDetail, Employee, Grade, Me, OrgUnit, Position, SalaryScale } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { OrganisationScreen } from "./OrganisationScreen";

const person = (roles: string[]): Me => ({
  id: 5,
  username: "hr.manager",
  name: "Hema Manager",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const agriculture: OrgUnit = {
  id: 1,
  code: "AGR",
  name: "Department of Agriculture",
  unit_type: "department",
  unit_type_name: "Department",
  parent: null,
  parent_name: null,
  campus: 1,
  campus_name: "Mon Repos Campus",
  head: 2,
  head_name: "Michael Thomas",
};
const livestock: OrgUnit = {
  ...agriculture,
  id: 2,
  code: "LIV",
  name: "Livestock Unit",
  unit_type: "unit",
  unit_type_name: "Unit",
  parent: 1,
  parent_name: "Department of Agriculture",
  head: null,
  head_name: null,
};
const grade: Grade = { id: 4, scale: 1, scale_code: "GS", code: "GS7", step: 1, amount: "250000.00", effective_from: "2026-01-01" };
const lecturer: Position = {
  id: 10,
  number: "AGR-002",
  title: "Lecturer, Crop Science",
  grade: 4,
  grade_name: "GS GS7, step 1",
  org_unit: 1,
  org_unit_name: "Department of Agriculture",
  campus_name: "Mon Repos Campus",
  status: "approved",
  status_name: "Approved",
  fte: "1.00",
  is_vacant: false,
  holder: "Asha Persaud",
};
const vacant: Position = { ...lecturer, id: 11, number: "AGR-004", title: "Laboratory Technician", is_vacant: true, holder: null };
const scale: SalaryScale = { id: 1, code: "GS", name: "General scale" };
const campus: CampusDetail = { id: 1, code: "MRP", name: "Mon Repos Campus", address: "Mon Repos, East Coast Demerara", region: "Region 4" };

function render_(path: string, roles: string[], campusId: number | null = null) {
  const onNavigate = vi.fn();
  render(<OrganisationScreen me={person(roles)} campusId={campusId} path={path} onNavigate={onNavigate} />);
  return onNavigate;
}

describe("posts", () => {
  it("lists the establishment with holders and vacancies, and opens the other tabs", async () => {
    fakeServer({
      "GET /org/positions/": page([lecturer, vacant]),
      "GET /org/units/": page([agriculture]),
      "GET /org/grades/": page([grade]),
    });
    const onNavigate = render_("/organisation/posts", ["hr_officer"]);
    const table = await screen.findByRole("table", { name: "Posts" });
    // The Chart comes first, and says who keeps the establishment (item 2.30).
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Chart", "Units", "Posts", "Salary scales", "Campuses"]);
    expect(screen.getByText(/Changes are made by the HR Manager or an administrator\./)).toBeInTheDocument();
    expect(within(table).getByText("Asha Persaud")).toBeInTheDocument();
    expect(within(table).getByText("Vacant")).toBeInTheDocument();
    expect(screen.getByText("2 posts, 1 approved and vacant")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add a post" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Units" }));
    expect(onNavigate).toHaveBeenCalledWith("/organisation/units");
  });

  it("adds a post and removes a vacant one, filtered to the campus and unit chosen", async () => {
    const server = fakeServer({
      "GET /org/positions/?campus=1": page([vacant]),
      "GET /org/positions/?campus=1&org_unit=1": page([vacant]),
      "GET /org/units/?campus=1": page([agriculture]),
      "GET /org/grades/": page([grade]),
      "POST /org/positions/": { status: 201, body: vacant },
      "DELETE /org/positions/11/": { status: 204 },
    });
    render_("/organisation/posts", ["hr_manager"], 1);
    expect(screen.queryByText(/Changes are made by/)).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Unit"), "1");
    await user.click(screen.getByRole("button", { name: "Add a post" }));
    const form = screen.getByRole("form", { name: "New post" });
    await user.type(within(form).getByLabelText("Post number"), "AGR-005");
    await user.type(within(form).getByLabelText("Title"), "Field Assistant");
    await user.selectOptions(within(form).getByLabelText("Unit"), "1");
    await user.selectOptions(within(form).getByLabelText("Grade"), "4");
    await user.click(within(form).getByRole("button", { name: "Save the post" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Post AGR-005 saved.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({ number: "AGR-005", org_unit: 1, grade: 4 });

    await user.click(screen.getByRole("button", { name: "Remove post AGR-004" }));
    expect(server.calls.some((c) => c.method === "DELETE")).toBe(true);
  });

  it("changes a post, and says why one still held cannot go", async () => {
    const server = fakeServer({
      "GET /org/positions/": page([lecturer]),
      "GET /org/units/": page([agriculture]),
      "GET /org/grades/": page([grade]),
      "PATCH /org/positions/10/": { status: 409, body: { code: "in_use", detail: "It cannot be removed while 1 assignment still refers to it." } },
    });
    render_("/organisation/posts", ["administrator"]);
    const user = userEvent.setup();
    expect(await screen.findByRole("button", { name: "Change post AGR-002" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove post AGR-002" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Change post AGR-002" }));
    const form = screen.getByRole("form", { name: "Change post AGR-002" });
    await user.selectOptions(within(form).getByLabelText("Status"), "frozen");
    await user.click(within(form).getByRole("button", { name: "Save the post" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("1 assignment still refers to it");
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ status: "frozen" });
  });
});

describe("units", () => {
  it("shows units under the unit they sit in, and adds one with its head", async () => {
    const staff: Employee[] = [
      {
        id: 2,
        employee_no: "E0002",
        full_name: "Michael Thomas",
        first_name: "Michael",
        last_name: "Thomas",
        other_names: "",
        date_of_birth: "1978-07-22",
        gender: "M",
        campus: 1,
        campus_name: "Mon Repos Campus",
        status: "active",
        position_title: null,
        nis_no_masked: null,
        tin_masked: null,
        national_id_masked: null,
        email: "",
        phone: "",
        address: "",
        user: null,
      },
    ];
    const server = fakeServer({
      "GET /org/units/": page([agriculture, livestock]),
      "GET /org/campuses/": page([campus]),
      "GET /employees/?campus=1&status=active": page(staff),
      "POST /org/units/": { status: 201, body: livestock },
      "DELETE /org/units/2/": { status: 409, body: { code: "in_use", detail: "It cannot be removed while 3 positions still refer to it." } },
    });
    render_("/organisation/units", ["hr_manager"]);
    const list = await screen.findByRole("list", { name: "Units" });
    const [top, below] = within(list).getAllByRole("listitem");
    expect(top).toHaveTextContent("headed by Michael Thomas");
    expect(below).toHaveTextContent("under Department of Agriculture");

    const user = userEvent.setup();
    await user.click(within(below).getByRole("button", { name: "Remove Livestock Unit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("3 positions still refer to it");

    await user.click(screen.getByRole("button", { name: "Add a unit" }));
    const form = screen.getByRole("form", { name: "New unit" });
    await user.type(within(form).getByLabelText("Code"), "LIV-P");
    await user.type(within(form).getByLabelText("Name"), "Pig Unit");
    await user.selectOptions(within(form).getByLabelText("Kind"), "section");
    await user.selectOptions(within(form).getByLabelText("Campus"), "1");
    await user.selectOptions(within(form).getByLabelText("Sits under"), "2");
    await user.selectOptions(await within(form).findByLabelText("Headed by"), "2");
    await user.click(within(form).getByRole("button", { name: "Save the unit" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Pig Unit saved.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      code: "LIV-P",
      name: "Pig Unit",
      unit_type: "section",
      campus: 1,
      parent: 2,
      head: 2,
    });
  });

  it("changes a unit, and lets others read only", async () => {
    const server = fakeServer({
      "GET /org/units/": page([livestock]),
      "GET /org/campuses/": page([campus]),
      "GET /employees/?campus=1&status=active": page([]),
      "PATCH /org/units/2/": { body: livestock },
    });
    const { unmount } = render(<OrganisationScreen me={person(["hr_manager"])} campusId={null} path="/organisation/units" onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change Livestock Unit" }));
    const form = screen.getByRole("form", { name: "Change Livestock Unit" });
    await user.clear(within(form).getByLabelText("Name"));
    await user.type(within(form).getByLabelText("Name"), "Livestock and Dairy");
    await user.click(within(form).getByRole("button", { name: "Save the unit" }));
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ name: "Livestock and Dairy", parent: 1 });
    unmount();

    fakeServer({ "GET /org/units/": page([livestock]), "GET /org/campuses/": page([campus]) });
    render_("/organisation/units", ["supervisor"]);
    await screen.findByRole("list", { name: "Units" });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("salary scales", () => {
  it("shows each scale's grades in G$, and adds a new amount from a date", async () => {
    const server = fakeServer({
      "GET /org/salary-scales/": page([scale]),
      "GET /org/grades/": page([grade]),
      "POST /org/grades/": { status: 201, body: grade },
      "POST /org/salary-scales/": { status: 201, body: { id: 2, code: "TS", name: "Teaching scale" } },
    });
    render_("/organisation/grades", ["finance"]);
    const table = await screen.findByRole("table", { name: "Grades on scale GS" });
    expect(table).toHaveTextContent("G$250,000.00");
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Add a grade or a new amount" });
    await user.selectOptions(within(form).getByLabelText("Scale"), "1");
    await user.type(within(form).getByLabelText("Grade"), "GS7");
    await user.type(within(form).getByLabelText("A month (G$)"), "262500");
    await user.type(within(form).getByLabelText("From"), "2027-01-01");
    await user.click(within(form).getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Grade GS7, step 1: G$262,500.00 a month from 01/01/2027.");
    expect(server.calls.find((c) => c.path === "/org/grades/" && c.method === "POST")?.body).toEqual({
      scale: 1,
      code: "GS7",
      step: 1,
      amount: "262500",
      effective_from: "2027-01-01",
    });
    const scaleForm = screen.getByRole("form", { name: "Add a salary scale" });
    await user.type(within(scaleForm).getByLabelText("Code"), "TS");
    await user.type(within(scaleForm).getByLabelText("Name"), "Teaching scale");
    await user.click(within(scaleForm).getByRole("button", { name: "Add the scale" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Scale TS added.");
  });

  it("hides amounts from roles that do not see pay", async () => {
    fakeServer({ "GET /org/salary-scales/": page([scale]), "GET /org/grades/": page([{ ...grade, amount: null }]) });
    render_("/organisation/grades", ["supervisor"]);
    expect(await screen.findByText("Not shown to your role")).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });
});

describe("campuses", () => {
  it("lists the campuses and changes one", async () => {
    const server = fakeServer({
      "GET /org/campuses/": page([campus]),
      "PATCH /org/campuses/1/": { body: campus },
      "POST /org/campuses/": { status: 201, body: { ...campus, id: 3, code: "BER", name: "Berbice (planned)" } },
    });
    render_("/organisation/campuses", ["administrator"]);
    const user = userEvent.setup();
    expect(await screen.findByText("Mon Repos, East Coast Demerara · Region 4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Change Mon Repos Campus" }));
    const form = screen.getByRole("form", { name: "Change Mon Repos Campus" });
    await user.clear(within(form).getByLabelText("Region"));
    await user.type(within(form).getByLabelText("Region"), "Region 4, Demerara-Mahaica");
    await user.click(within(form).getByRole("button", { name: "Save the campus" }));
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ region: "Region 4, Demerara-Mahaica" });
    await user.click(await screen.findByRole("button", { name: "Add a campus" }));
    const create = screen.getByRole("form", { name: "New campus" });
    await user.type(within(create).getByLabelText("Code"), "BER");
    await user.type(within(create).getByLabelText("Name"), "Berbice (planned)");
    await user.click(within(create).getByRole("button", { name: "Save the campus" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Berbice (planned) saved.");
  });

  it("says when the campuses cannot be loaded", async () => {
    fakeServer({ "GET /org/campuses/": { status: 500, body: { code: "error", detail: "Server error." } } });
    render_("/organisation/campuses", ["hr_officer"]);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});
