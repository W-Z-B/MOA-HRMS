import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee, Me, Notification, WaitingItem } from "../api/types";
import { fakeServer } from "../test/fetch";
import { useCrumb } from "./frame";
import { Shell } from "./Shell";

const MRP = { id: 1, code: "MRP", name: "Mon Repos Campus" };
const ESQ = { id: 2, code: "ESQ", name: "Essequibo Campus" };

const hr: Me = {
  id: 6,
  username: "natasha.khan",
  name: "Natasha Khan",
  roles: ["employee", "hr_officer", "supervisor"],
  mfa_required: false,
  mfa_verified: true,
  employee_id: 6,
  position: "Human Resources Officer",
  unit: "Administration",
  heads: ["Administration"],
  campus: "Mon Repos Campus",
  campuses: [ESQ, MRP],
};
const employee: Me = {
  ...hr,
  id: 1,
  username: "asha.persaud",
  name: "Asha Persaud",
  roles: ["employee"],
  employee_id: 1,
  position: "Lecturer, Crop Science",
  unit: "Department of Agriculture",
  heads: [],
  campuses: [MRP],
};

const waiting = (n: number): WaitingItem[] =>
  Array.from({ length: n }, (_, i) => ({
    kind: "bank",
    kind_name: "Bank details to approve",
    title: `Item ${i}`,
    since: "2026-10-01T10:00:00Z",
    waited_days: 1,
    overdue: false,
    link: "/people/9",
    for_whom: "",
  }));
const note: Notification = {
  id: 4,
  kind: "alert",
  title: "Contract ends in 60 days: Troy Benjamin",
  body: "",
  link: "/people/9",
  created_at: "2026-10-02T06:00:00Z",
  read_at: null,
};
const asha = { id: 1, employee_no: "E0001", full_name: "Asha Persaud", position_title: "Lecturer, Crop Science" } as Employee;

function server(extra: Record<string, unknown> = {}) {
  return fakeServer({
    "GET /approvals/waiting/": { body: waiting(3) },
    "GET /notifications/": { body: { unread: 1, results: [note] } },
    "POST /notifications/4/read/": { status: 204 },
    "POST /auth/logout/": { status: 204 },
    ...(extra as Record<string, { body?: unknown; status?: number }>),
  });
}

