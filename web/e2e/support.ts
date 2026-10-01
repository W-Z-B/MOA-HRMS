/** Helpers shared by the journeys: signing in as the fictional demonstration staff, and the axe check. */

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";

/** Demonstration accounts from seed_demo (fictional people). Their shared password comes from the environment. */
export const STAFF = {
  employee: { username: "asha.persaud", name: "Asha Persaud" },
  manager: { username: "michael.thomas", name: "Michael Thomas" },
  hr: { username: "natasha.khan", name: "Natasha Khan" },
} as const;

function password(): string {
  const value = process.env.E2E_PASSWORD;
  if (!value) throw new Error("Set E2E_PASSWORD to the DEMO_USER_PASSWORD of the test stack.");
  return value;
}

export async function signIn(page: Page, username: string) {
  await page.goto("/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
}

/** Open a main section from the side navigation, or from the bottom bar on a phone. */
export async function openSection(page: Page, label: string) {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label, exact: true }).click();
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
