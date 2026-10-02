import { expect, expectAccessible, letterPerson, openSection, signIn, signOut, STAFF, test } from "./support";

test("HR writes a job letter from a person's file, and the person reads it under My contract", async ({ page }, testInfo) => {
  const person = letterPerson(testInfo);
  await signIn(page, STAFF.hr.username);
  await openSection(page, "People");
  await page.getByLabel("Search staff").fill(person.name.split(" ")[1]);
  await page.getByRole("row").filter({ hasText: person.name }).getByRole("link", { name: person.name }).click();
  await page.getByRole("tab", { name: "Documents" }).click();
  await page.getByRole("button", { name: "Write a letter" }).click();
  await page.getByRole("combobox", { name: /^Letter/ }).selectOption({ label: "Job letter" });
  await page.getByRole("button", { name: "Read the letter" }).click();
  await expect(page.getByText("Answer: What the letter is for")).toBeVisible();
  await expect(page.getByRole("button", { name: "Issue the letter" })).toBeDisabled();

  await page.getByLabel("What the letter is for").fill("a loan application at a bank");
  await page.getByRole("button", { name: "Read the letter" }).click();
  const letter = page.getByRole("article", { name: "The letter" });
  await expect(letter).toContainText(`This is to confirm that ${person.name}`);
  await expect(letter).toContainText("for a loan application at a bank.");
  await expectAccessible(page, testInfo, "letter read before it is issued");
  await page.getByRole("button", { name: "Issue the letter" }).click();

  const issued = page.getByRole("status").filter({ hasText: "is issued" });
  await expect(issued).toContainText(/GSA\/HR\/\d{4}\/\d{4}/);
  const reference = ((await issued.textContent()) ?? "").match(/GSA\/HR\/\d{4}\/\d{4}/)![0];
  const download = page.waitForEvent("download");
  await issued.getByRole("link", { name: "Download it" }).click();
  expect((await download).suggestedFilename()).toBe(`${reference.replaceAll("/", "-")}.pdf`);
  await expect(page.getByRole("link", { name: `Job letter, ${reference}` })).toBeVisible();

  await openSection(page, "Letters");
  await page.getByRole("searchbox", { name: "Find a letter" }).fill(reference);
  await expect(page.getByRole("table", { name: "Letters issued" })).toContainText(person.name);
  await expectAccessible(page, testInfo, "letters issued");
  await page.getByRole("tab", { name: "Templates" }).click();
  await page.getByRole("button", { name: "Read the wording of Certificate of service" }).click();
  await expect(page.getByText(/This is to certify that/)).toBeVisible();
  await expectAccessible(page, testInfo, "letter templates");
  await signOut(page);

  await signIn(page, person.username);
  await openSection(page, "My contract");
  await expect(page.getByRole("list", { name: "My letters" })).toContainText(reference);
  await signOut(page);
});
