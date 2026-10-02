import { expect, expectAccessible, signIn, signOut, STAFF, test } from "./support";

test("the sign-in page is accessible and refuses a wrong password", async ({ page }, testInfo) => {
  const response = await page.goto("/");
  // The hosted configuration sends the Content-Security-Policy with the web app (deploy/railway/Caddyfile).
  expect(response?.headers()["content-security-policy"]).toContain("default-src 'self'");
  await expect(page.getByRole("heading", { name: "GSA HRMS" })).toBeVisible();
  await expectAccessible(page, testInfo, "sign-in");

  await page.getByLabel("Username").fill(STAFF.employee.username);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Username or password is incorrect.");
});

test("an employee lands on their own leave and sees only their own pages", async ({ page }) => {
  await signIn(page, STAFF.employee.username);
  await expect(page.getByRole("heading", { name: "Leave", level: 1 })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link")).toHaveText(["To do", "Leave", "My contract", "My record", "My account"]);
  await signOut(page);
});
