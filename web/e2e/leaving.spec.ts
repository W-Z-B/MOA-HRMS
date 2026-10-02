import { expect, expectAccessible, leaver, openSection, signIn, signOut, STAFF, test } from "./support";

const iso = (day: Date) => day.toISOString().slice(0, 10);

test("HR checks what a redundancy owes, records the leaving, then withdraws it", async ({ page }, testInfo) => {
  const { name } = leaver(testInfo);
  // Yesterday by the clock of the machine running the test: never later than the server's today.
  const noticeGiven = new Date(Date.now() - 24 * 3600 * 1000);
  const lastDay = new Date(Date.now() + 40 * 24 * 3600 * 1000);
  await signIn(page, STAFF.hr.username);
  await openSection(page, "People");
  await page.getByLabel("Search staff").fill(name.split(" ")[1]);
  await page.getByRole("row").filter({ hasText: name }).getByRole("link", { name }).click();
  await page.getByRole("tab", { name: "Appointments" }).click();

  await page.getByRole("button", { name: "Record leaving" }).click();
  const form = page.getByRole("form", { name: "Record leaving" });
  await form.getByRole("combobox", { name: /^Why they are leaving/ }).selectOption("redundancy");
  await form.getByLabel("Notice given on").fill(iso(noticeGiven));
  await form.getByLabel("Last day").fill(iso(lastDay));
  await form.getByLabel("In words").fill("The unit is closing");
  await form.getByRole("button", { name: "Check the notice and the figures" }).click();

  const check = form.getByLabel("The check");
  await expect(check).toContainText("one month, employed a year or more is asked for. The last day leaves full notice.");
  await expect(check.getByRole("table", { name: "Owed on leaving" })).toContainText(/Severance: \d+ weeks' wages for \d+ completed years/);
  await expectAccessible(page, testInfo, "leaving checked");
  await check.getByRole("button", { name: "Record leaving" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Recorded: leaving on" })).toBeVisible();
  await expect(page.getByText(/^Leaving on \d{2}\/\d{2}\/\d{4}$/)).toBeVisible();

  await page.getByRole("button", { name: "Withdraw the leaving" }).click();
  const withdraw = page.getByRole("form", { name: "Withdraw the leaving" });
  await withdraw.getByLabel("Why withdraw it").fill("The unit stays open");
  await withdraw.getByRole("button", { name: "Withdraw the leaving" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The leaving is withdrawn." })).toBeVisible();
  await expect(page.getByText(/Withdrawn before: redundancy/)).toBeVisible();
  await signOut(page);
});

test("the leaving section is not shown to someone who only reads staff files", async ({ page }) => {
  await signIn(page, STAFF.manager.username);
  await openSection(page, "People");
  await page.getByRole("row").filter({ hasText: STAFF.employee.name }).getByRole("link", { name: STAFF.employee.name }).click();
  await page.getByRole("tab", { name: "Appointments" }).click();
  await expect(page.getByRole("heading", { name: "Career changes" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Leaving" })).toHaveCount(0);
  await signOut(page);
});
