import { attendancePerson, expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("an employee checks in and out, and Human Resources corrects a day left open", async ({ page }, testInfo) => {
  const person = attendancePerson(testInfo);

  await signIn(page, person.username);
  await openSection(page, "Attendance");
  await expect(page.getByRole("heading", { name: "Attendance" })).toBeVisible();
  await expect(page.getByText("You have not checked in today.")).toBeVisible();

  await page.getByRole("button", { name: "Check in" }).click();
  await expect(page.getByRole("status")).toContainText(/Checked in at \d{2}:\d{2}\./);
  await expect(page.getByRole("button", { name: "Check out" })).toBeVisible();
  await expectAccessible(page, testInfo, "the attendance screen, checked in");
  await signOut(page);

  await signIn(page, STAFF.hr.username);
  await openSection(page, "Attendance");
  await page.getByRole("tab", { name: /Exceptions/ }).click();
  const row = page.getByRole("article", { name: new RegExp(`^${person.name}`) });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Checked in, not checked out");

  await row.getByLabel("Checked out").fill("16:30");
  await row.getByLabel("Why this is being corrected").fill("Confirmed with the supervisor that the day was worked.");
  await row.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(page.getByRole("article", { name: new RegExp(`^${person.name}`) })).toHaveCount(0);
  await expectAccessible(page, testInfo, "the attendance exceptions screen");
  await signOut(page);
});
