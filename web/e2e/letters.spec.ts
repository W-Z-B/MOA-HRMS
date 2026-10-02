import { expect, expectAccessible, letterPerson, openSection, password, signIn, signOut, STAFF, test } from "./support";

test("HR writes a job letter, the person reads it under My contract, and a bank checks it is genuine", async ({ page }, testInfo) => {
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
  await page.getByRole("combobox", { name: /^Once it is issued, ask/ }).selectOption("acknowledge");
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
  const row = page.getByRole("table", { name: "Letters issued" }).getByRole("row").filter({ hasText: reference });
  await expect(row).toContainText(person.name);
  await expect(row).toContainText("not checked yet");
  const code = ((await row.locator("code").textContent()) ?? "").trim();
  expect(code).toMatch(/^[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}$/);
  await expectAccessible(page, testInfo, "letters issued");
  await page.getByRole("tab", { name: "Templates" }).click();
  await page.getByRole("button", { name: "Read the wording of Certificate of service" }).click();
  await expect(page.getByText(/This is to certify that/)).toBeVisible();
  await expectAccessible(page, testInfo, "letter templates");
  await signOut(page);

  await signIn(page, person.username);
  await openSection(page, "My contract");
  await expect(page.getByRole("list", { name: "My letters" })).toContainText(reference);

  // Asked to acknowledge it: they read it, tick the sentence and confirm with their password (item 1.20).
  const waiting = page.getByRole("list", { name: "Waiting for your signature" });
  await expect(waiting).toContainText(reference);
  const sign = page.getByRole("form", { name: `Sign Job letter, ${reference}` });
  await sign.getByLabel("I have received this document and read it.").check();
  await sign.getByLabel(/Your password/).fill(password());
  await expectAccessible(page, testInfo, "waiting for a signature");
  await sign.getByRole("button", { name: "Sign" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Signed: Job letter, ${reference}.` })).toBeVisible();
  await expect(page.getByRole("list", { name: "Signed or declined" })).toContainText(reference);
  await signOut(page);

  // A bank shown the letter checks it with no account, by the reference and code at its foot (item 1.47).
  await page.getByRole("button", { name: "Shown a letter from the School? Check it is genuine" }).click();
  const check = page.getByRole("form", { name: "Check a letter" });
  await check.getByLabel("Reference").fill(reference);
  await check.getByLabel("Code").fill("ABCD-EFGH-JKMN");
  await check.getByRole("button", { name: "Check the letter" }).click();
  await expect(page.getByRole("alert")).toContainText("No letter matches that reference and code.");
  await check.getByLabel("Code").fill(code.toLowerCase());
  await check.getByRole("button", { name: "Check the letter" }).click();
  await expect(page.getByRole("status")).toContainText(`Genuine: Job letter ${reference}, about ${person.name}`);
  await expect(page.getByRole("article", { name: "The letter" })).toContainText("for a loan application at a bank.");
  await expectAccessible(page, testInfo, "checking a letter");
});
