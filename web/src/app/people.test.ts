import { describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { actionsFor, jobTitle, shortCampus, usesCampusSwitch } from "./people";

const person = (roles: string[], over: Partial<Me> = {}): Me => ({
  id: 1,
  username: "someone",
  name: "Someone",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: 1,
  position: "Lecturer, Crop Science",
  heads: [],
  campuses: [],
  ...over,
});
const MRP = { id: 1, code: "MRP", name: "Mon Repos Campus" };
const ESQ = { id: 2, code: "ESQ", name: "Essequibo Campus" };

describe("job titles instead of role codes", () => {
  it("names the most senior role, then the units the person heads", () => {
    expect(jobTitle(person(["employee", "supervisor", "hr_officer"], { heads: ["Administration"] }))).toBe(
      "HR Officer · Head of Administration",
    );
    expect(jobTitle(person(["employee", "supervisor"], { heads: ["Livestock Unit"] }))).toBe("Head of Livestock Unit");
    expect(jobTitle(person(["principal"], { position: null }))).toBe("Principal");
    expect(jobTitle(person(["administrator", "hr_manager", "auditor"]))).toBe("System Administrator");
  });

  it("falls back to the post, then to the plain role", () => {
    expect(jobTitle(person(["employee"]))).toBe("Lecturer, Crop Science");
    expect(jobTitle(person(["employee"], { position: null }))).toBe("Employee");
    expect(jobTitle(person([], { position: null }))).toBe("No role yet");
  });
});

describe("the campus switch", () => {
  it("is for office staff who work with more than one campus", () => {
    expect(usesCampusSwitch(person(["hr_officer"], { campuses: [ESQ, MRP] }))).toBe(true);
    expect(usesCampusSwitch(person(["supervisor"], { campuses: [MRP] }))).toBe(false);
    expect(usesCampusSwitch(person(["employee"], { campuses: [ESQ, MRP] }))).toBe(false);
    expect(usesCampusSwitch(person(["principal"], { campuses: undefined }))).toBe(false);
  });

  it("shortens campus names where space is short", () => {
    expect(shortCampus("Mon Repos Campus")).toBe("Mon Repos");
    expect(shortCampus("Essequibo")).toBe("Essequibo");
  });
});

describe("actions from search", () => {
  const labels = (me: Me) => actionsFor(me).map((a) => a.label);

  it("offers HR the actions of its work as well as its own", () => {
    expect(labels(person(["employee", "hr_officer"]))).toEqual([
      "Request leave",
      "New employee",
      "Write a letter",
      "Invite new starters",
      "Hand over my decisions while away",
      "Report an incident",
      "Ask for a correction to my record",
    ]);
  });

  it("offers an employee their own actions, and someone with no staff record what needs none", () => {
    expect(labels(person(["employee"]))).toEqual(["Request leave", "Report an incident", "Ask for a correction to my record"]);
    expect(labels(person(["principal"], { employee_id: null }))).toEqual(["Report an incident", "Open the headcount report"]);
    expect(actionsFor(person(["employee"])).find((a) => a.label === "Report an incident")?.to).toBe("/incidents/new");
  });
});