function onPhone(matches: boolean) {
  vi.stubGlobal("matchMedia", (media: string) => ({
    matches,
    media,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function Named({ label }: { label: string }) {
  useCrumb(label);
  return <p>The file</p>;
}

function frame(me: Me, over: Partial<Parameters<typeof Shell>[0]> = {}) {
  const props = {
    me,
    path: "/",
    onNavigate: vi.fn(),
    onLogout: vi.fn(),
    campusId: null,
    onCampusChange: vi.fn(),
    children: <p>Page</p>,
    ...over,
  };
  return { ...render(<Shell {...props} />), props };
}

describe("the frame", () => {
  it("shows the crest's Home link, how much waits in To do, and a job title instead of role codes", async () => {
    server();
    const { props } = frame(hr);
    expect(screen.getByRole("link", { name: "GSA HRMS Home" })).toHaveAttribute("href", "#/");
    const todo = screen.getByRole("link", { name: /^To do/ });
    expect(await within(todo).findByText("3")).toBeInTheDocument();
    expect(todo).toHaveTextContent("To do 3 waiting");
    await userEvent.setup().click(todo);
    expect(props.onNavigate).toHaveBeenCalledWith("/to-do");
    expect(screen.queryByText(/hr_officer/)).not.toBeInTheDocument();
  });

  it("opens the person's menu with their title, their own pages, and Sign out", async () => {
    server();
    const { props } = frame(hr);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Signed in as Natasha Khan" }));
    const menu = screen.getByRole("dialog", { name: "Your account" });
    expect(menu).toHaveTextContent("HR Officer · Head of Administration");
    expect(within(menu).getAllByRole("link").map((a) => a.textContent)).toEqual([
      "My leaveDays left and your requests",
      "My contractYour appointment and its terms",
      "My recordWhat the School holds about you",
      "My accountPassword, sign-in email and devices",
    ]);
    await user.click(within(menu).getByRole("link", { name: /My record/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/my-record");
    expect(screen.queryByRole("dialog", { name: "Your account" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Signed in as Natasha Khan" }));
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(props.onLogout).toHaveBeenCalled();
  });

  it("closes a menu with Esc or a click outside it", async () => {
    server();
    frame(hr);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Notifications, 1 unread/ }));
    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Notifications, 1 unread/ }));
    fireEvent.click(document.querySelector(".popover-backdrop")!);
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
  });

  it("follows a notification to where it points, and marks it read", async () => {
    const calls = server().calls;
    const { props } = frame(hr);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Notifications, 1 unread/ }));
    await user.click(await screen.findByRole("button", { name: /Troy Benjamin/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/people/9");
    expect(calls.some((c) => c.method === "POST" && c.path === "/notifications/4/read/")).toBe(true);
  });

  it("offers the campus switch only to someone who works with more than one campus", async () => {
    server();
    const { props, unmount } = frame(hr, { campusId: 2 });
    const group = screen.getByRole("group", { name: "Campus" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["All campuses", "Essequibo", "Mon Repos"]);
    expect(within(group).getByRole("button", { name: "Essequibo" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.setup().click(within(group).getByRole("button", { name: "All campuses" }));
    expect(props.onCampusChange).toHaveBeenCalledWith(null);
    unmount();
    frame(employee);
    expect(screen.queryByRole("group", { name: "Campus" })).not.toBeInTheDocument();
  });

  it("leads back to Home from every page, naming the item a page has open", () => {
    server();
    const { rerender, props } = frame(hr, { path: "/people/12", children: <Named label="Asha Persaud" /> });
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Home", "People", "Asha Persaud"]);
    expect(within(crumbs).getByText("Asha Persaud")).toHaveAttribute("aria-current", "page");
    fireEvent.click(within(crumbs).getByRole("link", { name: "People" }));
    expect(props.onNavigate).toHaveBeenCalledWith("/people");
    rerender(
      <Shell {...props} path="/organisation">
        <p>Chart</p>
      </Shell>,
    );
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("Organisation")).toHaveAttribute(
      "aria-current",
      "page",
    );
    rerender(
      <Shell {...props} path="/">
        <p>Home</p>
      </Shell>,
    );
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).not.toBeInTheDocument();
  });
});

describe("search", () => {
  it("opens with Ctrl K and lists only the pages and actions this person may use", async () => {
    server();
    frame(employee);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = screen.getByRole("dialog", { name: "Search" });
    const box = within(dialog).getByRole("combobox", { name: "Search people, pages and actions" });
    expect(box).toHaveFocus();
    const pages = within(dialog).getByRole("group", { name: "Pages" });
    expect(within(pages).getAllByRole("option").map((o) => o.querySelector(".search-title")?.textContent)).toEqual([
      "To do",
      "Leave",
      "Incidents",
      "My contract",
      "My record",
      "My account",
      "Attendance",
      "Appraisals",
      "Payroll",
    ]);
    const actions = within(dialog).getByRole("group", { name: "Actions" });
    expect(within(actions).getAllByRole("option").map((o) => o.querySelector(".search-title")?.textContent)).toEqual([
      "Request leave",
      "Report an incident",
      "Ask for a correction to my record",
    ]);
    expect(within(dialog).queryByRole("group", { name: "People" })).not.toBeInTheDocument();
  });

  it("finds a person by name, moves with the arrow keys and opens with Enter", async () => {
    const calls = server({ "GET /employees/": { body: { count: 1, next: null, previous: null, results: [asha] } } }).calls;
    const { props } = frame(hr);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Search people, pages and actions/ }));
    const box = screen.getByRole("combobox");
    await user.type(box, "asha");
    const people = await screen.findByRole("group", { name: "People" });
    expect(within(people).getByRole("option")).toHaveTextContent("Asha PersaudE0001 · Lecturer, Crop Science");
    expect(calls.some((c) => c.path === "/employees/?q=asha")).toBe(true);
    expect(box).toHaveAttribute("aria-activedescendant", "search-option-0");
    expect(within(people).getByRole("option")).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}{ArrowUp}{Enter}");
    expect(props.onNavigate).toHaveBeenCalledWith("/people/1");
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
  });

  it("says when nothing matches, keeps Tab inside, and closes with Esc back where it was opened", async () => {
    server();
    frame(hr);
    const user = userEvent.setup();
    const opener = screen.getByRole("button", { name: /Search people, pages and actions/ });
    await user.click(opener);
    await user.type(screen.getByRole("combobox"), "zzzz");
    expect(screen.getByRole("status")).toHaveTextContent("Nothing matches that.");
    expect(screen.getByRole("combobox")).not.toHaveAttribute("aria-activedescendant");
    await user.tab();
    expect(screen.getByRole("combobox")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("opens a page with a click, and closes on a click outside", async () => {
    server();
    const { props } = frame(hr);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Search people, pages and actions/ }));
    await user.type(screen.getByRole("combobox"), "organ");
    await user.click(screen.getByRole("option", { name: /Organisation/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/organisation");
    await user.click(screen.getByRole("button", { name: /Search people, pages and actions/ }));
    fireEvent.mouseDown(document.querySelector(".search-backdrop")!);
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
  });
});

describe("on a phone", () => {
  it("puts Home, To do, Search and Me in tabs at the bottom, and the campus switch in Me", async () => {
    onPhone(true);
    server();
    const { props } = frame(hr);
    const tabs = screen.getByRole("navigation", { name: "Main" });
    expect(within(tabs).getAllByRole("link").map((a) => a.textContent)).toEqual(["Home", expect.stringMatching(/^To do/)]);
    expect(within(tabs).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("group", { name: "Campus" })).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(within(tabs).getByRole("button", { name: "Me" }));
    const sheet = screen.getByRole("dialog", { name: "Your account" });
    expect(within(sheet).getByRole("group", { name: "Campus" })).toBeInTheDocument();
    await user.click(within(tabs).getByRole("button", { name: "Me" }));
    expect(screen.queryByRole("dialog", { name: "Your account" })).not.toBeInTheDocument();
    await user.click(within(tabs).getByRole("button", { name: "Search" }));
    const dialog = screen.getByRole("dialog", { name: "Search" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Search people, pages and actions" }));
    expect(screen.getByRole("dialog", { name: "Search" })).toBeInTheDocument();
    await user.click(within(tabs).getByRole("link", { name: /^To do/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/to-do");
  });

  it("closes what was open when the page changes", async () => {
    onPhone(false);
    server();
    const { rerender, props } = frame(hr);
    await userEvent.setup().click(screen.getByRole("button", { name: "Signed in as Natasha Khan" }));
    expect(screen.getByRole("dialog", { name: "Your account" })).toBeInTheDocument();
    await act(async () => rerender(<Shell {...props} path="/leave" />));
    expect(screen.queryByRole("dialog", { name: "Your account" })).not.toBeInTheDocument();
  });
});
