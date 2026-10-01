/** Hash-based routing with no dependency. A router library is approved in principle (ADR 0009) and is added when a feature needs it. */

import { useEffect, useState } from "react";
import { ACCOUNT_ROLES, hasAnyRole, isOfficeUser, type Me } from "../api/types";

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

/** `office` entries are for staff who work in the system; everyone sees the rest. `roles` narrows an entry further. */
export const NAV = [
  { path: "/", label: "Dashboard", office: true },
  { path: "/people", label: "People", office: true },
  { path: "/leave", label: "Leave", office: false },
  { path: "/me", label: "My contract", office: false },
  { path: "/my-record", label: "My record", office: false },
  { path: "/account", label: "My account", office: false },
  { path: "/attendance", label: "Attendance", office: true },
  { path: "/appraisals", label: "Appraisals", office: true },
  { path: "/payroll", label: "Payroll", office: true },
  { path: "/reports", label: "Reports", office: true },
  { path: "/admin", label: "Admin", office: true, roles: ACCOUNT_ROLES },
] as const;

/** An employee with no other role sees their own leave and contract, and nothing they cannot open. */
export const navFor = (me: Me) =>
  NAV.filter((item) => (isOfficeUser(me) || !item.office) && (!("roles" in item) || hasAnyRole(me, item.roles)));
