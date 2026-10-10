/** How figures and dates are written everywhere in the application. */

import type { Days } from "../api/types";

export const num = (value: Days | null | undefined): number => Number(value ?? 0);

/** 2 reads as "2 days", 1 as "1 day", 3.5 as "3.5 days". */
export function inDays(value: Days | null | undefined): string {
  const n = num(value);
  return `${parseFloat(n.toFixed(2))} ${n === 1 ? "day" : "days"}`;
}

/** Today, or this minute, by this device's clock, as date and datetime-local inputs write them. */
export function localNow(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}
export const localToday = (): string => localNow().slice(0, 10);

/** 2026-03-02 reads as 02/03/2026. */
export function dmy(iso: string | null | undefined): string {
  if (!iso) return "";
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

export function dmyTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "Natasha Khan" reads as "NK", "Indira Devi Narine" as "IN"; a single name gives one letter. */
export function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

/** "08:02:00" (as the API sends a time field) reads as "08:02". */
export function hm(value: string | null | undefined): string {
  return value ? value.slice(0, 5) : "";
}

export function gyd(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  return `G$${Number(value).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** 2026-10-02 reads as "Friday 2 October 2026", the same on every device. */
export function longDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return `${WEEKDAYS[weekday]} ${day} ${MONTHS[month - 1]} ${year}`;
}

/** How long since a start date, as of a given day: "3 years", "4 months", "Started this month". */
export function since(startIso: string, asAtIso: string): string {
  const [y1, m1, d1] = startIso.slice(0, 10).split("-").map(Number);
  const [y2, m2, d2] = asAtIso.slice(0, 10).split("-").map(Number);
  const months = (y2 - y1) * 12 + (m2 - m1) - (d2 < d1 ? 1 : 0);
  if (months < 1) return "Started this month";
  if (months < 12) return `${months} ${months === 1 ? "month" : "months"}`;
  const years = Math.floor(months / 12);
  return `${years} ${years === 1 ? "year" : "years"}`;
}
