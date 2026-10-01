import { expect, test } from "@playwright/test";
import { expectAccessible, signIn, signOut, STAFF } from "./support";

test("the sign-in page is accessible and refuses a wrong password", async ({ page }, testInfo) => {
  await page.goto("/");
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
  await expect(nav.getByRole("link")).toHaveText(["Leave", "My contract"]);
  await signOut(page);
});
