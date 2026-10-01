import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

test("someone signed in on two devices signs the other one out", async ({ page, browser, baseURL }, testInfo) => {
  // A second device: its own browser context, so its own session.
  const otherDevice = await browser.newContext({ baseURL, ignoreHTTPSErrors: true });
  const other = await otherDevice.newPage();
  try {
    await signIn(page, STAFF.lecturer.username);
    await signIn(other, STAFF.lecturer.username);

    await openSection(page, "My account");
    const list = page.getByRole("region", { name: "Where you are signed in" });
    await expect(list.getByText("This device")).toBeVisible();
    expect(await list.getByRole("listitem").count()).toBeGreaterThanOrEqual(2);
    await expectAccessible(page, testInfo, "my account");

    await page.getByRole("button", { name: "Sign out everywhere else" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Signed out of" })).toHaveText(
      /^Signed out of \d+ other devices?\.$/,
    );
    await expect(list.getByRole("listitem")).toHaveCount(1);

    // The other device finds out on its next request and returns to sign-in.
    await openSection(other, "My contract");
    await expect(other.getByRole("button", { name: "Sign in" })).toBeVisible();
    await signOut(page);
  } finally {
    await otherDevice.close();
  }
});
