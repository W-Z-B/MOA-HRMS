/** Helpers shared by the journeys: signing in as the fictional demonstration staff, and the axe check. */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { test as base, expect, type Page, type TestInfo } from "@playwright/test";

/**
 * Every journey runs with a guard: a Content-Security-Policy violation in the browser fails the test,
 * so the policy set in deploy/ can never quietly break a screen.
 */
export const test = base.extend<{ cspGuard: void }>({
  cspGuard: [
    async ({ page }, use) => {
      const violations: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error" && /Content Security Policy/i.test(message.text())) violations.push(message.text());
      });
      await use();
      expect(violations, "Content-Security-Policy violations").toEqual([]);
    },
    { auto: true },
  ],
});
export { expect };

/** Demonstration accounts from seed_demo (fictional people). Their shared password comes from the environment. */
export const STAFF = {
  employee: { username: "asha.persaud", name: "Asha Persaud" },
  manager: { username: "michael.thomas", name: "Michael Thomas" },
  hr: { username: "natasha.khan", name: "Natasha Khan" },
  // Used only by the session journey, so that ending sessions never disturbs the leave journey.
  lecturer: { username: "shanta.ramdeen", name: "Shanta Ramdeen" },
  // Not on the staff: reads the audit log and the access review, changes nothing.
  auditor: { username: "audit.reviewer", name: "Audit Reviewer" },
  // Not on the staff: decides objections (item 1.46).
  dpo: { username: "privacy.officer", name: "Privacy Officer" },
  // Not on the staff: the Principal's Home shows the establishment (item 2.30).
  principal: { username: "principal.office", name: "Office of the Principal" },
} as const;

/** Staff used only by the privacy journey, one for each browser project, each signing in first there. */
const PRIVACY_PEOPLE = {
  desktop: { username: "devon.charles", name: "Devon Charles", employeeNo: "E0007" },
  phone: { username: "troy.benjamin", name: "Troy Benjamin", employeeNo: "E0009" },
} as const;

/**
 * New starters from seed_demo, on file but with no account yet: one for each browser project, so that each
 * journey invites its own person.
 */
const NEW_STARTERS = {
  desktop: { name: "Kemal Bacchus", username: "kemal.bacchus", email: "kemal.bacchus@gsa.example" },
  phone: { name: "Petal Fredericks", username: "petal.fredericks", email: "petal.fredericks@gsa.example" },
} as const;
export const newStarter = (testInfo: TestInfo) => NEW_STARTERS[testInfo.project.name as keyof typeof NEW_STARTERS];

/** Staff used only by the letters journey, one for each browser project: each is written a letter and reads it. */
const LETTER_PEOPLE = {
  desktop: { username: "roxanne.williams", name: "Roxanne Williams" },
  phone: { username: "indira.narine", name: "Indira Narine" },
} as const;
export const letterPerson = (testInfo: TestInfo) => LETTER_PEOPLE[testInfo.project.name as keyof typeof LETTER_PEOPLE];

/** The acting appointment each browser project records: the letters journey's person, and a post of their campus. */
const CAREER_CHANGES = {
  desktop: { name: "Roxanne Williams", post: "AGR-004 Laboratory Technician" },
  phone: { name: "Indira Narine", post: "ESQ-AGR-002 Field Instructor" },
} as const;
export const careerChange = (testInfo: TestInfo) => CAREER_CHANGES[testInfo.project.name as keyof typeof CAREER_CHANGES];

/** Staff with ten years' service or more, one for each browser project, whose leaving is recorded and withdrawn. */
const LEAVERS = {
  desktop: { name: "Kwame Adams" },
  phone: { name: "Indira Narine" },
} as const;
export const leaver = (testInfo: TestInfo) => LEAVERS[testInfo.project.name as keyof typeof LEAVERS];

/** Heads of unit who name a stand-in, one for each browser project, and the colleague they name. */
const STAND_INS = {
  desktop: { username: "michael.thomas", delegate: "Shanta Ramdeen" },
  phone: { username: "natasha.khan", delegate: "Devon Charles" },
} as const;
export const standIn = (testInfo: TestInfo) => STAND_INS[testInfo.project.name as keyof typeof STAND_INS];

/** Where the test stack writes the email it would send (compose.e2e.yml). */
const MAIL_DIR = process.env.E2E_MAIL_DIR ?? "/files/mail";

function messages(): string[] {
  try {
    return readdirSync(MAIL_DIR).sort();
  } catch {
    return []; // nothing has been sent yet
  }
}

/** The email written so far. Take this before an action, then wait for what the action sends. */
export const mailbox = () => new Set(messages());

/**
 * The link in the first email to that address written after `before`: by default the one to choose a password,
 * or another page of the app, such as "confirm-email".
 */
