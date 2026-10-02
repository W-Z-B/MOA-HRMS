import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Holiday, HolidayCalendar, LeaveTypeRules, Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { HolidaysTab } from "./HolidaysTab";
import { LeaveTypesTab } from "./LeaveTypesTab";

const person = (roles: string[]): Me => ({
  id: 5,
  username: "hr.manager",
  name: "Hema Manager",
  roles,
  mfa_required: true,
  mfa_verified: true,
  employee_id: null,
});
const year = new Date().getFullYear();
const labour: Holiday = { id: 3, date: `${year}-05-01`, weekday: "Friday", name: "Labour Day" };
const deepavali: Holiday = { id: 9, date: `${year}-11-08`, weekday: "Sunday", name: "Deepavali" };
const substitute: Holiday = { id: 10, date: `${year}-11-09`, weekday: "Monday", name: "Deepavali Holiday" };
const calendar = (over: Partial<HolidayCalendar> = {}): { body: HolidayCalendar } => ({
  body: {
    year,
    expected: [
      { name: "Labour Day", rule: "Fixed date", date: `${year}-05-01`, on_file: labour },
      { name: "Good Friday", rule: "Two days before Easter Sunday", date: `${year}-04-03`, on_file: null },
      { name: "Phagwah", rule: "Date named in the gazette", date: null, on_file: null },
      { name: "Deepavali", rule: "Date named in the gazette", date: null, on_file: deepavali },
    ],
    others: [substitute],
    sundays: [deepavali],
    ...over,
  },
});

