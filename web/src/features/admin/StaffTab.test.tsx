import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { StaffTab } from "./StaffTab";

const starter: Employee = {
  id: 10,
  employee_no: "E0010",
  full_name: "Kemal Bacchus",
  first_name: "Kemal",
  last_name: "Bacchus",
  other_names: "",
  date_of_birth: "1999-01-19",
  gender: "M",
  campus: 1,
  campus_name: "Mon Repos Campus",
  status: "active",
  position_title: "Farm Attendant",
  nis_no_masked: null,
  tin_masked: null,
  national_id_masked: null,
  email: "kemal.bacchus@gsa.example",
  phone: "",
  address: "",
  user: null,
};
const noEmail: Employee = { ...starter, id: 11, employee_no: "E0011", full_name: "Petal Fredericks", email: "" };
const page = (results: Employee[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const LIST = "GET /employees/?has_account=0&status=active";

describe("staff without an account", () => {
  it("opens an account and says where the invitation went", async () => {
    const server = fakeServer({
      [LIST]: [page([starter, noEmail]), page([noEmail])],
      "POST /accounts/": { status: 201, body: { id: 14, username: "kemal.bacchus", email: starter.email, emailed: true } },
    });
    render(<StaffTab campusId={null} onNavigate={vi.fn()} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Open an account for Kemal Bacchus" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Account opened for Kemal Bacchus, username kemal.bacchus. The invitation to choose a password was sent to kemal.bacchus@gsa.example.",
    );
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ employee: 10 });
    expect(screen.queryByText("Kemal Bacchus")).not.toBeInTheDocument();
  });

  it("asks for an email address before an account can be opened", async () => {
    fakeServer({ [LIST]: page([noEmail]) });
    const onNavigate = vi.fn();
    render(<StaffTab campusId={null} onNavigate={onNavigate} />);
    expect(await screen.findByText("No email address on file")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Open an account/ })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("link", { name: "Add an email address first" }));
    expect(onNavigate).toHaveBeenCalledWith("/people/11");
  });

  it("says when the invitation could not be sent", async () => {
    fakeServer({
      [LIST]: page([starter]),
      "POST /accounts/": { status: 201, body: { id: 14, username: "kemal.bacchus", email: starter.email, emailed: false } },
    });
    render(<StaffTab campusId={null} onNavigate={vi.fn()} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Open an account for Kemal Bacchus" }));
    expect(await screen.findByRole("status")).toHaveTextContent("the invitation could not be sent");
  });

  it("shows the server's refusal", async () => {
    fakeServer({
      [LIST]: page([starter]),
      "POST /accounts/": { status: 409, body: { code: "email_in_use", detail: "Another account already uses that email address." } },
    });
    render(<StaffTab campusId={null} onNavigate={vi.fn()} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Open an account for Kemal Bacchus" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another account already uses that email address.");
  });

  it("finds staff on the campus chosen in the top bar, and says when everyone has an account", async () => {
    const server = fakeServer({ "GET /employees/?has_account=0&status=active&q=E00&campus=2": page([]) });
    render(<StaffTab campusId={2} onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Find a member of staff"), "E00");
    await user.click(screen.getByRole("button", { name: "Find" }));
    expect(await screen.findByText("Every member of staff here has an account.")).toBeInTheDocument();
    expect(server.calls.at(-1)?.path).toBe("/employees/?has_account=0&status=active&q=E00&campus=2");
  });
});
