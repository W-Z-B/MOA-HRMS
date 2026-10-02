/** Who the signed-in person is, in words, and what they can start from search (item 2.30). */

import { ACCOUNT_WRITE_ROLES, HR_ROLES, hasAnyRole, isOfficeUser, type Me } from "../api/types";

/** Roles as job titles, most senior first. Supervisor and employee are said through the post and the units headed. */
const ROLE_TITLES: [string, string][] = [
  ["administrator", "System Administrator"],
  ["hr_manager", "HR Manager"],
  ["hr_officer", "HR Officer"],
  ["principal", "Principal"],
  ["finance", "Finance Officer"],
  ["auditor", "Auditor"],
  ["data_protection_officer", "Data Protection Officer"],
  ["ministry_liaison", "Ministry Liaison"],
];

/**
 * A job title, never a system code: "HR Officer · Head of Administration", "Head of Livestock Unit",
 * "Lecturer, Crop Science". The most senior role names the person, then the units they head.
 */
export function jobTitle(me: Me): string {
  const role = ROLE_TITLES.find(([code]) => me.roles.includes(code));
  const heads = (me.heads ?? []).map((unit) => `Head of ${unit}`);
  const parts = [...(role ? [role[1]] : []), ...heads];
  if (parts.length > 0) return parts.join(" · ");
  return me.position ?? (me.roles.includes("employee") ? "Employee" : "No role yet");
}

/** "Mon Repos Campus" reads as "Mon Repos" where space is short. */
export const shortCampus = (name: string) => name.replace(/\s+Campus$/i, "");

/** The campus switch is for people who work with more than one campus. */
export const usesCampusSwitch = (me: Me) => isOfficeUser(me) && (me.campuses?.length ?? 0) > 1;

export interface QuickAction {
  label: string;
  desc: string;
  to: string;
}

/** Things a person can start from search, as well as the pages they open. */
export function actionsFor(me: Me): QuickAction[] {
  const own = me.employee_id !== null;
  const list: QuickAction[] = [];
  if (own) list.push({ label: "Request leave", desc: "Ask for days off", to: "/leave" });
  if (hasAnyRole(me, HR_ROLES)) {
    list.push({ label: "New employee", desc: "Open a staff file", to: "/people/new" });
    list.push({ label: "Write a letter", desc: "Open the person's file, then Write a letter", to: "/people" });
  }
  if (hasAnyRole(me, ACCOUNT_WRITE_ROLES))
    list.push({ label: "Invite new starters", desc: "Staff without an account", to: "/admin/staff" });
  if (isOfficeUser(me) && own)
    list.push({ label: "Hand over my decisions while away", desc: "Name a stand-in", to: "/to-do" });
  list.push({ label: "Report an incident", desc: "An accident, a near miss or a dangerous occurrence", to: "/incidents/new" });
  if (own) list.push({ label: "Ask for a correction to my record", desc: "From My record", to: "/my-record" });
  if (me.roles.includes("principal"))
    list.push({ label: "Open the headcount report", desc: "Active staff on each campus", to: "/reports" });
  return list;
}
