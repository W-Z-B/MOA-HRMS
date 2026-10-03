import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Me } from "../../api/types";
import { fakeServer, offline } from "../../test/fetch";
import { LoginScreen } from "./LoginScreen";

const me = (over: Partial<Me> = {}): Me => ({
  id: 3,
  username: "natasha.khan",
  name: "Natasha Khan",
  roles: ["hr_officer"],
  mfa_required: false,
  mfa_verified: true,
  employee_id: 6,
  ...over,
});

async function signIn(username: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Username"), username);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

describe("sign-in", () => {
  it("signs in a role that needs no second factor straight away", async () => {
    const server = fakeServer({ "POST /auth/login/": { body: me() } });
    const onSignedIn = vi.fn();
    render(<LoginScreen onSignedIn={onSignedIn} />);
    await signIn("natasha.khan", "a-long-pass-phrase");
    expect(onSignedIn).toHaveBeenCalledWith(me());
    expect(server.calls[0].body).toEqual({ username: "natasha.khan", password: "a-long-pass-phrase" });
  });

  it("offers the browser's password manager the right fields", () => {
    render(<LoginScreen onSignedIn={vi.fn()} />);
    expect(screen.getByLabelText("Username")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
  });

  it("says why sign-in failed, in the server's words", async () => {
    fakeServer({ "POST /auth/login/": { status: 401, body: { code: "invalid_credentials", detail: "Username or password is incorrect." } } });
    render(<LoginScreen onSignedIn={vi.fn()} />);
    await signIn("natasha.khan", "wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("Username or password is incorrect.");
  });

  it("says plainly when the server cannot be reached", async () => {
    fakeServer({ "POST /auth/login/": offline });
    render(<LoginScreen onSignedIn={vi.fn()} />);
    await signIn("natasha.khan", "a-long-pass-phrase");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("asks a privileged role to enrol an authenticator, then verifies the code", async () => {
    const pending = me({ roles: ["hr_manager"], mfa_required: true, mfa_verified: false });
    const verified = { ...pending, mfa_verified: true };
    const server = fakeServer({
      "POST /auth/login/": { body: pending },
      "POST /auth/mfa/enrol/": { body: { provisioning_uri: "otpauth://totp/GSA%20HRMS:hr.manager?secret=ABC" } },
      "POST /auth/mfa/verify/": { body: verified },
    });
    const onSignedIn = vi.fn();
    render(<LoginScreen onSignedIn={onSignedIn} />);
    const user = await signIn("hr.manager", "a-long-pass-phrase");
    expect(onSignedIn).not.toHaveBeenCalled();
    expect(await screen.findByText(/otpauth:\/\/totp/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Enter your code" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("6-digit code"), "123 456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(onSignedIn).toHaveBeenCalledWith(verified);
    expect(server.calls.at(-1)?.body).toEqual({ code: "123456" });
  });

  it("skips enrolment for someone already enrolled and reports a wrong code", async () => {
    fakeServer({
      "POST /auth/login/": { body: me({ roles: ["finance"], mfa_required: true, mfa_verified: false }) },
      "POST /auth/mfa/enrol/": { status: 409, body: { code: "already_enrolled", detail: "A confirmed device exists." } },
      "POST /auth/mfa/verify/": { status: 400, body: { code: "invalid_code", detail: "The code is not valid." } },
    });
    render(<LoginScreen onSignedIn={vi.fn()} />);
    const user = await signIn("finance.officer", "a-long-pass-phrase");
    expect(screen.queryByText(/otpauth/)).not.toBeInTheDocument();
    await user.type(await screen.findByLabelText("6-digit code"), "000000");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The code is not valid.");
  });

  it("lets someone at the code step start again with another account, ending the half-made sign-in", async () => {
    const server = fakeServer({
      "POST /auth/login/": { body: me({ roles: ["finance"], mfa_required: true, mfa_verified: false }) },
      "POST /auth/mfa/enrol/": { status: 409, body: { code: "already_enrolled", detail: "A confirmed device exists." } },
      "POST /auth/logout/": { status: 204 },
    });
    render(<LoginScreen onSignedIn={vi.fn()} />);
    const user = await signIn("finance.officer", "a-long-pass-phrase");
    await user.click(await screen.findByRole("button", { name: "Use a different account" }));
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(server.calls.some((c) => c.method === "POST" && c.path === "/auth/logout/")).toBe(true);
  });

  it("shows the password on request, and hides it again", async () => {
    render(<LoginScreen onSignedIn={vi.fn()} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Password"), "secret-words");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("says why the person is signing in again", () => {
    render(<LoginScreen onSignedIn={vi.fn()} notice="You were signed out after 30 minutes without activity." />);
    expect(screen.getByRole("status")).toHaveTextContent("You were signed out after 30 minutes without activity.");
  });

  it("fills in the username after a password is chosen, and offers a way back in when it is forgotten", async () => {
    const onForgotPassword = vi.fn();
    render(<LoginScreen onSignedIn={vi.fn()} username="kemal.bacchus" onForgotPassword={onForgotPassword} />);
    expect(screen.getByLabelText("Username")).toHaveValue("kemal.bacchus");
    await userEvent.setup().click(screen.getByRole("button", { name: "Forgot your password?" }));
    expect(onForgotPassword).toHaveBeenCalled();
  });

  it("sends someone shown a letter from the School to the page that checks it", async () => {
    const onCheckLetter = vi.fn();
    render(<LoginScreen onSignedIn={vi.fn()} onCheckLetter={onCheckLetter} />);
    expect(screen.getByText(/Shown a letter from the School\?/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Check that it is genuine" }));
    expect(onCheckLetter).toHaveBeenCalled();
  });
});
