import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

const iso = (day: Date) => day.toISOString().slice(0, 10);

test("a dangerous occurrence is reported, notified within two days and closed", async ({ page }, testInfo) => {
  // Yesterday by the clock of the machine running the test: never later than the server's today.
  const yesterday = new Date(Date.now() - 24 * 3600 * 1000);
  const place = `Workshop bench ${testInfo.project.name}`;

  await signIn(page, STAFF.employee.username);
  await openSection(page, "Incidents");
  await page.getByRole("button", { name: "Report an incident" }).click();
  const form = page.getByRole("form", { name: "Report an incident" });
  await form.getByRole("radio", { name: /A dangerous occurrence/ }).check();
  await form.getByLabel("When").fill(`${iso(yesterday)}T10:00`);
  await form.getByRole("combobox", { name: "Campus" }).selectOption({ label: "Mon Repos Campus" });
  await form.getByLabel("Exactly where").fill(place);
  await form.getByRole("checkbox", { name: /industrial place/ }).check();
  await form.getByLabel("What happened").fill("A grinder disc shattered. Nobody was hurt.");
  await form.getByRole("button", { name: "Send the report" }).click();
  const status = page.getByRole("status");
  await expect(status).toContainText(/Reported as IN-\d{4}-\d{3}\. Human Resources has been told\./);
  const reference = (await status.textContent())!.match(/IN-\d{4}-\d{3}/)![0];
  await expect(page.getByRole("list", { name: "Reported by you, or about you" })).toContainText(reference);
  await expectAccessible(page, testInfo, "the incident report");
  await signOut(page);

  await signIn(page, STAFF.hr.username);
  await openSection(page, "Incidents");
  await page.getByRole("table", { name: "Incidents" }).getByRole("button", { name: reference }).click();
  await expect(page.getByRole("heading", { name: `${reference}: dangerous occurrence at ${place}` })).toBeVisible();
  await expect(page.getByRole("list", { name: "Notices the Act requires" })).toContainText(
    "A dangerous occurrence, section 74: due",
  );

  const notice = page.getByRole("form", { name: "Record a notice sent" });
  for (const body of ["The Occupational Safety and Health Authority", "The safety and health committee"]) {
    await expect(notice.getByRole("combobox", { name: "Notice" })).toContainText(body);
    await notice.getByLabel("Sent on").fill(iso(yesterday));
    await notice.getByLabel("How", { exact: true }).fill("By hand");
    await notice.getByRole("button", { name: "Record a notice sent" }).click();
    await expect(page.getByRole("status")).toHaveText("The notice is recorded.");
  }
  await expect(page.getByRole("form", { name: "Record a notice sent" })).toHaveCount(0);

  const found = page.getByRole("form", { name: "Record what the investigation found" });
  await found.getByLabel("Why it happened").fill("The disc was past its date and not checked.");
  await found.getByLabel("Found on").fill(iso(yesterday));
  await found.getByRole("button", { name: "Record what the investigation found" }).click();
  await expect(page.getByRole("status")).toHaveText("The investigation is recorded.");

  await page.getByRole("button", { name: "Close the incident" }).click();
  await expect(page.getByText(/^Closed \d{2}\/\d{2}\/\d{4} by Natasha Khan\./)).toBeVisible();
  await expectAccessible(page, testInfo, "an incident");
  await signOut(page);
});
