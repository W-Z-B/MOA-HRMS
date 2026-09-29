/** Hash-based routing with no dependency. Replace with a router library once approved (ADR 0002). */

import { useEffect, useState } from "react";

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

export const NAV = [
  { path: "/", label: "Dashboard" },
  { path: "/people", label: "People" },
  { path: "/leave", label: "Leave" },
  { path: "/attendance", label: "Attendance" },
  { path: "/appraisals", label: "Appraisals" },
  { path: "/payroll", label: "Payroll" },
  { path: "/reports", label: "Reports" },
  { path: "/admin", label: "Admin" },
] as const;
