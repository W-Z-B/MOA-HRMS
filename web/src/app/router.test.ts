import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { PAGES, pageOf, pagesFor, useHashRoute } from "./router";

const person = (roles: string[]): Me => ({
  id: 1,
  username: "asha.persaud",
  name: "Asha Persaud",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: 1,
});

describe("pages by role", () => {
  it("gives an employee their Home, their own pages, and where to report an incident", () => {
    const own = ["Home", "To do", "Leave", "Incidents", "My contract", "My record", "My account", "Attendance", "Payroll"];
    expect(pagesFor(person(["employee"])).map((p) => p.label)).toEqual(own);
    expect(pagesFor(person([])).map((p) => p.label)).toEqual(own);
  });

  it("gives staff who work in the system every page, Admin to those with a tab in it, Letters to HR", () => {
    expect(pagesFor(person(["employee", "supervisor"]))).toEqual(
      PAGES.filter((p) => !["Admin", "Letters", "Onboarding"].includes(p.label)),
    );
    expect(pagesFor(person(["finance"])).map((p) => p.label)).not.toContain("Cases");
    expect(pagesFor(person(["hr_officer"]))).toEqual(PAGES);
    expect(pagesFor(person(["auditor"])).map((p) => p.label)).toEqual(expect.arrayContaining(["Admin", "Letters"]));
    expect(pagesFor(person(["finance"])).map((p) => p.label)).not.toContain("Letters");
  });

  it("keeps the Release 2 placeholders apart, and says what every page is for", () => {
    expect(PAGES.filter((p) => p.later).map((p) => p.label)).toEqual(["Appraisals"]);
    expect(PAGES.every((p) => p.desc.length > 0)).toBe(true);
  });

  it("finds the page an address belongs to, for the breadcrumb", () => {
    expect(pageOf("/people/12")?.label).toBe("People");
    expect(pageOf("/people")?.label).toBe("People");
    expect(pageOf("/my-record")?.label).toBe("My record");
    expect(pageOf("/me")?.label).toBe("My contract");
    expect(pageOf("/leave/requests/4?x=1")?.label).toBe("Leave");
    expect(pageOf("/meeting")).toBeUndefined();
    expect(pageOf("/")).toBeUndefined();
  });
});

describe("hash routing", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("starts on Home and follows the address", async () => {
    const { result } = renderHook(() => useHashRoute());
    expect(result.current[0]).toBe("/");
    await act(async () => {
      result.current[1]("/leave/requests/4");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(window.location.hash).toBe("#/leave/requests/4");
    expect(result.current[0]).toBe("/leave/requests/4");
  });
});
