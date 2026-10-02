import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { EmergencyContact } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ContactsTab } from "./ContactsTab";

const mum: EmergencyContact = {
  id: 7,
  employee: 1,
  name: "Leela Persaud",
  relationship: "Mother",
  phone: "600-1234",
  alternate_phone: "",
  priority: 1,
};
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

describe("records on the employee file", () => {
  it("lists emergency contacts in calling order", async () => {
    fakeServer({ "GET /emergency-contacts/": page([mum]), "GET /dependants/": page([]) });
    render(<ContactsTab employeeId={1} canEdit={false} canSeeDependants />);
    const section = await screen.findByRole("region", { name: "Emergency contacts" });
    expect(await within(section).findByText("Leela Persaud")).toBeInTheDocument();
    expect(within(section).getByText(/1\. call 600-1234/)).toBeInTheDocument();
    expect(within(section).queryByRole("button")).not.toBeInTheDocument(); // read-only for this person
    expect(await screen.findByText("No dependants recorded.")).toBeInTheDocument();
  });

  it("hides dependants from roles that may not see family details", async () => {
    fakeServer({ "GET /emergency-contacts/": page([mum]) });
    render(<ContactsTab employeeId={1} canEdit={false} canSeeDependants={false} />);
    await screen.findByText("Leela Persaud");
    expect(screen.queryByRole("region", { name: "Dependants" })).not.toBeInTheDocument();
  });

  it("adds a contact through the form and sends only what was filled in", async () => {
    const server = fakeServer({
      "GET /emergency-contacts/": [page([]), page([mum])],
      "GET /dependants/": page([]),
      "POST /emergency-contacts/": { status: 201, body: mum },
    });
    render(<ContactsTab employeeId={1} canEdit canSeeDependants={false} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add an emergency contact" }));
    const form = screen.getByRole("form", { name: "Add an emergency contact" });
    await user.type(within(form).getByLabelText(/^Name/), "Leela Persaud");
    await user.type(within(form).getByLabelText(/^Phone/), "600-1234");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Leela Persaud")).toBeInTheDocument();
    const sent = server.calls.find((c) => c.method === "POST");
    expect(sent?.body).toEqual({ employee: 1, name: "Leela Persaud", phone: "600-1234" });
  });

  it("asks before removing, then removes", async () => {
    const server = fakeServer({
      "GET /emergency-contacts/": [page([mum]), page([])],
      "DELETE /emergency-contacts/7/": { status: 204 },
    });
    render(<ContactsTab employeeId={1} canEdit canSeeDependants={false} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Remove Leela Persaud" }));
    expect(server.calls.some((c) => c.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(await screen.findByText("No emergency contact. Add at least one.")).toBeInTheDocument();
  });

  it("shows the server's reason when a record is refused", async () => {
    fakeServer({
      "GET /emergency-contacts/": page([]),
      "POST /emergency-contacts/": { status: 400, body: { phone: ["Enter a phone number with at least 7 digits."] } },
    });
    render(<ContactsTab employeeId={1} canEdit canSeeDependants={false} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add an emergency contact" }));
    const form = screen.getByRole("form", { name: "Add an emergency contact" });
    await user.type(within(form).getByLabelText(/^Name/), "X");
    await user.type(within(form).getByLabelText(/^Phone/), "12");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("phone: Enter a phone number with at least 7 digits.");
  });
});
