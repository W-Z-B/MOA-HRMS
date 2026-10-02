import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("the auditor checks the audit log, finds what happened to a file, and downloads it", async ({ page }, testInfo) => {
  await signIn(page, STAFF.auditor.username);
  await openSection(page, "Admin");
  await page.getByRole("tab", { name: "Audit log" }).click();
  await expect(page.getByRole("list", { name: "Audit entries" })).toBeVisible();

  await page.getByRole("button", { name: "Check every entry now" }).click();
  await expect(page.getByRole("status")).toContainText(/Nothing changed or removed: \d+ entries checked/);
  await expectAccessible(page, testInfo, "audit log");

  await page.getByLabel("Who did it").fill(STAFF.auditor.username);
  await page.getByRole("button", { name: "Show", exact: true }).click();
  await expect(page.getByRole("list", { name: "Audit entries" }).getByText(/^Audit check: audit log checked$/).first()).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download as a spreadsheet (CSV)" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^gsa-hrms-audit-\d{8}-\d{4}\.csv$/);
  await signOut(page);
});
