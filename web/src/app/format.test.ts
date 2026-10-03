import { describe, expect, it } from "vitest";
import { dmy, dmyTime, gyd, inDays, initials, longDate, num, since } from "./format";

describe("figures and dates", () => {
  it("reads numbers that arrive as strings or nothing", () => {
    expect(num("2.50")).toBe(2.5);
    expect(num(3)).toBe(3);
    expect(num(null)).toBe(0);
    expect(num(undefined)).toBe(0);
  });

  it("writes days the way people say them", () => {
    expect(inDays(1)).toBe("1 day");
    expect(inDays("1.00")).toBe("1 day");
    expect(inDays(2)).toBe("2 days");
    expect(inDays("3.50")).toBe("3.5 days");
    expect(inDays(0)).toBe("0 days");
    expect(inDays(null)).toBe("0 days");
  });

  it("writes dates day first, as in Guyana", () => {
    expect(dmy("2026-03-02")).toBe("02/03/2026");
    expect(dmy("2026-11-16T09:30:00-04:00")).toBe("16/11/2026");
    expect(dmy(null)).toBe("");
    expect(dmy("")).toBe("");
  });

  it("writes a date and time with the day first", () => {
    expect(dmyTime("2026-10-01T14:05:00")).toMatch(/^01\/10\/2026, 14:05$/);
  });

  it("shortens a name to initials for the phone's top bar", () => {
    expect(initials("Natasha Khan")).toBe("NK");
    expect(initials("Indira Devi Narine")).toBe("IN");
    expect(initials("  asha   persaud ")).toBe("AP");
    expect(initials("Admin")).toBe("A");
    expect(initials("")).toBe("");
  });

  it("writes Guyana dollars with two decimals and thousands separators", () => {
    expect(gyd(250000)).toBe("G$250,000.00");
    expect(gyd("750.5")).toBe("G$750.50");
    expect(gyd(null)).toBe("");
    expect(gyd("")).toBe("");
  });

  it("writes the day in full, the same on every device, for Home", () => {
    expect(longDate("2026-10-02")).toBe("Friday 2 October 2026");
    expect(longDate("2027-01-01T08:00:00Z")).toBe("Friday 1 January 2027");
  });

  it("says how long someone has been in post", () => {
    expect(since("2019-09-02", "2026-10-02")).toBe("7 years");
    expect(since("2025-10-02", "2026-10-02")).toBe("1 year");
    expect(since("2026-07-01", "2026-10-02")).toBe("3 months");
    expect(since("2026-09-01", "2026-10-02")).toBe("1 month");
    expect(since("2026-09-28", "2026-10-02")).toBe("Started this month");
  });
});
