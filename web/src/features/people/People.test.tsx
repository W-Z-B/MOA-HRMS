import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee, Me } from "../../api/types";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { EmployeeFile } from "./EmployeeFile";
import { EmployeeFormPage } from "./EmployeeFormPage";
import { PeopleScreen } from "./PeopleScreen";

const MRP = { id: 1, code: "MRP", name: "Mon Repos Campus" };
const ESQ = { id: 2, code: "ESQ", name: "Essequibo Campus" };
const page = <T,>(results: T[], next: string | null = null, count = results.length) => ({
  body: { count, next, previous: null, results },
});

const hr: Me = {
  id: 6,
  username: "natasha.khan",
  name: "Natasha Khan",
  roles: ["employee", "hr_officer", "supervisor"],
  mfa_required: false,
  mfa_verified: true,
  employee_id: 6,
  campuses: [ESQ, MRP],
};
const auditor: Me = { ...hr, id: 9, name: "Audit Reviewer", roles: ["auditor"], employee_id: null };

const asha: Employee = {
  id: 1,
  employee_no: "E0001",
  full_name: "Asha Persaud",
  first_name: "Asha",
  last_name: "Persaud",
  other_names: "",
  date_of_birth: "1990-03-14",
  gender: "F",
  campus: 1,
  campus_name: "Mon Repos Campus",
  status: "active",
  position_title: "Lecturer, Crop Science",
  unit_name: "Department of Agriculture",
  appointment_type: "Permanent",
  started: "2019-09-02",
  manager_name: "Michael Thomas",
  contract_type: "Open ended",
  ends: null,
  probation_end: null,
  restricted: [],
  nis_no_masked: "••••••001",
  tin_masked: "••••••001",
  national_id_masked: "••••••001",
  email: "asha.persaud@gsa.example",
  phone: "",
  address: "Demonstration record (fictional person)",
  user: 3,
};
const troy: Employee = {
  ...asha,
  id: 9,
  employee_no: "E0009",
  full_name: "Troy Benjamin",
  campus: 2,
  campus_name: "Essequibo Campus",
  status: "on_leave",
  position_title: null,
  unit_name: null,
  appointment_type: null,
  started: null,
  manager_name: null,
  contract_type: null,
};

function framed(ui: React.ReactElement) {
  const frame = { setCrumb: vi.fn(), decided: vi.fn() };
  render(<FrameContext.Provider value={frame}>{ui}</FrameContext.Provider>);
  return frame;
}

