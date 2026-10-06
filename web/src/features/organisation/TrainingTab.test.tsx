import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CampusDetail, Me, OrgUnit, TrainingRequirement } from "../../api/types";
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
const firstAid: TrainingRequirement = {
  id: 1,
  course_code: "SD-FA-01",
  title: "First aid at work",
  post_title: "",
  org_unit: null,
  org_unit_code: null,
  org_unit_name: null,
  campus: 1,
  campus_code: "MRP",
  campus_name: "Mon Repos Campus",
  applies_to: "campus MRP",
  due_days: 60,
  renewal_months: 24,
  is_active: true,
  notes: "",
};
const retired: TrainingRequirement = { ...firstAid, id: 2, title: "Old induction", course_code: "", applies_to: "all staff", renewal_months: null, is_active: false };
const livestock = { id: 2, code: "LIV", name: "Livestock Unit" } as OrgUnit;
const campus: CampusDetail = { id: 1, code: "MRP", name: "Mon Repos Campus", address: "", region: "" };

function show(roles: string[]) {
  render(<OrganisationScreen me={person(roles)} campusId={null} path="/organisation/training" onNavigate={vi.fn()} />);
}

describe("required training", () => {
  it("lists what each post must take, adds a requirement and retires one", async () => {
    const server = fakeServer({
      "GET /training/requirements/": page([firstAid, retired]),
      "GET /org/units/": page([livestock]),
      "GET /org/campuses/": page([campus]),
      "GET /org/positions/": page([{ title: "Farm Hand" }, { title: "Farm Hand" }, { title: "Lecturer" }]),
      "POST /training/requirements/": { status: 201, body: { ...firstAid, id: 3 } },
      "PATCH /training/requirements/1/": { body: { ...firstAid, is_active: false } },
    });
    show(["hr_manager"]);
    const list = await screen.findByRole("list", { name: "Required training" });
    expect(list).toHaveTextContent("For campus MRP · due within 60 days · every 24 months");
    expect(list).toHaveTextContent("Old induction");
    expect(within(list).getByText("Retired")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Add required training" }));
    const form = screen.getByRole("form", { name: "New required training" });
    await user.type(within(form).getByLabelText("Course"), "Safe use of tractors");
    await user.type(within(form).getByLabelText("Post"), "Farm Hand");
    await user.selectOptions(within(form).getByLabelText("Unit"), "2");
    await user.type(within(form).getByLabelText("Renew every (months)"), "36");
    await user.click(within(form).getByRole("button", { name: "Save the requirement" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Safe use of tractors saved.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      title: "Safe use of tractors",
      course_code: "",
      post_title: "Farm Hand",
      org_unit: 2,
      campus: null,
      due_days: 30,
      renewal_months: 36,
      notes: "",
    });

    await user.click(screen.getByRole("button", { name: "Change First aid at work" }));
    const change = screen.getByRole("form", { name: "Change First aid at work" });
    expect(within(change).getByLabelText("Campus")).toHaveValue("1");
    await user.click(within(change).getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Retire First aid at work" }));
    expect(await screen.findByRole("status")).toHaveTextContent("First aid at work retired.");
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ is_active: false });
  });

  it("shows the list without the means to change it to those who do not keep it", async () => {
    const server = fakeServer({ "GET /training/requirements/": page([]) });
    show(["hr_officer"]);
    expect(await screen.findByText("No required training yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add required training" })).not.toBeInTheDocument();
    expect(server.calls.map((c) => c.path)).toEqual(["/training/requirements/"]);
  });

  it("says when the list cannot be loaded, and what the server refused", async () => {
    fakeServer({
      "GET /training/requirements/": [{ status: 500, body: { code: "error", detail: "Server error." } }],
    });
    show(["hr_officer"]);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });

  it("puts back the server's reason when a requirement is refused", async () => {
    fakeServer({
      "GET /training/requirements/": page([]),
      "GET /org/units/": page([]),
      "GET /org/campuses/": page([]),
      "GET /org/positions/": page([]),
      "POST /training/requirements/": {
        status: 400,
        body: { post_title: ["No post has this title. Use a title from the establishment."] },
      },
    });
    show(["administrator"]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add required training" }));
    const form = screen.getByRole("form", { name: "New required training" });
    await user.type(within(form).getByLabelText("Course"), "Space walking");
    await user.type(within(form).getByLabelText("Post"), "Astronaut");
    await user.click(within(form).getByRole("button", { name: "Save the requirement" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No post has this title");
  });
});