describe("public holidays", () => {
  it("checks the year against Guyana's holidays and adds the missing ones", async () => {
    const server = fakeServer({
      [`GET /holidays/calendar/?year=${year}`]: calendar(),
      "POST /holidays/": { status: 201, body: labour },
    });
    render(<HolidaysTab me={person(["hr_manager"])} />);
    const table = await screen.findByRole("table", { name: `Guyana's public holidays in ${year}` });
    expect(screen.getByText(`2 of Guyana's holidays not yet on file for ${year}`)).toBeInTheDocument();
    expect(within(table).getByText("Friday 01/05/" + year)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`Deepavali falls on Sunday 08/11/${year}`))).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Other holidays on file" })).toHaveTextContent("Deepavali Holiday");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: `Add 03/04/${year}` }));
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ date: `${year}-04-03`, name: "Good Friday" });
    expect(await screen.findByRole("status")).toHaveTextContent(`Good Friday added for 03/04/${year}.`);

    const add = screen.getByRole("button", { name: "Add Phagwah" });
    expect(add).toBeDisabled();
    await user.type(screen.getByLabelText("Date of Phagwah in the gazette"), `${year}-03-03`);
    await user.click(add);
    expect(server.calls.filter((c) => c.method === "POST").at(-1)?.body).toEqual({ date: `${year}-03-03`, name: "Phagwah" });
  });

  it("adds a substitute day, removes a holiday, and looks at next year", async () => {
    const server = fakeServer({
      [`GET /holidays/calendar/?year=${year}`]: calendar(),
      [`GET /holidays/calendar/?year=${year + 1}`]: calendar({ year: year + 1, sundays: [], others: [] }),
      "POST /holidays/": { status: 201, body: substitute },
      "DELETE /holidays/10/": { status: 204 },
    });
    render(<HolidaysTab me={person(["administrator"])} />);
    const user = userEvent.setup();
    await screen.findByRole("table");
    const form = screen.getByRole("form", { name: "Add another holiday" });
    await user.type(within(form).getByLabelText("Date"), `${year}-11-09`);
    await user.type(within(form).getByLabelText("Name"), "Deepavali Holiday");
    await user.click(within(form).getByRole("button", { name: "Add the holiday" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Deepavali Holiday added");

    await user.click(screen.getByRole("button", { name: "Remove Deepavali Holiday" }));
    expect(server.calls.some((c) => c.method === "DELETE" && c.path === "/holidays/10/")).toBe(true);

    await user.selectOptions(screen.getByLabelText("Year"), String(year + 1));
    expect(await screen.findByText(`2 of Guyana's holidays not yet on file for ${year + 1}`)).toBeInTheDocument();
  });

  it("lets others read without changing, and says when every holiday is on file", async () => {
    const complete = calendar({
      expected: [{ name: "Labour Day", rule: "Fixed date", date: `${year}-05-01`, on_file: labour }],
      others: [],
      sundays: [],
    });
    fakeServer({ [`GET /holidays/calendar/?year=${year}`]: complete });
    render(<HolidaysTab me={person(["hr_officer"])} />);
    expect(await screen.findByText(`Every holiday for ${year} is on file`)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add another holiday" })).not.toBeInTheDocument();
  });

  it("says when the holidays cannot be loaded", async () => {
    fakeServer({ [`GET /holidays/calendar/?year=${year}`]: { status: 500, body: { code: "error", detail: "Server error." } } });
    render(<HolidaysTab me={person(["hr_manager"])} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});

const annual: LeaveTypeRules = {
  id: 1,
  code: "ANN",
  name: "Annual leave",
  annual_entitlement_days: "21.00",
  accrues_monthly: true,
  carry_over_max_days: "10.00",
  max_balance_days: null,
  is_paid: true,
  requires_evidence: false,
  over_balance: "refuse",
  evidence_name: "Supporting document",
  evidence_is_medical: false,
  appointment_types: [],
  term_time_restricted: true,
};
const sick: LeaveTypeRules = {
  ...annual,
  id: 2,
  code: "SIC",
  name: "Sick leave",
  annual_entitlement_days: "14.00",
  accrues_monthly: false,
  carry_over_max_days: "0.00",
  over_balance: "evidence",
  evidence_name: "Doctor's note",
  evidence_is_medical: true,
  appointment_types: ["permanent", "contract"],
  term_time_restricted: false,
};
const page = (results: LeaveTypeRules[]) => ({ body: { count: results.length, next: null, previous: null, results } });

describe("leave types", () => {
  it("shows each type's rules in words", async () => {
    fakeServer({ "GET /leave/types/": page([annual, sick]) });
    render(<LeaveTypesTab me={person(["hr_officer"])} />);
    const table = await screen.findByRole("table", { name: "Leave types and their rules" });
    const [, first, second] = within(table).getAllByRole("row");
    expect(first).toHaveTextContent("21 days");
    expect(first).toHaveTextContent("Refused");
    expect(first).toHaveTextContent("Everyone");
    expect(second).toHaveTextContent("Doctor's note (medical)");
    expect(second).toHaveTextContent("Permanent, Contract");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("changes a type's rules, keeping its code", async () => {
    const server = fakeServer({
      "GET /leave/types/": page([annual]),
      "PATCH /leave/types/1/": { body: { ...annual, annual_entitlement_days: "24.00" } },
    });
    render(<LeaveTypesTab me={person(["hr_manager"])} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change Annual leave" }));
    const form = screen.getByRole("form", { name: "Change Annual leave" });
    expect(within(form).getByLabelText("Code")).toHaveAttribute("readonly");
    const days = within(form).getByLabelText("Days a year");
    await user.clear(days);
    await user.type(days, "24");
    await user.click(within(form).getByLabelText("Paid"));
    await user.click(within(form).getByLabelText("Seasonal"));
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Annual leave saved.");
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
      code: "ANN",
      annual_entitlement_days: "24",
      is_paid: false,
      appointment_types: ["seasonal"],
    });
  });

  it("adds a new leave type, and shows the server's refusal", async () => {
    const server = fakeServer({
      "GET /leave/types/": page([annual]),
      "POST /leave/types/": [
        { status: 400, body: { code: ["leave type with this code already exists."] } },
        { status: 201, body: { ...annual, id: 7, code: "CMP", name: "Compassionate leave" } },
      ],
    });
    render(<LeaveTypesTab me={person(["administrator"])} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add a leave type" }));
    const form = screen.getByRole("form", { name: "New leave type" });
    await user.type(within(form).getByLabelText("Code"), "cmp");
    await user.type(within(form).getByLabelText("Name"), "Compassionate leave");
    await user.selectOptions(within(form).getByLabelText("Beyond the balance"), "evidence");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("leave type with this code already exists.");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Compassionate leave saved.");
    expect(server.calls.filter((c) => c.method === "POST").at(-1)?.body).toMatchObject({ code: "CMP", over_balance: "evidence" });
  });
});
