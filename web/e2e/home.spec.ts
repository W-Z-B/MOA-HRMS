import type { Page } from "@playwright/test";
import { expect, expectAccessible, openSearch, signIn, signOut, STAFF, test } from "./support";

/** Item 2.30: a Home for each role, search for everything, and on a phone four tabs at the bottom. */

const onPhone = (page: Page) => page.getByRole("navigation", { name: "Main" }).isVisible();

async function chooseCampus(page: Page, label: string) {
  if (await onPhone(page)) {
    await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Me" }).click();
    await page.getByRole("dialog", { name: "Your account" }).getByRole("button", { name: label }).click();
    await page.keyboard.press("Escape");
  } else {
    await page.getByRole("banner").getByRole("group", { name: "Campus" }).getByRole("button", { name: label }).click();
  }
}

test("Human Resources' Home shows its work, its figures, and narrows to one campus", async ({ page }, testInfo) => {
  await signIn(page, STAFF.hr.username);
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
  await expect(page.locator(".eyebrow")).toHaveText(/ · All campuses$/);
  const shortcuts = page.getByRole("navigation", { name: "Shortcuts" });
  await expect(shortcuts.locator(".shortcut-title")).toHaveText(["People", "Leave requests", "Letters", "Organisation", "Reports", "Admin"]);
  const figures = page.getByRole("region", { name: "Figures" });
  await expect(figures).toContainText("Active staff");
  await expect(figures).toContainText("Posts filled");
  await expect(page.getByRole("region", { name: "Waiting for a decision" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Headcount by campus" })).toContainText("Essequibo Campus");
  await expect(page.getByRole("region", { name: "Needs attention" })).toBeVisible();
  await expectAccessible(page, testInfo, "hr home");

  await chooseCampus(page, "Essequibo");
  await expect(page.locator(".eyebrow")).toHaveText(/ · Essequibo Campus$/);
  const headcount = page.getByRole("region", { name: "Headcount by campus" });
  await expect(headcount.getByRole("listitem")).toHaveCount(1);
  await expect(headcount).not.toContainText("Mon Repos");
  await chooseCampus(page, "All campuses");
  await expect(page.locator(".eyebrow")).toHaveText(/ · All campuses$/);

  await shortcuts.getByRole("link", { name: /Leave requests/ }).click();
  await expect(page.getByRole("tab", { name: /To decide/ })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Home" }).click();
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
  await signOut(page);
});

test("search finds a person by name and opens their file, with the way back above it", async ({ page }, testInfo) => {
  await signIn(page, STAFF.hr.username);
  await openSearch(page);
  const dialog = page.getByRole("dialog", { name: "Search" });
  await dialog.getByRole("combobox").fill("Persaud");
  const person = dialog.getByRole("group", { name: "People" }).getByRole("option", { name: /^Asha Persaud,/ });
  await expect(person).toBeVisible();
  await expectAccessible(page, testInfo, "search");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumbs.getByRole("listitem")).toHaveText(["Home", "People", STAFF.employee.name]);

  // An action, too: "Report an incident" opens the form at once.
  await openSearch(page);
  await dialog.getByRole("combobox").fill("incident");
  await dialog.getByRole("group", { name: "Actions" }).getByRole("option", { name: /^Report an incident,/ }).click();
  await expect(page.getByRole("form", { name: "Report an incident" })).toBeVisible();
  await signOut(page);
});

test("the Principal's Home shows the establishment unit by unit and what ends soon", async ({ page }, testInfo) => {
  await signIn(page, STAFF.principal.username);
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
  const units = page.getByRole("region", { name: "Establishment by unit" });
  await expect(units).toContainText("Livestock Unit");
  await expect(units).toContainText("filled");
  await expect(page.getByRole("region", { name: "Ending soon" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Waiting for a decision" })).toHaveCount(0);
  await expectAccessible(page, testInfo, "principal home");
  await page.getByRole("region", { name: "Reports" }).getByRole("button", { name: /^Open: Headcount/ }).click();
  await expect(page.getByRole("heading", { name: "Reports", level: 1 })).toBeVisible();
  await signOut(page);
});

test("a phone has Home, To do, Search and Me at the bottom; a wider screen has them in the header", async ({ page }, testInfo) => {
  await signIn(page, STAFF.manager.username);
  if (await onPhone(page)) {
    const tabs = page.getByRole("navigation", { name: "Main" });
    await expect(tabs.getByRole("link").first()).toHaveText("Home");
    await tabs.getByRole("link", { name: /^To do/ }).click();
    await expect(page.getByRole("heading", { name: "To do", level: 1 })).toBeVisible();
    await tabs.getByRole("button", { name: "Me" }).click();
    const sheet = page.getByRole("dialog", { name: "Your account" });
    await expect(sheet).toContainText("Head of Department of Agriculture");
    await expectAccessible(page, testInfo, "phone me sheet");
    await sheet.getByRole("link", { name: /My contract/ }).click();
    await expect(page.getByRole("heading", { name: "My contract", level: 1 })).toBeVisible();
  } else {
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await page.getByRole("banner").getByRole("link", { name: /^To do/ }).click();
    await expect(page.getByRole("heading", { name: "To do", level: 1 })).toBeVisible();
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: "Search" })).toBeVisible();
    await page.keyboard.press("Escape");
  }
  await signOut(page);
});