describe("the People list", () => {
  it("lists staff with their unit, campus, appointment and status, and opens a file", async () => {
    fakeServer({
      "GET /org/units/": page([{ id: 4, name: "Livestock Unit" }, { id: 3, name: "Department of Agriculture" }]),
      "GET /employees/": page([asha, troy]),
    });
    const onNavigate = vi.fn();
    render(<PeopleScreen me={hr} campusId={null} onNavigate={onNavigate} />);
    expect(await screen.findByText("2 staff on all campuses")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Staff" });
    const [, first, second] = within(table).getAllByRole("row");
    expect(first).toHaveTextContent("Asha PersaudE0001");
    expect(first).toHaveTextContent("Lecturer, Crop ScienceDepartment of Agriculture");
    expect(first).toHaveTextContent("PermanentActive");
    expect(second).toHaveTextContent("Unassigned");
    expect(second).toHaveTextContent("NoneOn leave");
    // Units are offered in alphabetical order.
    expect(within(screen.getByRole("combobox", { name: "Unit" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All units",
      "Department of Agriculture",
      "Livestock Unit",
    ]);
    await userEvent.setup().click(within(first).getByRole("link", { name: "Asha Persaud" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/1");
  });

  it("filters by name, status and unit inside the chosen campus, and clears the filters when nobody matches", async () => {
    const server = fakeServer({
      "GET /org/units/": page([{ id: 4, name: "Livestock Unit" }]),
      // The campus alone finds Asha; any filter on top finds nobody.
      "GET /employees/?campus=1": page([asha]),
      "GET /employees/": page([]),
    });
    render(<PeopleScreen me={hr} campusId={1} onNavigate={vi.fn()} />);
    expect(await screen.findByText("1 staff on Mon Repos Campus")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByRole("searchbox", { name: "Search staff" }), "zz");
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "suspended");
    await user.selectOptions(screen.getByRole("combobox", { name: "Unit" }), "4");
    expect(await screen.findByText("No one matches those filters.")).toBeInTheDocument();
    const last = server.calls.filter((c) => c.path.startsWith("/employees/")).at(-1)!;
    expect(last.path).toBe("/employees/?q=zz&status=suspended&org_unit=4&campus=1");
    expect(server.calls.some((c) => c.path === "/org/units/?campus=1")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Clear the filters" }));
    expect(await screen.findByRole("link", { name: "Asha Persaud" })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search staff" })).toHaveValue("");
  });

  it("shows more when there are more staff than one page, and HR's own buttons", async () => {
    const onNavigate = vi.fn();
    fakeServer({
      "GET /org/units/": page([]),
      "GET /employees/": page([asha], "https://hrms.example/api/v1/employees/?page=2", 2),
      "GET /employees/?page=2": page([troy], null, 2),
    });
    render(<PeopleScreen me={hr} campusId={null} onNavigate={onNavigate} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Show more" }));
    expect(await screen.findByRole("link", { name: "Troy Benjamin" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New employee" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/new");
    await user.click(screen.getByRole("button", { name: "File scanned papers" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/scanning");
  });

  it("offers no HR buttons to others, and says when the list cannot be loaded", async () => {
    fakeServer({
      "GET /org/units/": { status: 500, body: { detail: "Server error." } },
      "GET /employees/": { status: 500, body: { code: "error", detail: "Server error." } },
    });
    render(<PeopleScreen me={auditor} campusId={null} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
    expect(screen.queryByRole("button", { name: "New employee" })).not.toBeInTheDocument();
  });
});

describe("one staff file", () => {
  const balances = {
    employee: 1,
    balances: [
      { leave_type: 1, code: "ANN", name: "Annual leave", balance: "10.00", entitlement: "14.00", pending: "2.00", available: "8.00", limited: true },
    ],
  };

  it("shows who the person is and the facts that matter most, named in the breadcrumb", async () => {
    fakeServer({
      "GET /employees/1/": { body: { ...asha, contract_type: "Fixed term", ends: "2026-11-16", probation_end: "2026-12-31" } },
      "GET /leave/ledger/balances/": { body: balances },
    });
    const frame = framed(<EmployeeFile employeeId={1} me={hr} initialTab={null} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Asha Persaud", level: 1 })).toBeInTheDocument();
    expect(frame.setCrumb).toHaveBeenCalledWith("Asha Persaud");
    expect(screen.getByText("E0001 · Lecturer, Crop Science · Department of Agriculture · Mon Repos Campus")).toBeInTheDocument();
    const facts = Object.fromEntries(
      [...document.querySelectorAll(".facts > div")].map((d) => [d.querySelector("dt")!.textContent, d.textContent]),
    );
    expect(facts.Started).toMatch(/^Started02\/09\/2019\d+ years$/);
    expect(facts.Manager).toBe("ManagerMichael ThomasDepartment of Agriculture");
    expect(await screen.findByText("8 days")).toBeInTheDocument();
    expect(document.querySelector(".facts")).toHaveTextContent("Annual leave left8 days2 days awaiting a decision");
    expect(facts.Contract).toBe("ContractFixed termEnds 16/11/2026");
    expect(facts["Probation ends"]).toBe("Probation ends31/12/2026");
  });

  it("keeps identifiers hidden until shown, records that, and hides them again", async () => {
    const server = fakeServer({
      "GET /employees/1/": { body: asha },
      "GET /leave/ledger/balances/": { body: balances },
      "POST /employees/1/reveal/": { body: { id: 1, employee_no: "E0001", national_id: "DEMO-1001", nis_no: "DEMO-NIS-0001", tin: "DEMO-T001" } },
    });
    framed(<EmployeeFile employeeId={1} me={hr} initialTab={null} onNavigate={vi.fn()} />);
    const panel = await screen.findByRole("tabpanel");
    expect(within(panel).getByRole("heading", { name: "Personal details" })).toBeInTheDocument();
    const nis = () => [...panel.querySelectorAll("dt")].find((d) => d.textContent === "NIS number")!.nextElementSibling!;
    expect(nis()).toHaveTextContent("••••••001");
    expect(panel).toHaveTextContent("Identifiers stay hidden until you show them.");
    const user = userEvent.setup();
    await user.click(within(panel).getByRole("button", { name: "Show identifiers" }));
    expect(await within(panel).findByText("DEMO-NIS-0001")).toBeInTheDocument();
    expect(panel).toHaveTextContent(/Shown at \d\d:\d\d by Natasha Khan\. Showing identifiers is recorded in the audit log\./);
    expect(server.calls.filter((c) => c.method === "POST").map((c) => c.path)).toEqual(["/employees/1/reveal/"]);
    await user.click(within(panel).getByRole("button", { name: "Hide identifiers" }));
    expect(nis()).toHaveTextContent("••••••001");
    expect(within(panel).getByText("Not recorded")).toBeInTheDocument(); // the phone number
  });

  it("opens the tab the address names, and keeps the address in step with the tab", async () => {
    fakeServer({
      "GET /employees/1/": { body: asha },
      "GET /leave/ledger/balances/": { body: balances },
      "GET /assignments/": page([]),
      "GET /documents/": page([]),
      "GET /signing/requests/": page([]),
    });
    framed(<EmployeeFile employeeId={1} me={hr} initialTab="leave" onNavigate={vi.fn()} />);
    const leaveTab = await screen.findByRole("tab", { name: "Leave" });
    expect(leaveTab).toHaveAttribute("aria-selected", "true");
    expect(within(screen.getByRole("tabpanel")).getByText("8 days (2 days awaiting a decision)")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Appointments" }));
    expect(window.location.hash).toBe("#/people/1/appointments");
    expect(await screen.findByText("No appointments.")).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Personal",
      "Appointments",
      "Contract",
      "Leave",
      "Documents",
      "Contacts",
      "Background",
      "Bank",
      "Items issued",
      "History",
    ]);
  });

  it("sends HR to the letter form from the top of the file, and to the details form", async () => {
    fakeServer({
      "GET /employees/1/": { body: asha },
      "GET /leave/ledger/balances/": { body: balances },
      "GET /documents/": page([]),
      "GET /signing/requests/": page([]),
      "GET /letters/templates/": page([]),
    });
    const onNavigate = vi.fn();
    framed(<EmployeeFile employeeId={1} me={hr} initialTab={null} onNavigate={onNavigate} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Write a letter" }));
    expect(screen.getByRole("tab", { name: "Documents" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("heading", { name: "Write a letter" })).toBeInTheDocument();
    // On the Documents tab the letter is written there, so the button at the top steps aside.
    expect(screen.queryByRole("button", { name: "Write a letter" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit details" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/1/edit");
  });

  it("lets HR add an appointment, then shows it, and lists the documents on file", async () => {
    const held = {
      id: 30,
      employee: 1,
      position: 7,
      position_title: "Laboratory Technician",
      appointment_type: "temporary",
      start_date: "2026-10-05",
      end_date: null,
      probation_end: "2027-04-05",
      confirmed_on: null,
      is_acting: false,
      status: "active",
      pay_grade_name: "GS5 step 1",
    };
    const server = fakeServer({
      "GET /employees/1/": { body: asha },
      "GET /leave/ledger/balances/": { body: balances },
      "GET /assignments/": [page([]), page([held])],
      "GET /org/positions/": page([
        { id: 7, number: "AGR-004", title: "Laboratory Technician", org_unit_name: "Department of Agriculture", is_vacant: true },
        { id: 8, number: "AGR-001", title: "Head of Department", org_unit_name: "Department of Agriculture", is_vacant: false },
      ]),
      "POST /assignments/": { status: 201, body: held },
      "GET /documents/": page([
        { id: 5, title: "Contract of employment", filename: "contract.pdf", version: 2, doc_type: "contract", classification: "confidential", download_url: "/api/v1/documents/5/download/" },
      ]),
    });
    framed(<EmployeeFile employeeId={1} me={hr} initialTab="appointments" onNavigate={vi.fn()} />);
    const form = await screen.findByRole("form", { name: "Add an appointment" });
    const user = userEvent.setup();
    const post = within(form).getByRole("combobox", { name: "Position" });
    await within(form).findByRole("option", { name: /AGR-004 Laboratory Technician/ });
    expect(within(post).getByRole("option", { name: /AGR-001 Head of Department.*filled/ })).toBeDisabled();
    await user.selectOptions(post, "7");
    await user.selectOptions(within(form).getByRole("combobox", { name: "Appointment type" }), "temporary");
    await user.type(within(form).getByLabelText("Start"), "2026-10-05");
    await user.type(within(form).getByLabelText("Probation ends (optional)"), "2027-04-05");
    await user.click(within(form).getByRole("button", { name: "Add assignment" }));
    expect(await screen.findByText("Laboratory Technician")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      employee: 1,
      position: 7,
      appointment_type: "temporary",
      start_date: "2026-10-05",
      end_date: null,
      probation_end: "2027-04-05",
      is_acting: false,
    });
    await user.click(screen.getByRole("tab", { name: "Documents" }));
    const link = await screen.findByRole("link", { name: "Contract of employment" });
    expect(link).toHaveAttribute("href", "/api/v1/documents/5/download/");
    expect(link.parentElement).toHaveTextContent("contract.pdf · v2 · contract · confidential");
  });

  it("says when an appointment is refused", async () => {
    fakeServer({
      "GET /employees/1/": { body: asha },
      "GET /leave/ledger/balances/": { body: balances },
      "GET /assignments/": page([]),
      "GET /org/positions/": page([{ id: 7, number: "AGR-004", title: "Laboratory Technician", org_unit_name: "Agriculture", is_vacant: true }]),
      "POST /assignments/": { status: 400, body: { start_date: ["The post is held on those dates."] } },
    });
    framed(<EmployeeFile employeeId={1} me={hr} initialTab="appointments" onNavigate={vi.fn()} />);
    const form = await screen.findByRole("form", { name: "Add an appointment" });
    const user = userEvent.setup();
    await within(form).findByRole("option", { name: /AGR-004/ });
    await user.selectOptions(within(form).getByRole("combobox", { name: "Position" }), "7");
    await user.click(within(form).getByRole("checkbox", { name: "Acting appointment" }));
    await user.type(within(form).getByLabelText("Start"), "2026-10-05");
    await user.click(within(form).getByRole("button", { name: "Add assignment" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("start date: The post is held on those dates.");
  });

  it("shows a role only the tabs it may open, and no HR buttons", async () => {
    const server = fakeServer({ "GET /employees/9/": { body: troy } });
    framed(<EmployeeFile employeeId={9} me={{ ...auditor, roles: ["principal"] }} initialTab="bank" onNavigate={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Troy Benjamin" })).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).not.toContain("Bank"); // the Principal does not decide bank details
    expect(tabs).toContain("History");
    expect(tabs).toContain("Leave");
    // The address named a tab this role cannot open: the file opens on Personal.
    expect(screen.getByRole("tab", { name: "Personal" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
    expect(document.querySelector(".facts")).toHaveTextContent("StartedNot appointed");
    expect(server.calls.some((c) => c.path.startsWith("/leave/ledger/balances/"))).toBe(true);
  });

  it("does not ask for leave balances a role may not read, and says when the file cannot be opened", async () => {
    const server = fakeServer({ "GET /employees/9/": { status: 404, body: { code: "not_found", detail: "Not found." } } });
    framed(<EmployeeFile employeeId={9} me={auditor} initialTab={null} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
    expect(server.calls.some((c) => c.path.startsWith("/leave/ledger/balances/"))).toBe(false);
  });
});

describe("the staff details pages", () => {
  it("opens a new file and goes to it once created", async () => {
    const server = fakeServer({
      "GET /org/campuses/": page([MRP]),
      "POST /employees/": { status: 201, body: { ...asha, id: 12 } },
    });
    const onNavigate = vi.fn();
    const frame = framed(<EmployeeFormPage me={hr} employeeId={null} campusId={1} onNavigate={onNavigate} />);
    expect(screen.getByRole("heading", { name: "New employee", level: 1 })).toBeInTheDocument();
    expect(frame.setCrumb).toHaveBeenCalledWith("New employee");
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "New employee" });
    await user.type(within(form).getByLabelText("Employee number"), "E0012");
    await user.click(within(form).getByRole("button", { name: "Cancel" }));
    expect(onNavigate).toHaveBeenCalledWith("/people");
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("edits an existing file and leads back to it", async () => {
    fakeServer({ "GET /employees/1/": { body: asha }, "GET /org/campuses/": page([MRP]) });
    const onNavigate = vi.fn();
    framed(<EmployeeFormPage me={hr} employeeId={1} campusId={null} onNavigate={onNavigate} />);
    expect(screen.getByRole("heading", { name: "Edit details", level: 1 })).toBeInTheDocument();
    const form = await screen.findByRole("form", { name: "Edit Asha Persaud" });
    expect(screen.getByText("Asha Persaud, E0001")).toBeInTheDocument();
    await userEvent.setup().click(within(form).getByRole("button", { name: "Cancel" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/1");
  });

  it("is for Human Resources only, and says when the file cannot be opened", async () => {
    fakeServer({ "GET /employees/1/": { status: 404, body: { code: "not_found", detail: "Not found." } } });
    const { unmount } = render(<EmployeeFormPage me={auditor} employeeId={null} campusId={null} onNavigate={vi.fn()} />);
    expect(screen.getByText("Only Human Resources opens and changes staff files.")).toBeInTheDocument();
    unmount();
    framed(<EmployeeFormPage me={hr} employeeId={1} campusId={null} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });
});
