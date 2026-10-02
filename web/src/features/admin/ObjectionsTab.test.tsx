import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Employee, Me, Objection, RecordRestriction } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ObjectionsTab } from "./ObjectionsTab";

const person = (roles: string[]): Me => ({
  id: 40,
  username: "privacy.officer",
  name: "Privacy Officer",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const open: Objection = {
  id: 7,
  employee: 1,
  employee_name: "Asha Persaud",
  employee_no: "E0001",
  part: "contact",
  part_name: "Contact details",
  grounds: "My phone number is on the farm roster",
  state: "open",
  state_name: "With the data protection officer",
  due_by: "2026-11-01",
  overdue: true,
  created_at: "2026-10-02T10:00:00-04:00",
  decided_by_name: null,
  decided_at: null,
  reasons: "",
  is_mine: false,
};
const held: RecordRestriction = {
  id: 3,
  employee: 1,
  employee_name: "Asha Persaud",
  employee_no: "E0001",
  part: "bank",
  part_name: "Bank details",
  ground: "unlawful",
  ground_name: "Its processing is unlawful",
  note: "Collected without a notice",
  correction: null,
  objection: null,
  created_at: "2026-10-02T09:00:00-04:00",
  placed_by_name: "Natasha Khan",
  in_force: true,
  lifted_at: null,
  lifted_by_name: null,
  lifted_reason: "",
};
const byObjection: RecordRestriction = { ...held, id: 4, part: "contact", part_name: "Contact details", ground: "objection", ground_name: "The person has objected", note: "", objection: 7 };
const staff = [{ id: 1, full_name: "Asha Persaud", employee_no: "E0001" }] as Employee[];

describe("objections and restrictions", () => {
  it("lets the officer decide an objection, lift a restriction and restrict a part", async () => {
    const server = fakeServer({
      "GET /privacy/objections/": [page([open]), page([{ ...open, state: "not_upheld", state_name: "Not upheld", reasons: "Needed in an emergency", decided_by_name: "Privacy Officer" }])],
      "GET /privacy/restrictions/": [page([held, byObjection]), page([held]), page([]), page([held])],
      "GET /employees/": page(staff),
      "POST /privacy/objections/7/decide/": [{ status: 400, body: { reasons: ["Give the reasons."] } }, { body: open }],
      "POST /privacy/restrictions/3/lift/": { body: { ...held, in_force: false } },
      "POST /privacy/restrictions/": { status: 201, body: held },
    });
    render(<ObjectionsTab me={person(["data_protection_officer"])} />);
    const user = userEvent.setup();
    const objections = await screen.findByRole("list", { name: "Objections" });
    expect(objections).toHaveTextContent("Asha Persaud E0001, about contact details");
    expect(within(objections).getByText("Late")).toBeInTheDocument();
    const restrictions = screen.getByRole("list", { name: "Restrictions in force" });
    expect(within(restrictions).queryByRole("form", { name: /Contact details/ })).not.toBeInTheDocument(); // the objection decides it

    const decide = screen.getByRole("form", { name: "Decide the objection of Asha Persaud" });
    await user.selectOptions(within(decide).getByLabelText("Decision"), "not_upheld");
    await user.type(within(decide).getByLabelText(/Reasons/), " ");
    await user.click(within(decide).getByRole("button", { name: "Record the decision" }));
    expect(await within(decide).findByRole("alert")).toHaveTextContent("Give the reasons.");
    await user.clear(within(decide).getByLabelText(/Reasons/));
    await user.type(within(decide).getByLabelText(/Reasons/), "Needed in an emergency");
    await user.click(within(decide).getByRole("button", { name: "Record the decision" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The decision is recorded. The person is told.");
    expect(server.calls.filter((c) => c.path === "/privacy/objections/7/decide/").at(-1)?.body).toEqual({
      outcome: "not_upheld",
      reasons: "Needed in an emergency",
    });
    expect(await screen.findByText(/decided by Privacy Officer: Needed in an emergency/)).toBeInTheDocument();

    const lift = await screen.findByRole("form", { name: "Lift the restriction on Bank details for Asha Persaud" });
    await user.type(within(lift).getByLabelText(/Why it is lifted/), "A notice was given");
    await user.click(within(lift).getByRole("button", { name: "Lift it" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Lifted. The person is told why.");
    expect(await screen.findByText("No part of any record is held back.")).toBeInTheDocument();

    const restrict = screen.getByRole("form", { name: "Restrict part of a record" });
    await within(restrict).findByRole("option", { name: "Asha Persaud (E0001)" });
    await user.selectOptions(within(restrict).getByLabelText("Whose record"), "1");
    await user.selectOptions(within(restrict).getByLabelText("Which part"), "bank");
    await user.selectOptions(within(restrict).getByLabelText("Why"), "unlawful");
    await user.type(within(restrict).getByLabelText("Note"), "Collected without a notice");
    await user.click(within(restrict).getByRole("button", { name: "Restrict it" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Bank details in the record of Asha Persaud is restricted. They are told.");
    expect(server.calls.find((c) => c.path === "/privacy/restrictions/" && c.method === "POST")?.body).toEqual({
      employee: 1,
      part: "bank",
      ground: "unlawful",
      note: "Collected without a notice",
    });
  });

  it("shows the HR Manager the objections without the officer's decision form, and says when there are none", async () => {
    fakeServer({
      "GET /privacy/objections/": page([open]),
      "GET /privacy/restrictions/": page([]),
      "GET /employees/": page(staff),
    });
    render(<ObjectionsTab me={person(["hr_manager"])} />);
    expect(await screen.findByRole("list", { name: "Objections" })).toHaveTextContent("My phone number is on the farm roster");
    expect(screen.queryByRole("form", { name: /Decide the objection/ })).not.toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Restrict part of a record" })).toBeInTheDocument();
    expect(await screen.findByText("No part of any record is held back.")).toBeInTheDocument();
  });

  it("says when the objections cannot be loaded", async () => {
    fakeServer({
      "GET /privacy/objections/": { status: 500, body: { code: "error", detail: "Server error." } },
      "GET /privacy/restrictions/": page([]),
    });
    render(<ObjectionsTab me={person(["administrator"])} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
    expect(screen.queryByText("No objections.")).not.toBeInTheDocument();
  });
});
