import { openSearch, openSection, signIn, signOut, STAFF, test, openAdmin } from "./support";

/**
 * Screenshots of the main screens for review in a pull request. Off by default; run with
 * SCREENSHOTS=1 bash scripts/e2e.sh and look in web/test-results/screens/.
 */
test.skip(!process.env.SCREENSHOTS, "screenshots are taken only when SCREENSHOTS=1");

test("main screens", async ({ page }, testInfo) => {
  // The page scrolls in its own area, so a whole page is shot by making the window as tall as the page.
  const shot = async (name: string) => {
    const size = page.viewportSize()!;
    const more = await page.evaluate(() => {
      const area = document.querySelector(".scroller");
      return area ? area.scrollHeight - area.clientHeight : 0;
    });
    if (more > 0) await page.setViewportSize({ width: size.width, height: size.height + more });
    await page.screenshot({ path: `test-results/screens/${testInfo.project.name}-${name}.png`, fullPage: true });
    if (more > 0) await page.setViewportSize(size);
  };

  await signIn(page, STAFF.hr.username);
  await page.getByRole("region", { name: "Waiting for a decision" }).getByRole("listitem").first().waitFor();
  await shot("hr-home");
  await openSearch(page);
  await page.getByRole("dialog", { name: "Search" }).getByRole("combobox").fill("Thomas");
  await page.getByRole("dialog", { name: "Search" }).getByRole("group", { name: "People" }).waitFor();
  await shot("search");
  await page.keyboard.press("Escape");
  await openSection(page, "To do");
  await page.getByRole("list", { name: "Waiting for you" }).waitFor();
  await shot("to-do");
  await openSection(page, "People");
  await page.getByRole("table", { name: "Staff" }).getByRole("row").nth(5).waitFor();
  await shot("people");
  await page.getByLabel("Search staff").fill("Persaud");
  await page.getByRole("row").filter({ hasText: STAFF.employee.name }).getByRole("link", { name: STAFF.employee.name }).click();
  await page.getByRole("heading", { name: STAFF.employee.name, level: 1 }).waitFor();
  await page.locator(".facts").getByText("Annual leave left").waitFor();
  await shot("employee-file");
  for (const tab of ["Background", "Contacts", "Bank", "History"]) {
    await page.getByRole("tab", { name: tab }).click();
    await page.waitForTimeout(300);
    await shot(`employee-${tab.toLowerCase()}`);
  }
  await page.getByRole("tab", { name: "Appointments" }).click();
  await page.getByRole("button", { name: "Record a change" }).click();
  await page.getByRole("form", { name: "Record a change" }).waitFor();
  await shot("employee-career-change");
  await page.getByRole("tab", { name: "Documents" }).click();
  await page.getByRole("button", { name: "Write a letter" }).click();
  await page.getByRole("combobox", { name: /^Letter/ }).selectOption({ label: "Job letter" });
  await page.getByLabel("What the letter is for").fill("a loan application at a bank");
  await page.getByRole("button", { name: "Read the letter" }).click();
  await page.getByRole("article", { name: "The letter" }).waitFor();
  await shot("letter-read-before-issue");
  await openSection(page, "Letters");
  await page.getByRole("tab", { name: "Templates" }).click();
  await page.getByRole("list", { name: "Letter templates" }).waitFor();
  await shot("letter-templates");
  await openSection(page, "Reports");
  await page.getByRole("radio", { name: /^Staff records to check/ }).click();
  await page.getByRole("table").waitFor();
  await shot("report-data-quality");
  await openSection(page, "Organisation");
  await page.getByRole("list", { name: "Units on Mon Repos Campus" }).waitFor();
  await shot("organisation-chart");
  await page.getByRole("tab", { name: "Posts" }).click();
  await page.getByRole("table", { name: "Posts" }).waitFor();
  await shot("organisation-posts");
  await page.getByRole("tab", { name: "Units" }).click();
  await page.getByRole("list", { name: "Units" }).waitFor();
  await shot("organisation-units");
  await openSection(page, "Incidents");
  await page.getByRole("table", { name: "Incidents" }).getByRole("button", { name: "IN-2026-002" }).click();
  await page.getByRole("list", { name: "People hurt" }).waitFor();
  await shot("incident");
  await openSection(page, "Admin");
  await page.getByRole("list", { name: "Accounts" }).waitFor();
  await shot("admin-accounts");
  await openAdmin(page, "Staff without an account");
  await page.waitForTimeout(300);
  await shot("admin-staff");
  await openAdmin(page, "Holidays");
  await page.getByRole("table").waitFor();
  await shot("admin-holidays");
  await openAdmin(page, "Leave types");
  await page.getByRole("table").waitFor();
  await shot("admin-leave-types");
  await signOut(page);
  await shot("sign-in");
  await page.getByRole("button", { name: "Forgot your password?" }).click();
  await shot("forgot-password");

  await signIn(page, STAFF.employee.username);
  await page.getByRole("region", { name: "Your employment" }).getByRole("listitem").first().waitFor();
  await shot("employee-home");
  await page.getByRole("button", { name: "Request leave" }).click();
  await page.getByRole("region", { name: "Days you have left" }).waitFor();
  await shot("employee-leave");
  await openSection(page, "My account");
  await page.getByRole("region", { name: "Where you are signed in" }).getByRole("listitem").first().waitFor();
  await shot("my-account");
  await openSection(page, "My record");
  await page.getByRole("region", { name: "Personal details" }).waitFor();
  await shot("my-record");
  await signOut(page);

  await signIn(page, STAFF.manager.username);
  await page.getByRole("region", { name: "Your team" }).getByRole("listitem").first().waitFor();
  await shot("manager-home");
  await signOut(page);

  await signIn(page, STAFF.principal.username);
  await page.getByRole("region", { name: "Establishment by unit" }).getByRole("listitem").first().waitFor();
  await shot("principal-home");
  await signOut(page);

  await signIn(page, STAFF.auditor.username);
  await openSection(page, "Admin");
  await openAdmin(page, "Access review");
  await page.getByRole("table").waitFor();
  await shot("admin-access-review");
  await openAdmin(page, "Audit log");
  await page.getByRole("list", { name: "Audit entries" }).waitFor();
  await shot("admin-audit");
  await openAdmin(page, "Retention");
  await page.getByRole("table", { name: "The retention schedule" }).waitFor();
  await shot("admin-retention");
  await signOut(page);
});
