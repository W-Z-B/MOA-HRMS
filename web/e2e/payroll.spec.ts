import { expect, expectAccessible, openSection, signIn, signOut, STAFF, test } from "./support";

// Every payroll write (calculate, approve, disburse) needs Finance or an administrator, and every role
// that may act there needs MFA verified, which no browser journey in this suite automates for any role.
// The demonstration data (seed_demo) disburses one payslip directly, so this journey checks the
// self-service half end to end: viewing and downloading a real payslip. The admin workflow (calculate,
// the same person never approving their own figures, disburse) is covered by payroll's pytest suite.
test("an employee reads and downloads a disbursed payslip", async ({ page }, testInfo) => {
  await signIn(page, STAFF.employee.username);
  await openSection(page, "Payroll");
  await expect(page.getByRole("heading", { name: "Payroll" })).toBeVisible();

  const row = page.getByRole("listitem").filter({ hasText: "2026-09" });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Gross");

  const download = page.waitForEvent("download");
  await row.getByRole("link", { name: "Download PDF" }).click();
  expect((await download).suggestedFilename()).toBe("payslip-2026-09-E0001.pdf");

  await expectAccessible(page, testInfo, "the payroll screen");
  await signOut(page);
});
