import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("HR runs the data-quality report and opens a file from it", async ({ page }, testInfo) => {
  await signIn(page, STAFF.hr.username);
  await openSection(page, "Reports");
  await page.getByRole("button", { name: "Staff records to check" }).click();
  const table = page.getByRole("table");
  await expect(table).toBeVisible();
  // The fictional staff carry demonstration identifiers, so the report has things for HR to check.
  await expect(table.getByRole("link").first()).toBeVisible();
  await expectAccessible(page, testInfo, "data-quality report");

  const first = await table.getByRole("link").first().textContent();
  await table.getByRole("link").first().click();
  await expect(page.getByText(new RegExp(`^${first} ·`))).toBeVisible();
  await signOut(page);
});
