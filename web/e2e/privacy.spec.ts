import { expect, expectAccessible, openSection, privacyPerson, signIn, signOut, STAFF, test } from "./support";

// The person asks; HR answers; the person sees the answer.
test.describe.serial("privacy rights", () => {
  test("at first sign-in a member of staff reads the privacy notice, sees their record and asks for a correction", async ({
    page,
  }, testInfo) => {
    const person = privacyPerson(testInfo);
    await page.goto("/");
    await page.getByLabel("Username").fill(person.username);
    await page.getByLabel("Password", { exact: true }).fill(process.env.E2E_PASSWORD ?? "");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Demonstration privacy notice" })).toBeVisible();
    await expectAccessible(page, testInfo, "privacy notice");
    await page.getByRole("button", { name: "I have read this notice" }).click();
    await expect(page.getByRole("link", { name: "GSA HRMS Home" })).toBeVisible();

    await openSection(page, "My record");
    await expect(page.getByRole("region", { name: "Personal details" })).toContainText(person.employeeNo);
    await expectAccessible(page, testInfo, "my record");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download as a file" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^my-gsa-hrms-record-\d{4}-\d{2}-\d{2}\.json$/);

    await page.getByLabel("What is it about").selectOption("contact");
    await page.getByLabel("What is wrong").fill("My phone number is out of date");
    await page.getByLabel("What it should say").fill("592-600-7777");
    await page.getByRole("button", { name: "Send to Human Resources" }).click();
    await expect(page.getByRole("status")).toContainText("Sent to Human Resources");
    await signOut(page);
  });

  test("HR answers the correction, and the person sees the answer", async ({ page }, testInfo) => {
    const person = privacyPerson(testInfo);
    await signIn(page, STAFF.hr.username);
    await openSection(page, "Admin");
    await page.getByRole("tab", { name: "Correction requests" }).click();
    const request = page
      .getByRole("list", { name: "Correction requests" })
      .getByRole("listitem")
      .filter({ hasText: person.name })
      .first();
    await expect(request).toContainText("My phone number is out of date");
    await expectAccessible(page, testInfo, "correction requests");
    await request.getByLabel(`Answer to ${person.name}`).fill("Your phone number is updated on your file.");
    await request.getByRole("button", { name: "Corrected" }).click();
    await expect(page.getByRole("status")).toContainText(`${person.name} is told the record has been corrected.`);
    await signOut(page);

    await signIn(page, person.username);
    await openSection(page, "My record");
    await expect(page.getByRole("list", { name: "Your correction requests" })).toContainText("Corrected");
    await signOut(page);
  });
});
