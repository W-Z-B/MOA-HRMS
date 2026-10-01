/** How figures and dates are written everywhere in the application. */

import type { Days } from "../api/types";

export const num = (value: Days | null | undefined): number => Number(value ?? 0);

/** 2 reads as "2 days", 1 as "1 day", 3.5 as "3.5 days". */
export function inDays(value: Days | null | undefined): string {
  const n = num(value);
  return `${parseFloat(n.toFixed(2))} ${n === 1 ? "day" : "days"}`;
}

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

export function gyd(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  return `G$${Number(value).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
