import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer, offline } from "../../test/fetch";
import { ForgotPasswordScreen } from "./ForgotPasswordScreen";
import { SetPasswordScreen } from "./SetPasswordScreen";

const CHOSEN = "Guava-Season-Starts-2026";

function open(over: { onDone?: () => void; onAskAgain?: () => void } = {}) {
  const onDone = over.onDone ?? vi.fn();
  const onAskAgain = over.onAskAgain ?? vi.fn();
  render(<SetPasswordScreen uid="MTQ" token="abc-123" onDone={onDone} onAskAgain={onAskAgain} />);
  return { onDone, onAskAgain };
}

async function choose(first: string, second = first) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("New password"), first);
  await user.type(screen.getByLabelText("New password again"), second);
  await user.click(screen.getByRole("button", { name: "Save my password" }));
  return user;
}

describe("choosing a password from an emailed link", () => {
  it("welcomes someone invited, with their username, and saves their own password", async () => {
    const server = fakeServer({
      "POST /auth/password/check/": { body: { username: "kemal.bacchus", kind: "invitation" } },
      "POST /auth/password/set/": { body: { username: "kemal.bacchus", kind: "invitation" } },
    });
    const { onDone } = open();
    expect(await screen.findByRole("heading", { name: "Welcome: choose your password" })).toBeInTheDocument();
    expect(screen.getByText("kemal.bacchus")).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    await choose(CHOSEN);
    expect(onDone).toHaveBeenCalledWith("kemal.bacchus");
    expect(server.calls.at(-1)?.body).toEqual({ uid: "MTQ", token: "abc-123", password: CHOSEN });
  });

  it("will not send two passwords that differ", async () => {
    const server = fakeServer({ "POST /auth/password/check/": { body: { username: "asha.persaud", kind: "reset" } } });
    open();
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
    await choose(CHOSEN, `${CHOSEN}!`);
    expect(screen.getByRole("alert")).toHaveTextContent("The two passwords are not the same.");
    expect(server.calls).toHaveLength(1);
  });

  it("lists every rule the password breaks, in the server's words", async () => {
    fakeServer({
      "POST /auth/password/check/": { body: { username: "asha.persaud", kind: "reset" } },
      "POST /auth/password/set/": {
        status: 400,
        body: { password: ["This password is too short.", "This password is too common."] },
      },
    });
    open();
    await choose("password");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This password is too short.");
    expect(alert).toHaveTextContent("This password is too common.");
  });

  it("shows the password on request", async () => {
    fakeServer({ "POST /auth/password/check/": { body: { username: "asha.persaud", kind: "reset" } } });
    open();
    const field = await screen.findByLabelText("New password");
    expect(field).toHaveAttribute("type", "password");
    await userEvent.setup().click(screen.getByLabelText("Show the password"));
    expect(field).toHaveAttribute("type", "text");
  });

  it("says when a link has expired or been used, and offers a new one", async () => {
    fakeServer({
      "POST /auth/password/check/": {
        status: 400,
        body: { code: "invalid_link", detail: "This link has expired or has already been used." },
      },
    });
    const { onAskAgain } = open();
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has expired or has already been used.");
    await userEvent.setup().click(screen.getByRole("button", { name: "Ask for a new link" }));
    expect(onAskAgain).toHaveBeenCalled();
  });

  it("says so when the link stops working while the page is open", async () => {
    fakeServer({
      "POST /auth/password/check/": { body: { username: "asha.persaud", kind: "reset" } },
      "POST /auth/password/set/": { status: 400, body: { code: "invalid_link", detail: "This link has expired." } },
    });
    open();
    await choose(CHOSEN);
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has expired.");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });

  it("says plainly when the server cannot be reached", async () => {
    fakeServer({
      "POST /auth/password/check/": { body: { username: "asha.persaud", kind: "reset" } },
      "POST /auth/password/set/": offline,
    });
    open();
    await choose(CHOSEN);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("says plainly when the link cannot be checked", async () => {
    fakeServer({ "POST /auth/password/check/": offline });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });
});

describe("asking for a link", () => {
  it("gives the same answer whoever is asked for, and offers the way back", async () => {
    const answer = "If that is the username or email address of an account, a link is on its way.";
    const server = fakeServer({ "POST /auth/password/forgot/": { body: { detail: answer } } });
    const onBack = vi.fn();
    render(<ForgotPasswordScreen onBack={onBack} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Username or email address"), "kemal.bacchus");
    await user.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(await screen.findByRole("status")).toHaveTextContent(answer);
    expect(server.calls[0].body).toEqual({ login: "kemal.bacchus" });
    await user.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(onBack).toHaveBeenCalled();
  });

  it("says when one network has asked too often", async () => {
    fakeServer({
      "POST /auth/password/forgot/": {
        status: 429,
        body: { code: "too_many_attempts", detail: "Too many requests from this network. Try again in 15 minutes." },
      },
    });
    render(<ForgotPasswordScreen onBack={vi.fn()} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Username or email address"), "someone");
    await user.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 15 minutes.");
  });

  it("says plainly when the server cannot be reached", async () => {
    fakeServer({ "POST /auth/password/forgot/": offline });
    render(<ForgotPasswordScreen onBack={vi.fn()} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Username or email address"), "someone");
    await user.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });
});
