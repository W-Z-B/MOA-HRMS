import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("HR files a pile of scanned papers, each into the record its name gives", async ({ page }, testInfo) => {
  const tag = testInfo.project.name; // each browser files its own papers, so neither is a copy of the other
  const pdf = (name: string) => ({ name, mimeType: "application/pdf", buffer: Buffer.from(`%PDF-1.4\n% ${name}\n%%EOF\n`) });
  await signIn(page, STAFF.hr.username);
  await openSection(page, "People");
  await page.getByRole("button", { name: "File scanned papers" }).click();

  const begin = page.getByRole("form", { name: "Begin a batch" });
  await begin.getByLabel("The papers are").selectOption("letter");
  await begin.getByLabel(/Note/).fill(`Cabinet 2, ${tag}`);
  await begin.getByRole("button", { name: "Begin" }).click();
  await page.getByLabel(/Choose the scanned files/).setInputFiles([pdf(`E0001 Old appointment ${tag}.pdf`), pdf(`scan ${tag}.pdf`)]);
  await expect(page.getByRole("status")).toHaveText("1 of 2 filed.");
  const files = page.getByRole("list", { name: "Files in this batch" });
  await expect(files).toContainText(`filed in the record of ${STAFF.employee.name} (E0001) as “Old appointment ${tag}”`);
  await expect(files).toContainText("The name does not start with an employee number.");

  const place = page.getByRole("form", { name: `Choose whose file scan ${tag}.pdf belongs in` });
  await place.getByLabel("Whose file").selectOption({ label: `${STAFF.employee.name} (E0001)` });
  await place.getByRole("button", { name: "File it there" }).click();
  await expect(page.getByRole("status")).toHaveText("2 of 2 filed.");
  await expect(page.getByRole("table", { name: "Batches filed" })).toContainText(`Cabinet 2, ${tag}`);
  await expectAccessible(page, testInfo, "filing scanned papers");

  await page.getByRole("button", { name: "Back to People" }).click();
  await page.getByLabel("Search staff").fill("Persaud");
  await page.getByRole("row").filter({ hasText: STAFF.employee.name }).getByRole("link", { name: STAFF.employee.name }).click();
  await page.getByRole("tab", { name: "Documents" }).click();
  await expect(page.getByRole("link", { name: `Old appointment ${tag}`, exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: `scan ${tag}`, exact: true })).toBeVisible();
  await signOut(page);
});
