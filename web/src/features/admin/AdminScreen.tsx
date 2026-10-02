import {
  ACCOUNT_ROLES,
  ACCOUNT_WRITE_ROLES,
  AUDIT_ROLES,
  CORRECTION_ROLES,
  NOTICE_ROLES,
  RETENTION_ROLES,
  REVIEW_ROLES,
  hasAnyRole,
  type Me,
} from "../../api/types";
import { AccessReviewTab } from "./AccessReviewTab";
import { AccountsTab } from "./AccountsTab";
import { AuditTab } from "./AuditTab";
import { BreachesTab } from "./BreachesTab";
import { CorrectionsTab } from "./CorrectionsTab";
import { NoticeTab } from "./NoticeTab";
import { RetentionTab } from "./RetentionTab";
import { StaffTab } from "./StaffTab";

interface Props {
  me: Me;
  campusId: number | null;
  path: string;
  onNavigate: (to: string) => void;
}

const TABS = [
  { key: "accounts", path: "/admin", label: "Accounts", roles: ACCOUNT_ROLES },
  { key: "staff", path: "/admin/staff", label: "Staff without an account", roles: ACCOUNT_WRITE_ROLES },
  { key: "review", path: "/admin/review", label: "Access review", roles: REVIEW_ROLES },
  { key: "audit", path: "/admin/audit", label: "Audit log", roles: AUDIT_ROLES },
  { key: "corrections", path: "/admin/corrections", label: "Correction requests", roles: CORRECTION_ROLES },
  { key: "notice", path: "/admin/privacy-notice", label: "Privacy notice", roles: NOTICE_ROLES },
  { key: "retention", path: "/admin/retention", label: "Retention", roles: RETENTION_ROLES },
  { key: "breaches", path: "/admin/breaches", label: "Breaches", roles: RETENTION_ROLES },
] as const;

/** Accounts and access, the audit log, and privacy: who can sign in and see what, what was done, and people's rights. */
export function AdminScreen({ me, campusId, path, onNavigate }: Props) {
  const tabs = TABS.filter((t) => hasAnyRole(me, t.roles));
  const current = tabs.find((t) => t.path === path) ?? tabs[0];

  return (
    <>
      <h1>Admin</h1>
      {current === undefined ? (
        <p className="muted">Your role has no accounts to look after.</p>
      ) : (
        <>
          <div className="tabs" role="tablist" aria-label="Admin">
            {tabs.map((t) => (
              <button
                key={t.key}
                id={`admin-tab-${t.key}`}
                role="tab"
                aria-selected={t.key === current.key}
                aria-controls="admin-panel"
                className={t.key === current.key ? "tab active" : "tab"}
                onClick={() => onNavigate(t.path)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div id="admin-panel" role="tabpanel" aria-labelledby={`admin-tab-${current.key}`}>
            {current.key === "accounts" && <AccountsTab me={me} campusId={campusId} />}
            {current.key === "staff" && <StaffTab campusId={campusId} onNavigate={onNavigate} />}
            {current.key === "review" && <AccessReviewTab me={me} campusId={campusId} onNavigate={onNavigate} />}
            {current.key === "audit" && <AuditTab />}
            {current.key === "corrections" && <CorrectionsTab onNavigate={onNavigate} />}
            {current.key === "notice" && <NoticeTab me={me} />}
            {current.key === "retention" && <RetentionTab me={me} />}
            {current.key === "breaches" && <BreachesTab me={me} />}
          </div>
        </>
      )}
    </>
  );
}
