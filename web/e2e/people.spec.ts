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

  // The file is a page of its own (item 2.30), with the way back above it.
  await expect(page.getByRole("heading", { name: STAFF.employee.name, level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("listitem")).toHaveText([
    "Home",
    "People",
    STAFF.employee.name,
  ]);
  await expect(page.locator(".facts")).toContainText("Manager");
  const nis = page.locator("dt", { hasText: "NIS number" }).locator("xpath=following-sibling::dd[1]");
  await expect(nis).toContainText("•");
  await expectAccessible(page, testInfo, "employee file");

  await page.getByRole("button", { name: "Show identifiers" }).click();
  await expect(nis).toHaveText(/^DEMO-NIS-/);
  await page.getByRole("button", { name: "Hide identifiers" }).click();
  await expect(nis).toContainText("•");

  await page.getByRole("tab", { name: "Contract" }).click();
  const hours = page.locator("dt", { hasText: "Hours a week" }).locator("xpath=following-sibling::dd[1]");
  await expect(hours).toHaveText("40");
  await signOut(page);
});

test("HR keeps a file complete: an emergency contact, a change with its reason, and the history", async ({ page }, testInfo) => {
  // Each browser project writes its own number, so every run makes a real change.
  const phone = testInfo.project.name === "phone" ? "600-7702" : "600-7701";
  await signIn(page, STAFF.hr.username);
  await openSection(page, "People");
  await page.getByLabel("Search staff").fill("Devon");
  await page.getByRole("row").filter({ hasText: "Devon Charles" }).getByRole("link", { name: "Devon Charles" }).click();

  await page.getByRole("tab", { name: "Contacts" }).click();
  await page.getByRole("button", { name: "Add an emergency contact" }).click();
  const form = page.getByRole("form", { name: "Add an emergency contact" });
  await form.getByLabel(/^Name/).fill("Marcia Charles");
  await form.getByLabel(/^Relationship/).fill("Sister");
  await form.getByLabel(/^Phone/).fill("600-5555");
  await form.getByRole("button", { name: "Save" }).click();
  const contacts = page.getByRole("region", { name: "Emergency contacts" });
  await expect(contacts.getByText("Marcia Charles").first()).toBeVisible();
  await expectAccessible(page, testInfo, "employee contacts");

  await page.getByRole("button", { name: "Edit details" }).click();
  await expect(page.getByRole("heading", { name: "Edit details", level: 1 })).toBeVisible();
  await page.getByLabel("Phone", { exact: true }).fill(phone);
  await page.getByLabel("Reason for the change").fill("Number given on the form of 01/10/2026");
  await expectAccessible(page, testInfo, "editing a staff file");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: "Devon Charles", level: 1 })).toBeVisible();

  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByText("Reason: Number given on the form of 01/10/2026").first()).toBeVisible();
  await expect(page.getByText(new RegExp(`Phone changed from .* to ${phone}`)).first()).toBeVisible();
  await expectAccessible(page, testInfo, "employee history");
  await signOut(page);
});
