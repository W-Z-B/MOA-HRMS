import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee, Incident, Me, MyIncident, MySafetyAction } from "../../api/types";
import { localToday } from "../../app/format";
import { fakeServer } from "../../test/fetch";
import { IncidentsScreen } from "./IncidentsScreen";

const person = (roles: string[], employee_id: number | null = 6): Me => ({
  id: 3,
  username: "natasha.khan",
  name: "Natasha Khan",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

const reported: MyIncident = {
  id: 1,
  reference: "IN-2026-001",
  kind: "accident",
  kind_name: "Accident",
  occurred_at: "2026-09-30T13:30:00Z",
  campus_name: "Mon Repos Campus",
  place: "Feed mill",
  description: "Slipped on spilt feed",
  state: "reported",
  state_name: "Reported",
  reported_by_me: true,
  my_injury: { injury: "Sprained ankle", treatment_name: "", off_work_from: "2026-09-30", back_at_work_on: null, nis_form_on: null },
};
const action: MySafetyAction = { id: 5, reference: "IN-2026-001", place: "Feed mill", what: "Fit a guard to the mixer", due_on: "2026-10-01", done_on: null, overdue: true };

const incident: Incident = {
  id: 1,
  reference: "IN-2026-001",
  kind: "accident",
  kind_name: "Accident",
  occurred_at: "2026-09-26T13:30:00Z",
  campus: 1,
  campus_name: "Mon Repos Campus",
  org_unit: 2,
  org_unit_name: "Livestock Unit",
  place: "Feed mill",
  state: "investigating",
  state_name: "Being looked into",
  people_hurt: 1,
  notices_overdue: true,
  industrial: true,
  description: "Slipped on spilt feed",
  immediate_action: "First aid given",
  reported_by: "Asha Persaud",
  created_at: "2026-09-26T14:00:00Z",
  cause: "",
  investigated_on: null,
  investigated_by: null,
  closed_on: null,
  closed_by: null,
  people: [
    {
      id: 7,
      who: "staff",
      who_name: "Member of staff",
      employee: 1,
      name: "Asha Persaud",
      injury: "Sprained left ankle",
      treatment: "doctor",
      treatment_name: "Doctor or clinic",
      off_work_from: "2026-09-26",
      back_at_work_on: null,
      days_off: 6,
      died_on: null,
      nis_form_on: null,
    },
  ],
  notices: [],
  duties: [
    {
      duty: "disablement",
      duty_name: "A worker kept from full wages for more than a day",
      section: "69(1)(b)",
      person: 7,
      person_name: "Asha Persaud",
      due_on: "2026-09-30",
      overdue: true,
      to: [
        { recipient: "authority", recipient_name: "The Occupational Safety and Health Authority", sent_on: "2026-09-29" },
        { recipient: "workers", recipient_name: "The safety and health committee, representative or trade union", sent_on: null },
      ],
    },
  ],
  actions: [{ id: 5, what: "Fit a guard to the mixer", owner: 4, owner_name: "Kwame Adams", due_on: "2026-10-01", done_on: null, done_note: "", overdue: true }],
  outstanding: ["Record what the investigation found"],
};
const staff = [
  { id: 1, full_name: "Asha Persaud", employee_no: "E0001", user: 10 },
  { id: 4, full_name: "Kwame Adams", employee_no: "E0004", user: 11 },
] as Employee[];

describe("incidents", () => {
  it("lets anyone report, says HR is told, and shows their own report without the register", async () => {
    const server = fakeServer({
      "GET /incidents/mine/": [{ body: [] }, { body: [reported] }],
      "GET /incidents/actions/mine/": { body: [] },
      "GET /org/campuses/": page([{ id: 1, code: "MRP", name: "Mon Repos Campus" }]),
      "GET /org/units/": page([{ id: 2, name: "Livestock Unit", campus: 1 }]),
      "POST /incidents/": { status: 201, body: reported },
    });
    render(<IncidentsScreen me={person(["employee"])} incidentId={null} onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Report an incident" }));
    const form = screen.getByRole("form", { name: "Report an incident" });
    await user.click(within(form).getByRole("radio", { name: /A near miss/ }));
    await user.click(within(form).getByRole("radio", { name: /An accident/ }));
    await user.type(within(form).getByLabelText("When"), "2026-09-30T09:30");
    await within(form).findByRole("option", { name: "Mon Repos Campus" });
    await user.selectOptions(within(form).getByLabelText("Campus"), "1");
    await within(form).findByRole("option", { name: "Livestock Unit" });
    await user.selectOptions(within(form).getByLabelText("Farm, workshop or unit"), "2");
    await user.type(within(form).getByLabelText("Exactly where"), "Feed mill");
    await user.click(within(form).getByRole("checkbox", { name: /industrial place/ }));
    await user.type(within(form).getByLabelText("What happened"), "Slipped on spilt feed");
    await user.click(within(form).getByRole("checkbox", { name: "I was hurt" }));
    await user.type(within(form).getByLabelText(/Your injury/), "Sprained ankle");
    await user.click(within(form).getByRole("button", { name: "Send the report" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Reported as IN-2026-001. Human Resources has been told.");
    expect(server.calls.find((c) => c.method === "POST" && c.path === "/incidents/")?.body).toEqual({
      kind: "accident",
      occurred_at: "2026-09-30T09:30",
      campus: 1,
      org_unit: 2,
      place: "Feed mill",
      industrial: true,
      description: "Slipped on spilt feed",
      immediate_action: "",
      hurt: true,
      injury: "Sprained ankle",
    });
    const mine = await screen.findByRole("list", { name: "Reported by you, or about you" });
    expect(mine).toHaveTextContent("IN-2026-001 accident at Feed mill");
    expect(mine).toHaveTextContent("You were hurt: Sprained ankle; off work from 30/09/2026");
    expect(screen.queryByRole("heading", { name: "The register" })).not.toBeInTheDocument();
    expect(server.calls.some((c) => c.path.startsWith("/incidents/?") || c.path === "/incidents/" && c.method === "GET")).toBe(false);
  });

  it("shows a refused report in words, and someone without a staff record is not asked if they were hurt", async () => {
    fakeServer({
      "GET /incidents/mine/": { body: [] },
      "GET /incidents/actions/mine/": { body: [] },
      "GET /org/campuses/": page([{ id: 1, code: "MRP", name: "Mon Repos Campus" }]),
      "GET /org/units/": page([]),
      "GET /incidents/": page([]),
      "POST /incidents/": { status: 400, body: { code: "future", detail: "An incident is reported once it has happened." } },
    });
    render(<IncidentsScreen me={person(["auditor"], null)} incidentId={null} onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Report an incident" }));
    const form = screen.getByRole("form", { name: "Report an incident" });
    expect(within(form).queryByRole("checkbox", { name: "I was hurt" })).not.toBeInTheDocument();
    await user.type(within(form).getByLabelText("When"), "2026-09-30T09:30");
    await within(form).findByRole("option", { name: "Mon Repos Campus" });
    await user.selectOptions(within(form).getByLabelText("Campus"), "1");
    await user.type(within(form).getByLabelText("Exactly where"), "Workshop");
    await user.type(within(form).getByLabelText("What happened"), "A lathe guard came off");
    await user.click(within(form).getByRole("button", { name: "Send the report" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("An incident is reported once it has happened.");
    await user.click(within(form).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Report an incident" })).not.toBeInTheDocument();
    expect(await screen.findByText("Nothing in the register.")).toBeInTheDocument();
  });

  it("lets the owner of a safety action mark it done", async () => {
    const server = fakeServer({
      "GET /incidents/mine/": { body: [] },
      "GET /incidents/actions/mine/": [{ body: [action] }, { body: [] }],
      "POST /incidents/actions/5/done/": { body: { ...action, done_on: localToday() } },
    });
    render(<IncidentsScreen me={person(["employee"])} incidentId={null} onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    const done = await screen.findByRole("form", { name: "Mark done: Fit a guard to the mixer" });
    expect(screen.getByText("Late")).toBeInTheDocument();
    await user.type(within(done).getByLabelText(/What was done/), "Guard fitted");
    await user.click(within(done).getByRole("button", { name: "Mark done" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Marked done. Thank you.");
    expect(server.calls.find((c) => c.path === "/incidents/actions/5/done/")?.body).toEqual({ done_on: localToday(), note: "Guard fitted" });
    expect(screen.queryByRole("heading", { name: "Actions given to you" })).not.toBeInTheDocument();
  });

  it("gives HR the register, the notices due and the forms that keep it", async () => {
    const sent = { ...incident, notices_overdue: false, duties: [{ ...incident.duties[0], overdue: false, to: incident.duties[0].to.map((t) => ({ ...t, sent_on: "2026-09-29" })) }] };
    const server = fakeServer({
      "GET /incidents/mine/": { body: [] },
      "GET /incidents/actions/mine/": { body: [] },
      "GET /incidents/": page([incident]),
      "GET /incidents/1/": [{ body: incident }, { body: { ...sent, actions: [{ ...incident.actions[0], done_on: "2026-10-02", done_note: "" }] } }],
      "GET /employees/": page(staff),
      "POST /incidents/1/notices/": { body: sent },
      "PATCH /incidents/1/people/7/": { body: { ...sent, people: [{ ...incident.people[0], back_at_work_on: "2026-10-01", days_off: 5 }] } },
      "POST /incidents/1/people/": { body: { ...sent, people: [...incident.people, { ...incident.people[0], id: 8, who: "visitor", who_name: "Visitor", employee: null, name: "B. Visitor", injury: "Bruise" }] } },
      "POST /incidents/1/investigation/": { body: { ...sent, cause: "Feed not swept up", investigated_on: "2026-10-01", investigated_by: "Natasha Khan" } },
      "POST /incidents/1/actions/": { body: { ...sent, actions: [...incident.actions, { ...incident.actions[0], id: 6, what: "Sweep daily" }] } },
      "POST /incidents/actions/5/done/": { body: { ...action, done_on: "2026-10-02" } },
      "POST /incidents/1/close/": [
        { status: 400, body: { code: "outstanding", detail: "Not yet: Record what the investigation found." } },
        { body: { ...sent, state: "closed", state_name: "Closed", closed_on: "2026-10-02", closed_by: "Natasha Khan" } },
      ],
    });
    const onNavigate = vi.fn();
    const { rerender } = render(<IncidentsScreen me={person(["hr_officer"])} incidentId={null} onNavigate={onNavigate} />);
    const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Incidents" });
    expect(table).toHaveTextContent("Notice late");
    await user.click(within(table).getByRole("button", { name: "IN-2026-001" }));
    expect(onNavigate).toHaveBeenCalledWith("/incidents/1");
    rerender(<IncidentsScreen me={person(["hr_officer"])} incidentId={1} onNavigate={onNavigate} />);

    expect(await screen.findByRole("heading", { name: "IN-2026-001: accident at Feed mill" })).toBeInTheDocument();
    const notices = screen.getByRole("list", { name: "Notices the Act requires" });
    expect(notices).toHaveTextContent("A worker kept from full wages for more than a day (Asha Persaud), section 69(1)(b): due 30/09/2026");
    expect(notices).toHaveTextContent("The safety and health committee, representative or trade union: not sent");
    expect(screen.getByRole("list", { name: "People hurt" })).toHaveTextContent("Sprained left ankle; doctor or clinic · off work from 26/09/2026, not back yet (6 days)");

    const record = screen.getByRole("form", { name: "Record a notice sent" });
    await user.type(within(record).getByLabelText("Sent on"), "2026-10-01");
    await user.type(within(record).getByLabelText("How"), "By hand");
    await user.click(within(record).getByRole("button", { name: "Record a notice sent" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The notice is recorded.");
    expect(server.calls.find((c) => c.path === "/incidents/1/notices/")?.body).toEqual({
      duty: "disablement",
      recipient: "workers",
      person: 7,
      sent_on: "2026-10-01",
      how: "By hand",
      their_reference: "",
    });

    await user.click(screen.getByText("Update Asha Persaud", { selector: "summary" }));
    const update = screen.getByRole("form", { name: "Update Asha Persaud" });
    await user.type(within(update).getByLabelText("Back at work on"), "2026-10-01");
    await user.click(within(update).getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/to 01\/10\/2026 \(5 days\)/)).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({
      injury: "Sprained left ankle",
      treatment: "doctor",
      off_work_from: "2026-09-26",
      back_at_work_on: "2026-10-01",
      nis_form_on: null,
      died_on: null,
    });

    const add = screen.getByRole("form", { name: "Record someone hurt" });
    await user.selectOptions(within(add).getByLabelText("Who"), "visitor");
    await user.type(within(add).getByLabelText("Name"), "B. Visitor");
    await user.type(within(add).getByLabelText(/Injury or illness/), "Bruise");
    await user.click(within(add).getByRole("button", { name: "Record someone hurt" }));
    expect(await screen.findByText("B. Visitor")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/incidents/1/people/")?.body).toEqual({
      who: "visitor",
      employee: null,
      name: "B. Visitor",
      injury: "Bruise",
      treatment: "",
      off_work_from: null,
    });

    const close = screen.getByRole("button", { name: "Close the incident" });
    await user.click(close);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not yet: Record what the investigation found.");

    const found = screen.getByRole("form", { name: "Record what the investigation found" });
    await user.type(within(found).getByLabelText("Why it happened"), "Feed not swept up");
    await user.type(within(found).getByLabelText("Found on"), "2026-10-01");
    await user.click(within(found).getByRole("button", { name: "Record what the investigation found" }));
    expect(await screen.findByText(/Found 01\/10\/2026 by Natasha Khan/)).toBeInTheDocument();

    const give = screen.getByRole("form", { name: "Give someone an action" });
    await user.type(within(give).getByLabelText("What will be done"), "Sweep daily");
    await within(give).findByRole("option", { name: "Kwame Adams" });
    await user.selectOptions(within(give).getByLabelText("By whom"), "4");
    await user.type(within(give).getByLabelText("By when"), "2026-10-09");
    await user.click(within(give).getByRole("button", { name: "Give someone an action" }));
    expect(await screen.findByText("Sweep daily")).toBeInTheDocument();

    const mark = screen.getAllByRole("form", { name: "Mark done: Fit a guard to the mixer" })[0];
    await user.click(within(mark).getByRole("button", { name: "Mark done" }));
    expect(await screen.findByText(/done 02\/10\/2026/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close the incident" }));
    expect(await screen.findByText(/Closed 02\/10\/2026 by Natasha Khan\. Recording a death/)).toBeInTheDocument();
  });

  it("shows supervisors the register without anyone's injury, and no forms", async () => {
    const hidden = {
      ...incident,
      duties: [],
      kind: "dangerous" as const,
      kind_name: "Dangerous occurrence",
      people: [{ ...incident.people[0], injury: null, treatment: null, treatment_name: null, off_work_from: null, days_off: null }],
    };
    fakeServer({
      "GET /incidents/mine/": { body: [] },
      "GET /incidents/actions/mine/": { body: [] },
      "GET /incidents/": page([hidden]),
      "GET /incidents/1/": { body: hidden },
    });
    render(<IncidentsScreen me={person(["supervisor"])} incidentId={1} onNavigate={vi.fn()} />);
    expect(await screen.findByText("None: away from an industrial establishment the Act asks for no notice of a dangerous occurrence.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "People hurt" })).not.toHaveTextContent("ankle");
    expect(screen.getByText("What an injury was is read only by Human Resources.")).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close the incident" })).not.toBeInTheDocument();
  });

  it("says when an incident is not one the person may see", async () => {
    fakeServer({
      "GET /incidents/mine/": { body: [] },
      "GET /incidents/actions/mine/": { body: [] },
      "GET /incidents/": page([]),
      "GET /incidents/9/": { status: 404, body: { detail: "Not found." } },
    });
    render(<IncidentsScreen me={person(["principal"])} incidentId={9} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Not found|not one you may see/);
  });
});
