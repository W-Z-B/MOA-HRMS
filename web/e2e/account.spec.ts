import { expect, expectAccessible, linkSentTo, mailbox, openSection, password, signIn, signOut, STAFF, test } from "./support";

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

test("the sign-in email changes only once the new address confirms it", async ({ page }, testInfo) => {
  const fresh = `shanta.${testInfo.project.name}@gsa.example`;
  await signIn(page, STAFF.lecturer.username);
  await openSection(page, "My account");
  const form = page.getByRole("form", { name: "Change your sign-in email" });
  const before = mailbox();
  await form.getByLabel("New email address").fill(fresh);
  await form.getByLabel("Your password").fill(password());
  await form.getByRole("button", { name: "Send the link" }).click();
  await expect(form.getByRole("status")).toContainText(`A link to confirm it was sent to ${fresh}.`);
  await expect(form).toContainText(`Waiting for you to follow the link sent to ${fresh}`);
  await expectAccessible(page, testInfo, "changing the sign-in email");

  await page.goto(await linkSentTo(fresh, before, "confirm-email"));
  await page.getByRole("button", { name: "Confirm the new address" }).click();
  await expect(page.getByRole("status")).toContainText(`The sign-in email address is now ${fresh}.`);
  await expectAccessible(page, testInfo, "confirming a new sign-in email");
  await page.getByRole("button", { name: "Go to the GSA HRMS" }).click();
  await openSection(page, "My account");
  await expect(page.getByRole("form", { name: "Change your sign-in email" })).toContainText(fresh);
  await signOut(page);
});
