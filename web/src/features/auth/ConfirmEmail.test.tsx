import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { ConfirmEmailScreen } from "./ConfirmEmailScreen";

describe("confirming a new sign-in email address", () => {
  it("changes nothing until the button is pressed, then says where links will go", async () => {
    const server = fakeServer({
      "POST /auth/email/confirm/": { body: { detail: "The sign-in email address is now asha.new@gsa.example.", email: "asha.new@gsa.example" } },
    });
    const onDone = vi.fn();
    render(<ConfirmEmailScreen token="abc123" onDone={onDone} />);
    expect(server.calls).toHaveLength(0); // a mail program opening the link changes nothing
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm the new address" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The sign-in email address is now asha.new@gsa.example.");
    expect(server.calls[0].body).toEqual({ token: "abc123" });
    await user.click(screen.getByRole("button", { name: "Go to the GSA HRMS" }));
    expect(onDone).toHaveBeenCalled();
  });

  it("says when the link has expired or was replaced, and when the server is out of reach", async () => {
    fakeServer({
      "POST /auth/email/confirm/": [
        { status: 400, body: { code: "expired", detail: "This link has expired, has been used, or was replaced by a newer one." } },
        () => {
          throw new TypeError("Failed to fetch");
        },
      ],
    });
    render(<ConfirmEmailScreen token="old" onDone={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm the new address" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has expired");
    await user.click(screen.getByRole("button", { name: "Confirm the new address" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });
});