export async function linkSentTo(address: string, before: Set<string>, page = "set-password"): Promise<string> {
  const pattern = new RegExp(String.raw`https://\S+/#/${page}/\S+`);
  for (let attempt = 0; attempt < 50; attempt++) {
    for (const name of messages().filter((n) => !before.has(n))) {
      const text = readFileSync(join(MAIL_DIR, name), "utf8");
      const link = text.includes(`To: ${address}`) && text.match(pattern);
      if (link) return link[0];
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`No email with a ${page} link reached ${address}`);
}

export function password(): string {
  const value = process.env.E2E_PASSWORD;
  if (!value) throw new Error("Set E2E_PASSWORD to the DEMO_USER_PASSWORD of the test stack.");
  return value;
}

export const privacyPerson = (testInfo: TestInfo) =>
  PRIVACY_PEOPLE[testInfo.project.name as keyof typeof PRIVACY_PEOPLE];

/**
 * After signing in: the first time, the privacy notice in force is read and acknowledged (item 1.31).
 * Returns whether it was shown.
 */
export async function passNotice(page: Page): Promise<boolean> {
  // The crest's link to Home, in the frame of every page inside: the notice screen has no frame.
  const read = page.getByRole("button", { name: "I have read this notice" });
  const inside = page.getByRole("link", { name: "GSA HRMS Home" });
  await expect(read.or(inside).first()).toBeVisible();
  const shown = await read.isVisible();
  if (shown) await read.click();
  await expect(inside).toBeVisible();
  return shown;
}

export async function signIn(page: Page, username: string) {
  await page.goto("/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password());
  await page.getByRole("button", { name: "Sign in" }).click();
  await passNotice(page);
}

/** Sign out from the person's menu, behind their initials in the header. */
export async function signOut(page: Page) {
  await page.getByRole("button", { name: /^Signed in as / }).click();
  await page.getByRole("dialog", { name: "Your account" }).getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
}

/** Open search: the bar in the header, or the Search tab at the bottom of a phone, whichever the page has. */
export async function openSearch(page: Page) {
  const tab = page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Search" });
  const bar = page.getByRole("banner").getByRole("button", { name: "Search people, pages and actions" });
  await expect(tab.or(bar)).toBeVisible();
  await tab.or(bar).click();
  await expect(page.getByRole("dialog", { name: "Search" })).toBeVisible();
}

/** Open a page as people do, with no menu to click (item 2.30): search for it by name and choose it. */
export async function openSection(page: Page, label: string) {
  await openSearch(page);
  const dialog = page.getByRole("dialog", { name: "Search" });
  await dialog.getByRole("combobox").fill(label);
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  await dialog.getByRole("group", { name: "Pages" }).getByRole("option", { name: new RegExp(`^${escaped}(,|$)`) }).click();
  await expect(dialog).toBeHidden();
}

/** Open one of Admin's sections, from the list of sections grouped by purpose (item 2.30). */
export async function openAdmin(page: Page, label: string) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  await page
    .getByRole("navigation", { name: "Admin sections" })
    .getByRole("link", { name: new RegExp(`^${escaped}( \\d+ waiting)?$`) })
    .click();
  await expect(page.locator("#admin-section-title")).toHaveText(label);
}

/**
 * WCAG 2.2 AA rules, as the gold standard requires. Serious and critical findings fail the test; every
 * finding is attached to the report so the minor ones can be worked through too. The page must also
 * fit the screen: nothing may need sideways scrolling (WCAG 1.4.10 Reflow), at desktop or phone width.
 */
export async function expectAccessible(page: Page, testInfo: TestInfo, screen: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, `${screen} is wider than the screen by ${overflow}px`).toBeLessThanOrEqual(0);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  await testInfo.attach(`axe ${screen}`, { body: JSON.stringify(results.violations, null, 2), contentType: "application/json" });
  const blocking = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(blocking, `Accessibility problems on ${screen}`).toEqual([]);
}

/**
 * Two working days well ahead of today, different for each browser project so that the journeys never
 * ask for overlapping leave. Returns ISO dates (yyyy-mm-dd), a Monday and the Tuesday after it.
 */
export function leaveDates(testInfo: TestInfo): { from: string; to: string } {
  const weeksAhead = 4 + 2 * testInfo.config.projects.findIndex((p) => p.name === testInfo.project.name);
  const day = new Date();
  day.setUTCHours(12, 0, 0, 0);
  day.setUTCDate(day.getUTCDate() + weeksAhead * 7);
  day.setUTCDate(day.getUTCDate() + ((8 - day.getUTCDay()) % 7)); // forward to a Monday
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const tuesday = new Date(day);
  tuesday.setUTCDate(day.getUTCDate() + 1);
  return { from: iso(day), to: iso(tuesday) };
}
