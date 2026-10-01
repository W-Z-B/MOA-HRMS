import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("HR reads the establishment: posts and who holds them, units, salary scales and campuses", async ({ page }, testInfo) => {
  await signIn(page, STAFF.hr.username);
  await openSection(page, "Organisation");
  const posts = page.getByRole("table", { name: "Posts" });
  // By the cell's own text: on a phone each cell also shows its column's name.
  const post = (number: string) => posts.locator("tr").filter({ has: page.locator("td", { hasText: new RegExp(`^${number}$`) }) });
  await expect(post("AGR-002")).toContainText(STAFF.employee.name);
  await expect(post("ADM-003")).toContainText("Frozen");
  await expectAccessible(page, testInfo, "posts");

  await page.getByRole("tab", { name: "Units" }).click();
  const livestock = page.getByRole("list", { name: "Units" }).getByRole("listitem").filter({ hasText: "Livestock Unit" });
  await expect(livestock).toContainText("under Department of Agriculture");
  await expectAccessible(page, testInfo, "units");

  await page.getByRole("tab", { name: "Salary scales" }).click();
  await expect(page.getByRole("table", { name: "Grades on scale GS" })).toContainText("G$250,000.00");
  await expectAccessible(page, testInfo, "salary scales");

  await page.getByRole("tab", { name: "Campuses" }).click();
  await expect(page.getByRole("list", { name: "Campuses" })).toContainText("Essequibo Campus");
  await expectAccessible(page, testInfo, "campuses");
  await signOut(page);
});
