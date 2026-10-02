import { expect, expectAccessible, openSection, signIn, signOut, standIn, test } from "./support";

const iso = (day: Date) => day.toISOString().slice(0, 10);
const inDays = (n: number) => new Date(Date.now() + n * 24 * 3600 * 1000);

test("someone who decides names a stand-in for while they are away, then ends it", async ({ page }, testInfo) => {
  const { username, delegate } = standIn(testInfo);
  await signIn(page, username);
  await openSection(page, "To do");
  await expect(page.getByRole("heading", { name: "To do", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "Name a stand-in" }).click();
  const form = page.getByRole("form", { name: "Name a stand-in" });
  await form.getByRole("combobox", { name: /^Who/ }).selectOption({ label: delegate });
  await form.getByLabel("From").fill(iso(inDays(2)));
  await form.getByLabel("Until").fill(iso(inDays(12)));
  await form.getByLabel("Why (optional)").fill("A course in Georgetown");
  await form.getByRole("button", { name: "Name the stand-in" }).click();
  await expect(page.getByRole("status").filter({ hasText: `${delegate} stands in for you from` })).toBeVisible();
  await expect(page.getByRole("list", { name: "Your stand-ins" })).toContainText("A course in Georgetown");
  await expectAccessible(page, testInfo, "to do and stand-ins");

  await page.getByRole("button", { name: `End ${delegate} standing in` }).click();
  await expect(page.getByRole("status").filter({ hasText: `${delegate} no longer stands in for you.` })).toBeVisible();
  await signOut(page);
});
