import { useEffect, useState } from "react";
import { get } from "../../api/client";
import {
  ACCOUNT_ROLES,
  ACCOUNT_WRITE_ROLES,
  AUDIT_ROLES,
  CORRECTION_ROLES,
  NOTICE_ROLES,
  OBJECTION_ROLES,
  RETENTION_ROLES,
  REVIEW_ROLES,
  SETUP_ROLES,
  hasAnyRole,
  type Me,
  type Paginated,
} from "../../api/types";
import { AccessReviewTab } from "./AccessReviewTab";
import { AccountsTab } from "./AccountsTab";
import { AuditTab } from "./AuditTab";
import { BreachesTab } from "./BreachesTab";
import { CorrectionsTab } from "./CorrectionsTab";
import { HolidaysTab } from "./HolidaysTab";
import { LeaveTypesTab } from "./LeaveTypesTab";
import { NoticeTab } from "./NoticeTab";
import { ObjectionsTab } from "./ObjectionsTab";
import { RetentionTab } from "./RetentionTab";
import { StaffTab } from "./StaffTab";

interface Props {
  me: Me;
  campusId: number | null;
  path: string;
  onNavigate: (to: string) => void;
}

const SECTIONS = [
  { key: "accounts", path: "/admin", label: "Accounts", desc: "Who can sign in, and what each person can do.", roles: ACCOUNT_ROLES },
  {
    key: "staff",
    path: "/admin/staff",
    label: "Staff without an account",
    desc: "People on the staff list who cannot sign in yet.",
    roles: ACCOUNT_WRITE_ROLES,
  },
  {
    key: "review",
    path: "/admin/review",
    label: "Access review",
    desc: "Every role of every account, signed off every three months.",
    roles: REVIEW_ROLES,
  },
  {
    key: "corrections",
    path: "/admin/corrections",
    label: "Correction requests",
    desc: "Requests from staff to correct their record.",
    roles: CORRECTION_ROLES,
  },
  {
    key: "objections",
    path: "/admin/objections",
    label: "Objections",
    desc: "Objections to how a record is used, and parts of records held back.",
    roles: OBJECTION_ROLES,
  },
  {
    key: "notice",
    path: "/admin/privacy-notice",
    label: "Privacy notice",
    desc: "The notice staff read at their first sign-in, and who has read it.",
    roles: NOTICE_ROLES,
  },
  {
    key: "retention",
    path: "/admin/retention",
    label: "Retention",
    desc: "How long each kind of record is kept, and what is due to go.",
    roles: RETENTION_ROLES,
  },
  {
    key: "breaches",
    path: "/admin/breaches",
    label: "Breaches",
    desc: "Breaches of personal data, what was done, and who was told.",
    roles: RETENTION_ROLES,
  },
  { key: "audit", path: "/admin/audit", label: "Audit log", desc: "Every change, with who made it, when and why.", roles: AUDIT_ROLES },
  {
    key: "holidays",
    path: "/admin/holidays",
    label: "Holidays",
    desc: "Public holidays, which leave does not count.",
    roles: SETUP_ROLES,
  },
  {
    key: "leave-types",
    path: "/admin/leave-types",
    label: "Leave types",
    desc: "What happens when a request is for more than the days left.",
    roles: SETUP_ROLES,
  },
] as const;

type Key = (typeof SECTIONS)[number]["key"];

/** Sections grouped by purpose in place of eleven tabs (item 2.30). */
const GROUPS: { label: string; keys: Key[] }[] = [
  { label: "People and access", keys: ["accounts", "staff", "review"] },
  { label: "Privacy", keys: ["corrections", "objections", "notice", "retention", "breaches"] },
  { label: "Records", keys: ["audit"] },
  { label: "Setup", keys: ["holidays", "leave-types"] },
];

/** How many wait in a section, for the sections where something waits. Counted only where the role may look. */
function useCounts(me: Me): Partial<Record<Key, number>> {
  const [counts, setCounts] = useState<Partial<Record<Key, number>>>({});
  const accounts = hasAnyRole(me, ACCOUNT_WRITE_ROLES);
  const corrections = hasAnyRole(me, CORRECTION_ROLES);
  const objections = hasAnyRole(me, OBJECTION_ROLES);
  useEffect(() => {
    let current = true;
    const count = (key: Key, path: string) =>
      get<Paginated<unknown>>(path)
        .then((page) => current && setCounts((was) => ({ ...was, [key]: page.count })))
        .catch(() => undefined);
    if (accounts) count("staff", "/employees/?has_account=0&status=active");
    if (corrections) count("corrections", "/privacy/corrections/?state=open");
    if (objections) count("objections", "/privacy/objections/?state=open");
    return () => {
      current = false;
    };
  }, [accounts, corrections, objections]);
  return counts;
}

/**
 * Accounts and access, privacy, the audit log and setup (item 2.30): sections grouped by purpose, each with
 * what it is for. Each role sees only the sections it can open; the count says where something waits.
 */
export function AdminScreen({ me, campusId, path, onNavigate }: Props) {
  const sections = SECTIONS.filter((s) => hasAnyRole(me, s.roles));
  const current = sections.find((s) => s.path === path) ?? sections[0];
  const counts = useCounts(me);

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Admin</h1>
          <p className="muted lead">Accounts, requests about personal data, and the rules the system follows.</p>
        </div>
      </div>
      {current === undefined ? (
        <p className="muted">Your role has no accounts to look after.</p>
      ) : (
        <div className="admin">
          <nav className="admin-nav" aria-label="Admin sections">
            {GROUPS.map((group) => {
              const shown = sections.filter((s) => (group.keys as readonly string[]).includes(s.key));
              if (shown.length === 0) return null;
              return (
                <div key={group.label} className="admin-group">
                  <h2 className="admin-group-label">{group.label}</h2>
                  <ul>
                    {shown.map((s) => {
                      const waiting = counts[s.key];
                      return (
                        <li key={s.key}>
                          <a
                            href={`#${s.path}`}
                            aria-current={s.key === current.key ? "page" : undefined}
                            onClick={(e) => {
                              e.preventDefault();
                              onNavigate(s.path);
                            }}
                          >
                            <span>{s.label}</span>
                            {waiting ? (
                              <>
                                {" "}
                                <span className="count">
                                  {waiting} <span className="sr-only">waiting</span>
                                </span>
                              </>
                            ) : null}
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </nav>
          <div className="admin-section">
            <div className="stacked admin-section-head">
              <h2 id="admin-section-title">{current.label}</h2>
              <p className="muted">{current.desc}</p>
            </div>
            {current.key === "accounts" && <AccountsTab me={me} campusId={campusId} />}
            {current.key === "staff" && <StaffTab campusId={campusId} onNavigate={onNavigate} />}
            {current.key === "review" && <AccessReviewTab me={me} campusId={campusId} onNavigate={onNavigate} />}
            {current.key === "audit" && <AuditTab />}
            {current.key === "corrections" && <CorrectionsTab onNavigate={onNavigate} />}
            {current.key === "objections" && <ObjectionsTab me={me} />}
            {current.key === "notice" && <NoticeTab me={me} />}
            {current.key === "retention" && <RetentionTab me={me} />}
            {current.key === "breaches" && <BreachesTab me={me} />}
            {current.key === "holidays" && <HolidaysTab me={me} />}
            {current.key === "leave-types" && <LeaveTypesTab me={me} />}
          </div>
        </div>
      )}
    </>
  );
}
