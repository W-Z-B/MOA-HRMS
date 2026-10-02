import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

const iso = (day: Date) => day.toISOString().slice(0, 10);

test("a supervisor issues an item to someone on their campus and records it given back", async ({ page }, testInfo) => {
  // Yesterday by the clock of the machine running the test: never later than the server's today.
  const yesterday = new Date(Date.now() - 24 * 3600 * 1000);
  const description = `Field notebook (${testInfo.project.name})`;
  await signIn(page, STAFF.manager.username);
  await openSection(page, "People");
  await page.getByRole("row").filter({ hasText: STAFF.employee.name }).getByRole("link", { name: STAFF.employee.name }).click();
  await page.getByRole("tab", { name: "Items issued" }).click();

  const form = page.getByRole("form", { name: "Issue an item" });
  await form.getByRole("combobox", { name: /^Kind/ }).selectOption("book");
  await form.getByLabel("What it is").fill(description);
  await form.getByLabel("Issued on").fill(iso(yesterday));
  await form.getByRole("button", { name: "Issue the item" }).click();
  await expect(page.getByRole("status").filter({ hasText: `${description} issued.` })).toBeVisible();

  await page.getByRole("button", { name: `Record ${description} as given back` }).click();
  const back = page.getByRole("form", { name: `Given back: ${description}` });
  await back.getByLabel("Given back on").fill(iso(yesterday));
  await back.getByRole("combobox", { name: /^In what condition/ }).selectOption("good");
  await back.getByRole("button", { name: "Record it" }).click();
  await expect(page.getByRole("status").filter({ hasText: `${description}: in good order, recorded.` })).toBeVisible();
  await expectAccessible(page, testInfo, "items issued");
  await signOut(page);
});
