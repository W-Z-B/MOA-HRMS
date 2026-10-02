import { careerChange, expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

const iso = (day: Date) => day.toISOString().slice(0, 10);

test("HR records an acting appointment, then writes its letter from the change", async ({ page }, testInfo) => {
  const { name, post } = careerChange(testInfo);
  // Yesterday by the clock of the machine running the test: never later than the server's today.
  const from = new Date(Date.now() - 24 * 3600 * 1000);
  const until = new Date(Date.now() + 30 * 24 * 3600 * 1000);
  await signIn(page, STAFF.hr.username);
  await openSection(page, "People");
  await page.getByLabel("Search staff").fill(name.split(" ")[1]);
  await page.getByRole("row").filter({ hasText: name }).getByRole("link", { name }).click();
  await page.getByRole("tab", { name: "Appointments" }).click();

  await page.getByRole("button", { name: "Record a change" }).click();
  const form = page.getByRole("form", { name: "Record a change" });
  await form.getByRole("combobox", { name: /^Change/ }).selectOption("acting");
  const postPicker = form.getByRole("combobox", { name: /^Post acted in/ });
  const value = await postPicker.locator("option", { hasText: post }).getAttribute("value");
  await postPicker.selectOption(value!);
  await form.getByLabel("Acting from").fill(iso(from));
  await form.getByLabel(/Acting until/).fill(iso(until));
  await form.getByLabel("Why").fill("Cover while the post is vacant");
  await form.getByRole("button", { name: "Record the change" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Acting appointment recorded, and in effect." })).toBeVisible();

  const change = page.getByRole("list", { name: "Career changes" }).getByRole("listitem").filter({ hasText: "Acting appointment" });
  await expect(change).toContainText(`Acting in ${post}`);
  await expect(change).toContainText("In effect");
  await expectAccessible(page, testInfo, "career changes");

  await change.getByRole("button", { name: "Write the letter" }).click();
  await expect(page.getByRole("heading", { name: "Write the letter for the acting appointment" })).toBeVisible();
  await page.getByRole("button", { name: "Read the letter" }).click();
  await expect(page.getByRole("article", { name: "The letter" })).toContainText(
    `You are appointed to act in the post of ${post.split(" ").slice(1).join(" ")}`,
  );
  await page.getByRole("button", { name: "Issue the letter" }).click();
  await expect(page.getByRole("status").filter({ hasText: "is issued" })).toBeVisible();
  await expect(change).toContainText(/Letter: GSA\/HR\/\d{4}\/\d{4}/);
  await signOut(page);
});
