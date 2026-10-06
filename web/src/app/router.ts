/** Hash-based routing with no dependency. A router library is approved in principle (ADR 0009) and is added when a feature needs it. */

import { useEffect, useState } from "react";
import { ADMIN_ROLES, CASE_ROLES, LETTER_ROLES, hasAnyRole, isOfficeUser, type Me } from "../api/types";

const read = () => window.location.hash.replace(/^#/, "") || "/";

export function useHashRoute(): [string, (to: string) => void] {
  const [path, setPath] = useState<string>(read);
  useEffect(() => {
    const onChange = () => setPath(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [path, (to: string) => (window.location.hash = to)];
}

export interface Page {
  path: string;
  label: string;
  /** What the page is for, in a few words: shown beside it in search and on Home. */
  desc: string;
  /** For staff who work in the system; everyone has the rest. `roles` narrows a page further. */
  office: boolean;
  roles?: readonly string[];
  /** A Release 2 placeholder: it has an address, but search does not offer it yet. */
  later?: boolean;
}

/**
 * Every page, in the order search lists them (item 2.30). There is no permanent menu: Home shows each role
 * its pages, and search finds the rest. Who may open a page is the server's rule; this only hides what the
 * server would refuse.
 */
export const PAGES: readonly Page[] = [
  { path: "/", label: "Home", desc: "Your work and your shortcuts", office: false },
  { path: "/to-do", label: "To do", desc: "Decisions waiting for you", office: false },
  { path: "/people", label: "People", desc: "Staff files, appointments and documents", office: true },
  { path: "/organisation", label: "Organisation", desc: "Campuses, units, posts, grades and required training", office: true },
  { path: "/leave", label: "Leave", desc: "Days left, requests and decisions", office: false },
  {
    path: "/letters",
    label: "Letters",
    desc: "Write and issue letters, and check one is genuine",
    office: true,
    roles: LETTER_ROLES,
  },
  { path: "/cases", label: "Cases", desc: "Disciplinary cases and grievances", office: true, roles: CASE_ROLES },
  { path: "/incidents", label: "Incidents", desc: "Report accidents and dangerous occurrences", office: false },
  { path: "/reports", label: "Reports", desc: "Headcount and establishment", office: true },
  { path: "/admin", label: "Admin", desc: "Accounts, privacy requests and setup", office: true, roles: ADMIN_ROLES },
  { path: "/me", label: "My contract", desc: "Your appointment and its terms", office: false },
  { path: "/my-record", label: "My record", desc: "What the School holds about you", office: false },
  { path: "/account", label: "My account", desc: "Password, sign-in email and devices", office: false },
  { path: "/attendance", label: "Attendance", desc: "Shift patterns and attendance records", office: true, later: true },
  { path: "/appraisals", label: "Appraisals", desc: "Appraisal cycles and appraisals", office: true, later: true },
  { path: "/payroll", label: "Payroll", desc: "Payroll periods and the payroll interface", office: true, later: true },
];

/** The pages this person may open. An employee with no other role has their own pages, and nothing they cannot open. */
export const pagesFor = (me: Me) =>
  PAGES.filter((page) => (isOfficeUser(me) || !page.office) && (!page.roles || hasAnyRole(me, page.roles)));

/** The page an address belongs to: the longest page path it starts with, so /people/12 is People. */
export function pageOf(path: string): Page | undefined {
  const bare = path.split("?")[0];
  return PAGES.filter((page) => page.path !== "/")
    .filter((page) => bare === page.path || bare.startsWith(`${page.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0];
}
