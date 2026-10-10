import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CheckedApplication } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ApplicationStatusScreen } from "./ApplicationStatusScreen";

const found: CheckedApplication = {
  found: true,
  detail: "Found. This is the current stage of your application.",
  reference: "GSA-APP-AB12-CD34",
  vacancy: "Livestock Instructor",
  state: "shortlisted",
  state_label: "Shortlisted",
  submitted_at: "2026-10-01T12:00:00Z",
};
const nothing: CheckedApplication = {
  found: false,
  detail: "No application matches that reference and code. Check them against the email you were sent.",
  reference: null,
  vacancy: null,
  state: null,
  state_label: null,
  submitted_at: null,
};

async function fill(reference: string, code: string) {
  const user = userEvent.setup();
  const form = screen.getByRole("form", { name: "Check an application" });
  await user.type(within(form).getByLabelText("Reference"), reference);
  await user.type(within(form).getByLabelText("Code"), code);
  await user.click(within(form).getByRole("button", { name: "Check my application" }));
  return user;
}

describe("checking an application without an account", () => {
  it("shows where the application stands", async () => {
    const server = fakeServer({ "POST /recruitment/check/": { body: found } });
    render(<ApplicationStatusScreen onBack={vi.fn()} />);
    await fill("GSA-APP-AB12-CD34", "K0Q1-9XMB-4T3V");
    expect(await screen.findByText(/Livestock Instructor:/)).toBeInTheDocument();
    expect(screen.getByText("Shortlisted")).toBeInTheDocument();
    expect(server.calls[0].body).toEqual({ reference: "GSA-APP-AB12-CD34", code: "K0Q1-9XMB-4T3V" });
  });

  it("gives the same answer for a wrong code as for an unknown reference", async () => {
    fakeServer({ "POST /recruitment/check/": { body: nothing } });
    render(<ApplicationStatusScreen onBack={vi.fn()} />);
    await fill("GSA-APP-0000-0000", "WRONG-CODE-0000");
    expect(await screen.findByRole("alert")).toHaveTextContent("No application matches that reference and code.");
  });

  it("goes back to sign-in", async () => {
    const onBack = vi.fn();
    render(<ApplicationStatusScreen onBack={onBack} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Go to the sign-in page" }));
    expect(onBack).toHaveBeenCalled();
  });
});
