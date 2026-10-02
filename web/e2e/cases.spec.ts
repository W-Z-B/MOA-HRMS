import { expect, expectAccessible, newStarter, openSection, signIn, signOut, STAFF, test } from "./support";

const iso = (day: Date) => day.toISOString().slice(0, 10);

test("HR opens a discipline case, puts the allegation in writing and decides it", async ({ page }, testInfo) => {
  const { name } = newStarter(testInfo);
  // Yesterday by the clock of the machine running the test: never later than the server's today.
  const yesterday = new Date(Date.now() - 24 * 3600 * 1000);
  await signIn(page, STAFF.hr.username);
  await openSection(page, "Cases");
  await page.getByRole("button", { name: "Open a case" }).click();
  const form = page.getByRole("form", { name: "Open a case" });
  const about = form.getByRole("combobox", { name: /^About/ });
  const value = await about.locator("option", { hasText: name }).getAttribute("value");
  await about.selectOption(value!);
  await form.getByLabel("Opened on").fill(iso(yesterday));
  await form.getByLabel("The allegation").fill("Left the farm gate open overnight");
  await form.getByRole("button", { name: "Open the case" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`^DC-\\d{4}-\\d{3}: ${name}$`) })).toBeVisible();

  const step = page.getByRole("form", { name: "Record a step" });
  await step.getByLabel("On", { exact: true }).fill(iso(yesterday));
  await step.getByLabel("What happened").fill("A letter setting out the allegation, handed over in person");
  await step.getByRole("button", { name: "Record a step" }).click();
  await expect(page.getByRole("list", { name: "Steps" })).toContainText("Allegation put in writing");

  const decision = page.getByRole("form", { name: "Record the decision" });
  await decision.getByRole("combobox", { name: /^Outcome/ }).selectOption("verbal_warning");
  await decision.getByLabel("Decided on").fill(iso(yesterday));
  await decision.getByLabel("Reasons").fill("Admitted, and a first time");
  await decision.getByRole("button", { name: "Record the decision" }).click();
  await expect(page.getByText(/It lapses on \d{2}\/\d{2}\/\d{4}/)).toBeVisible();
  await expectAccessible(page, testInfo, "a case");
  await signOut(page);
});
