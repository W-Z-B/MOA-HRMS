import { expect, expectAccessible, openSection, privacyPerson, signIn, signOut, STAFF, test } from "./support";

// The person contests one part and objects to another; HR sees both held back; the officer decides.
test.describe.serial("restriction and objection", () => {
  test("a person holds a contested part back and objects to how another is used", async ({ page }, testInfo) => {
    const person = privacyPerson(testInfo);
    await signIn(page, person.username);
    await openSection(page, "My record");
    const correction = page.getByRole("form", { name: "Ask for a correction" });
    await correction.getByLabel("What is it about").selectOption("appointment");
    await correction.getByLabel("What is wrong").fill("My post title is wrong");
    await correction.getByLabel("What it should say").fill("Senior clerk");
    await correction.getByRole("checkbox", { name: /Hold that part of my record back/ }).check();
    await correction.getByRole("button", { name: "Send to Human Resources" }).click();
    await expect(correction.getByRole("status")).toContainText("held back from use");

    const object = page.getByRole("form", { name: "Object to how your record is used" });
    await object.getByLabel("Which part").selectOption("bank");
    await object.getByLabel("Why you object").fill(`Not needed before pay starts (${testInfo.project.name})`);
    await object.getByRole("button", { name: "Send my objection" }).click();
    await expect(object.getByRole("status")).toContainText("Sent to the data protection officer");
    await expect(page.getByRole("list", { name: "Parts of your record held back" })).toContainText(
      "Bank details: the person has objected",
    );
    await expectAccessible(page, testInfo, "objecting on my record");
    await signOut(page);
  });

  test("HR sees what is held back, and the officer decides the objection", async ({ page }, testInfo) => {
    const person = privacyPerson(testInfo);
    await signIn(page, STAFF.hr.username);
    await openSection(page, "People");
    await page.getByLabel("Search staff").fill(person.name.split(" ")[1]);
    await page.getByRole("row").filter({ hasText: person.name }).getByRole("link", { name: person.name }).click();
    const held = page.getByRole("note", { name: "Held back from use" });
    await expect(held).toContainText("Appointment or contract: its accuracy is contested");
    await expect(held).toContainText("Bank details: the person has objected");
    await expectAccessible(page, testInfo, "a record held back");
    await signOut(page);

    await signIn(page, STAFF.dpo.username);
    await openSection(page, "Admin");
    const objection = page
      .getByRole("list", { name: "Objections" })
      .getByRole("listitem")
      .filter({ hasText: `(${testInfo.project.name})` });
    const decide = objection.getByRole("form", { name: `Decide the objection of ${person.name}` });
    await decide.getByLabel("Decision").selectOption("not_upheld");
    await decide.getByLabel(/Reasons/).fill("Needed to pay you from the first month");
    await decide.getByRole("button", { name: "Record the decision" }).click();
    await expect(page.getByRole("status")).toContainText("The decision is recorded. The person is told.");
    await expect(objection).toContainText("Not upheld");
    await expectAccessible(page, testInfo, "objections");
    await signOut(page);
  });
});
