import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("HR finds an employee, opens the file, and sees identifiers masked until revealed", async ({ page }, testInfo) => {
  await signIn(page, STAFF.hr.username);
  await openSection(page, "People");
  await expect(page.getByRole("heading", { name: "People", level: 1 })).toBeVisible();
  await expectAccessible(page, testInfo, "people directory");

  await page.getByLabel("Search staff").fill("Persaud");
  const row = page.getByRole("row").filter({ hasText: STAFF.employee.name });
  await expect(row).toHaveCount(1);
  // Keyboard users open a file the same way: the name is a link.
  await row.getByRole("link", { name: STAFF.employee.name }).click();

  await expect(page.getByRole("heading", { name: STAFF.employee.name, level: 2 })).toBeVisible();
  const nis = page.locator("dt", { hasText: "NIS number" }).locator("xpath=following-sibling::dd[1]");
  await expect(nis).toContainText("•");
  await expectAccessible(page, testInfo, "employee file");

  await page.getByRole("button", { name: "Reveal identifiers (audited)" }).click();
  await expect(nis).toHaveText(/^DEMO-NIS-/);

  await page.getByRole("tab", { name: "Contract" }).click();
  const hours = page.locator("dt", { hasText: "Hours a week" }).locator("xpath=following-sibling::dd[1]");
  await expect(hours).toHaveText("40");
  await signOut(page);
});
