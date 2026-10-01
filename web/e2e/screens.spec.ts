import { openSection, signIn, signOut, STAFF, test } from "./support";

/**
 * Screenshots of the main screens for review in a pull request. Off by default; run with
 * SCREENSHOTS=1 bash scripts/e2e.sh and look in web/test-results/screens/.
 */
test.skip(!process.env.SCREENSHOTS, "screenshots are taken only when SCREENSHOTS=1");

test("main screens", async ({ page }, testInfo) => {
  const shot = async (name: string) =>
    page.screenshot({ path: `test-results/screens/${testInfo.project.name}-${name}.png`, fullPage: true });

  await signIn(page, STAFF.hr.username);
  await openSection(page, "People");
  await page.getByLabel("Search staff").fill("Persaud");
  await page.getByRole("row").filter({ hasText: STAFF.employee.name }).getByRole("link", { name: STAFF.employee.name }).click();
  await shot("employee-file");
  for (const tab of ["Background", "Contacts", "Bank", "History"]) {
    await page.getByRole("tab", { name: tab }).click();
    await page.waitForTimeout(300);
    await shot(`employee-${tab.toLowerCase()}`);
  }
  await openSection(page, "Reports");
  await page.getByRole("button", { name: "Staff records to check" }).click();
  await page.getByRole("table").waitFor();
  await shot("report-data-quality");
  await signOut(page);

  await signIn(page, STAFF.employee.username);
  await shot("employee-leave");
  await openSection(page, "My account");
  await page.getByRole("region", { name: "Where you are signed in" }).getByRole("listitem").first().waitFor();
  await shot("my-account");
  await signOut(page);
});
