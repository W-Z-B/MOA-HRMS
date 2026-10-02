import type { Page } from "@playwright/test";
import { expect, expectAccessible, leaveDates, openSection, signIn, signOut, STAFF, test } from "./support";

/**
 * The leave brief of 29 September 2026, end to end: the employee asks on a phone, their own manager
 * approves, Human Resources gives the final approval, and the employee gets a receipt with the days left.
 */
test.describe.configure({ mode: "serial" });

async function requestCard(page: Page, who: string) {
  return page.locator("article.request").filter({ hasText: who }).first();
}

test("employee asks for two days of annual leave", async ({ page }, testInfo) => {
  const { from, to } = leaveDates(testInfo);
  await signIn(page, STAFF.employee.username);
  await expect(page.getByRole("region", { name: "Days you have left" })).toBeVisible();

  await page.getByLabel("Leave type").selectOption({ label: "Annual leave" });
  await page.getByLabel("First day").fill(from);
  await page.getByLabel("Last day").fill(to);
  await expect(page.locator(".check")).toContainText("of leave");
  await expectAccessible(page, testInfo, "leave request form");

  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByRole("status").filter({ hasText: "for approval" })).toHaveText(
    `Sent to ${STAFF.manager.name} for approval.`,
  );
  const mine = page.locator("article.request").filter({ hasText: "With the manager" }).first();
  await expect(mine).toContainText("Annual leave");
  await signOut(page);
});

test("their manager approves it", async ({ page }, testInfo) => {
  await signIn(page, STAFF.manager.username);
  await openSection(page, "Leave");
  await page.getByRole("tab", { name: /To decide/ }).click();
  const card = await requestCard(page, STAFF.employee.name);
  await expect(card).toContainText("With the manager");
  await expectAccessible(page, testInfo, "leave decisions");
  await card.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Approved" })).toHaveText(
    "Approved. It is now with Human Resources.",
  );
  await signOut(page);
});

test("Human Resources gives the final approval", async ({ page }) => {
  await signIn(page, STAFF.hr.username);
  await openSection(page, "Leave");
  await page.getByRole("tab", { name: /To decide/ }).click();
  const card = await requestCard(page, STAFF.employee.name);
  await expect(card).toContainText("With Human Resources");
  await card.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Approved" })).toHaveText(
    `Approved. ${STAFF.employee.name} has been sent a receipt.`,
  );
  await signOut(page);
});

test("the employee opens the receipt with the days left", async ({ page }, testInfo) => {
  await signIn(page, STAFF.employee.username);
  const approved = page.locator("article.request").filter({ hasText: "Approved" }).first();
  await approved.getByRole("button", { name: "View receipt" }).click();
  await expect(page.getByRole("heading", { name: "Leave approved" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Days you have left" })).toBeVisible();
  await expect(page.getByText(STAFF.manager.name)).toBeVisible();
  await expect(page.getByText(STAFF.hr.name)).toBeVisible();
  await expectAccessible(page, testInfo, "leave receipt");
  await page.getByRole("button", { name: "Back to leave" }).click();
  await signOut(page);
});
