import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("HR reads the establishment: posts and who holds them, units, salary scales, campuses and required training", async ({ page }, testInfo) => {
  await signIn(page, STAFF.hr.username);
  await openSection(page, "Organisation");
  // The chart comes first (item 2.30); the posts are a tab away.
  await expect(page.getByRole("tab", { name: "Chart" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Posts" }).click();
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

  // Required training by post (item 5.24): the list the LMS reads, kept by the HR Manager.
  await page.getByRole("tab", { name: "Required training" }).click();
  const required = page.getByRole("list", { name: "Required training" });
  await expect(required).toContainText("First aid at work");
  await expect(required.getByRole("listitem").filter({ hasText: "Safe handling of livestock" })).toContainText("post Farm Attendant");
  await expectAccessible(page, testInfo, "required training");
  await signOut(page);
});

test("the organisation chart draws units as they nest, finds a person, and prints without its controls", async ({ page }, testInfo) => {
  await signIn(page, STAFF.hr.username);
  await openSection(page, "Organisation");
  await expect(page.getByRole("list", { name: "Units under Department of Agriculture", exact: true })).toContainText("Livestock Unit");
  await expect(page.getByRole("list", { name: "Posts in Department of Agriculture", exact: true })).toContainText(STAFF.employee.name);
  await expect(page.getByRole("list", { name: "Posts in Administration" })).toContainText("Frozen");
  await expectAccessible(page, testInfo, "chart");

  const search = page.getByRole("searchbox", { name: "Find a person, post or unit" });
  await search.fill("Ramdeen");
  await expect(page.getByText("1 match.", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Posts in Department of Agriculture", exact: true })).toContainText("Lecturer, Soil Science");
  await expect(page.getByText("Livestock Unit")).toHaveCount(0);
  await search.fill("");

  await page.emulateMedia({ media: "print" });
  await expect(search).toBeHidden();
  await expect(page.getByRole("tab", { name: "Chart" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Units on Mon Repos Campus" })).toBeVisible();
  await page.emulateMedia({ media: "screen" });
  await signOut(page);
});
