import {
  expect,
  expectAccessible,
  linkSentTo,
  mailbox,
  newStarter,
  openAdmin,
  openSection,
  passNotice,
  signIn,
  signOut,
  STAFF,
  test,
} from "./support";

// The new starter's own passwords: chosen from the invitation, then from a reset link.
const CHOSEN = "Mangrove-Seawall-Sunrise-2026";
const RESET = "Cane-Field-Morning-Rain-2026";

// Each journey hands the account on to the next: invited, then a forgotten password, then switched off.
test.describe.serial("accounts", () => {
  test("HR opens an account for a new starter, who chooses their own password and signs in", async ({ page }, testInfo) => {
    const starter = newStarter(testInfo);
    await signIn(page, STAFF.hr.username);
    await openSection(page, "Admin");
    await openAdmin(page, "Staff without an account");
    await expect(page.getByText(starter.name)).toBeVisible();
    await expectAccessible(page, testInfo, "staff without an account");

    const before = mailbox();
    await page.getByRole("button", { name: `Open an account for ${starter.name}` }).click();
    await expect(page.getByRole("status")).toContainText(`The invitation to choose a password was sent to ${starter.email}.`);
    const invitation = await linkSentTo(starter.email, before);
    await signOut(page);

    await page.goto(invitation);
    await expect(page.getByRole("heading", { name: "Welcome: choose your password" })).toBeVisible();
    await expect(page.getByText(starter.username, { exact: true })).toBeVisible();
    await expectAccessible(page, testInfo, "choose your password");
    await page.getByLabel("New password", { exact: true }).fill(CHOSEN);
    await page.getByLabel("New password again").fill(CHOSEN);
    await page.getByRole("button", { name: "Save my password" }).click();

    await expect(page.getByRole("status")).toHaveText("Your password is saved. Sign in with it now.");
    await expect(page.getByLabel("Username")).toHaveValue(starter.username);
    await page.getByLabel("Password", { exact: true }).fill(CHOSEN);
    await page.getByRole("button", { name: "Sign in" }).click();
    // Their first sign-in: the privacy notice comes first (item 1.31).
    expect(await passNotice(page)).toBe(true);
    await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
    await signOut(page);

    // The link worked once.
    await page.goto(invitation);
    await expect(page.getByRole("alert")).toContainText("expired or has already been used");
  });

  test("someone who forgot their password asks for a link and chooses a new one", async ({ page }, testInfo) => {
    const starter = newStarter(testInfo);
    await page.goto("/");
    await page.getByRole("button", { name: "Forgot your password?" }).click();
    await expect(page.getByRole("heading", { name: "Forgot your password?" })).toBeVisible();
    await expectAccessible(page, testInfo, "forgot password");

    const before = mailbox();
    await page.getByLabel("Username or email address").fill(starter.username);
    await page.getByRole("button", { name: "Email me a link" }).click();
    await expect(page.getByRole("status")).toContainText("a link to choose a new password is on its way");
    await page.goto(await linkSentTo(starter.email, before));
    await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
    await page.getByLabel("New password", { exact: true }).fill(RESET);
    await page.getByLabel("New password again").fill(RESET);
    await page.getByRole("button", { name: "Save my password" }).click();

    await expect(page.getByRole("status")).toHaveText("Your password is saved. Sign in with it now.");
    await page.getByLabel("Password", { exact: true }).fill(RESET);
    await page.getByRole("button", { name: "Sign in" }).click();
    await passNotice(page);
    await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
    await signOut(page);
  });

  test("HR gives a role and takes it away, and switching the account off signs the person out at once", async ({
    page,
    browser,
    baseURL,
  }, testInfo) => {
    const starter = newStarter(testInfo);
    await signIn(page, STAFF.hr.username);
    await openSection(page, "Admin");
    await page.getByLabel("Find an account").fill(starter.username);
    await page.getByRole("button", { name: "Find", exact: true }).click();
    const card = page.getByRole("list", { name: "Accounts" }).getByRole("listitem").filter({ hasText: starter.email });
    await expect(card.getByText("In use")).toBeVisible();
    await expectAccessible(page, testInfo, "accounts");

    await card.getByRole("button", { name: `Give a role to ${starter.name}` }).click();
    await card.getByRole("combobox", { name: "Role", exact: true }).selectOption({ label: "Supervisor / Head of Department" });
    await card.getByRole("combobox", { name: "Campus", exact: true }).selectOption({ index: 1 });
    await card.getByRole("button", { name: "Give the role" }).click();
    await expect(card.getByRole("status")).toContainText("applies from their next sign-in");
    const takeAway = new RegExp(`^Take away Supervisor / Head of Department, .*, from ${starter.name}$`);
    await card.getByRole("button", { name: takeAway }).click();
    await expect(card.getByRole("status")).toContainText("taken away");

    // The starter signs in on their own device.
    const theirs = await browser.newContext({ baseURL, ignoreHTTPSErrors: true });
    const device = await theirs.newPage();
    try {
      await device.goto("/");
      await device.getByLabel("Username").fill(starter.username);
      await device.getByLabel("Password", { exact: true }).fill(RESET);
      await device.getByRole("button", { name: "Sign in" }).click();
      await passNotice(device);
      await expect(device.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();

      await card.getByRole("button", { name: `Switch off the account of ${starter.name}` }).click();
      await card.getByLabel("Why switch it off?").fill("Journey test: switched off and on again");
      await card.getByRole("button", { name: "Switch off", exact: true }).click();
      await expect(card.getByRole("status")).toContainText("every session has ended");

      // Their device finds out at its next request and returns to sign-in.
      await openSection(device, "My contract");
      await expect(device.getByRole("button", { name: "Sign in" })).toBeVisible();
    } finally {
      await theirs.close();
    }

    await card.getByRole("button", { name: `Switch on the account of ${starter.name}` }).click();
    await card.getByLabel("Why switch it on?").fill("Journey test: back on");
    await card.getByRole("button", { name: "Switch on", exact: true }).click();
    await expect(card.getByRole("status")).toContainText("can sign in again");
    await signOut(page);
  });
});
