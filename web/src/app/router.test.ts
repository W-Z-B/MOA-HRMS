import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { NAV, navFor, useHashRoute } from "./router";

const person = (roles: string[]): Me => ({
  id: 1,
  username: "asha.persaud",
  name: "Asha Persaud",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: 1,
});

describe("navigation by role", () => {
  it("shows an employee only their own leave, contract and account", () => {
    const own = ["Leave", "My contract", "My record", "My account"];
    expect(navFor(person(["employee"])).map((i) => i.label)).toEqual(own);
    expect(navFor(person([])).map((i) => i.label)).toEqual(own);
  });

  it("shows staff who work in the system the whole menu, and Admin only to those who manage accounts", () => {
    expect(navFor(person(["employee", "supervisor"]))).toEqual(NAV.filter((i) => i.label !== "Admin"));
    expect(navFor(person(["hr_officer"]))).toEqual(NAV);
    expect(navFor(person(["auditor"])).map((i) => i.label)).toContain("Admin");
  });
});

describe("hash routing", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("starts on the dashboard and follows the address", async () => {
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
