import { expect, expectAccessible, openSearch, signIn, signOut, STAFF, test } from "./support";

test("the sign-in page is accessible and refuses a wrong password", async ({ page }, testInfo) => {
  const response = await page.goto("/");
  // The hosted configuration sends the Content-Security-Policy with the web app (deploy/railway/Caddyfile).
  expect(response?.headers()["content-security-policy"]).toContain("default-src 'self'");
  await expect(page.getByRole("heading", { name: "GSA HRMS" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Guyana School of Agriculture crest" })).toBeVisible();
  await expectAccessible(page, testInfo, "sign-in");

  await page.getByLabel("Username").fill(STAFF.employee.username);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Username or password is incorrect.");
});

test("an employee lands on their own Home, and search offers only their own pages", async ({ page }, testInfo) => {
  await signIn(page, STAFF.employee.username);
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Request leave" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Your employment" })).toContainText("Lecturer, Crop Science");
  await expectAccessible(page, testInfo, "employee home");

  await openSearch(page);
  const pages = page.getByRole("dialog", { name: "Search" }).getByRole("group", { name: "Pages" });
  await expect(pages.locator(".search-title")).toHaveText([
    "To do",
    "Leave",
    "Incidents",
    "My contract",
    "My record",
    "My account",
    "Attendance",
    "Payroll",
  ]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Search" })).toBeHidden();
  await signOut(page);
});
