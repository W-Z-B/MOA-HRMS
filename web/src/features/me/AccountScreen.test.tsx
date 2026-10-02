import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { SignedInSession } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { AccountScreen } from "./AccountScreen";

const here: SignedInSession = {
  id: 1,
  device: "Chrome on Android",
  ip: "190.80.1.2",
  created_at: "2026-10-01T08:00:00-04:00",
  last_seen_at: "2026-10-01T08:30:00-04:00",
  current: true,
};
const laptop: SignedInSession = { ...here, id: 2, device: "Edge on Windows", ip: "190.80.9.9", current: false };
const tablet: SignedInSession = { ...here, id: 3, device: "Safari on iPhone or iPad", ip: null, current: false };

describe("my account", () => {
  it("lists where I am signed in and marks this device", async () => {
    fakeServer({ "GET /auth/sessions/": { body: [here, laptop] } });
    render(<AccountScreen />);
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Chrome on Android")).toBeInTheDocument();
    expect(within(items[0]).getByText("This device")).toBeInTheDocument();
    expect(within(items[0]).queryByRole("button")).not.toBeInTheDocument();
    expect(within(items[1]).getByRole("button", { name: "Sign out of Edge on Windows" })).toBeInTheDocument();
  });

  it("signs out one other device", async () => {
    const server = fakeServer({
      "GET /auth/sessions/": [{ body: [here, laptop] }, { body: [here] }],
      "DELETE /auth/sessions/2/": { status: 204 },
    });
    render(<AccountScreen />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign out of Edge on Windows" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Signed out of Edge on Windows.");
    expect(server.calls.some((c) => c.method === "DELETE" && c.path === "/auth/sessions/2/")).toBe(true);
    expect(await screen.findAllByRole("listitem")).toHaveLength(1);
  });

  it("signs out everywhere else at once", async () => {
    fakeServer({
      "GET /auth/sessions/": [{ body: [here, laptop, tablet] }, { body: [here] }],
      "POST /auth/sessions/end-others/": { body: { ended: 2 } },
    });
    render(<AccountScreen />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign out everywhere else" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Signed out of 2 other devices.");
    expect(screen.queryByRole("button", { name: "Sign out everywhere else" })).not.toBeInTheDocument();
  });

  it("changes my password and says how many other devices were signed out", async () => {
    const server = fakeServer({
      "GET /auth/sessions/": [{ body: [here, laptop] }, { body: [here] }],
      "POST /auth/password/change/": { body: { ended: 1 } },
    });
    render(<AccountScreen />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Current password"), "Old-Password-2025");
    await user.type(screen.getByLabelText("New password"), "Guava-Season-Starts-2026");
    await user.type(screen.getByLabelText("New password again"), "Guava-Season-Starts-2026");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("status")).toHaveTextContent("You were signed out on 1 other device.");
    expect(server.calls.find((c) => c.path === "/auth/password/change/")?.body).toEqual({
      current_password: "Old-Password-2025",
      new_password: "Guava-Season-Starts-2026",
    });
    expect(screen.getByLabelText("Current password")).toHaveValue("");
  });

  it("refuses two new passwords that differ, and shows the server's reasons", async () => {
    const server = fakeServer({
      "GET /auth/sessions/": { body: [here] },
      "POST /auth/password/change/": [
        { status: 400, body: { code: "wrong_password", detail: "Your current password is not right." } },
        { status: 400, body: { new_password: ["This password is too common."] } },
      ],
    });
    render(<AccountScreen />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Current password"), "not-it");
    await user.type(screen.getByLabelText("New password"), "Guava-Season-Starts-2026");
    await user.type(screen.getByLabelText("New password again"), "Guava-Season-Starts-2027");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The two new passwords are not the same.");
    expect(server.calls.some((c) => c.path === "/auth/password/change/")).toBe(false);

    await user.clear(screen.getByLabelText("New password again"));
    await user.type(screen.getByLabelText("New password again"), "Guava-Season-Starts-2026");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your current password is not right.");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("This password is too common.")).toBeInTheDocument();
  });

  it("says so when the list cannot be loaded", async () => {
    fakeServer({ "GET /auth/sessions/": { status: 500, body: { code: "error", detail: "Server error." } } });
    render(<AccountScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});
