import { ORG_WRITE_ROLES, hasAnyRole, type Me } from "../../api/types";
import { CampusesTab } from "./CampusesTab";
import { ChartTab } from "./ChartTab";
import { GradesTab } from "./GradesTab";
import { PostsTab } from "./PostsTab";
import { TrainingTab } from "./TrainingTab";
import { UnitsTab } from "./UnitsTab";

interface Props {
  me: Me;
  campusId: number | null;
  path: string;
  onNavigate: (to: string) => void;
}

// The chart comes first (item 2.30): the establishment as people picture it, units within units.
const TABS = [
  { key: "chart", path: "/organisation", label: "Chart" },
  { key: "units", path: "/organisation/units", label: "Units" },
  { key: "posts", path: "/organisation/posts", label: "Posts" },
  { key: "grades", path: "/organisation/grades", label: "Salary scales" },
  { key: "campuses", path: "/organisation/campuses", label: "Campuses" },
  { key: "training", path: "/organisation/training", label: "Required training" },
] as const;

/** The establishment: posts, the units they sit in, the chart they make (item 1.10), the grades they are paid on,
 * the campuses (item 1.25), and the training each post requires (item 5.24). */
export function OrganisationScreen({ me, campusId, path, onNavigate }: Props) {
  // Any other address, the chart's older one included, opens the chart.
  const current = TABS.find((t) => t.path === path) ?? TABS[0];
  const keeps = hasAnyRole(me, ORG_WRITE_ROLES);
  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Organisation</h1>
          <p className="muted lead">
            Campuses, units, posts, salary scales and the training posts require.
            {keeps ? "" : " Changes are made by the HR Manager or an administrator."}
          </p>
        </div>
      </div>
      <div className="tabs no-print" role="tablist" aria-label="Organisation">
        {TABS.map((t) => (
          <button
            key={t.key}
            id={`org-tab-${t.key}`}
            role="tab"
            aria-selected={t.key === current.key}
            aria-controls="org-panel"
            className={t.key === current.key ? "tab active" : "tab"}
            onClick={() => onNavigate(t.path)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id="org-panel" role="tabpanel" aria-labelledby={`org-tab-${current.key}`}>
        {current.key === "posts" && <PostsTab me={me} campusId={campusId} />}
        {current.key === "units" && <UnitsTab me={me} campusId={campusId} />}
        {current.key === "chart" && <ChartTab campusId={campusId} />}
        {current.key === "grades" && <GradesTab me={me} />}
        {current.key === "campuses" && <CampusesTab me={me} />}
        {current.key === "training" && <TrainingTab me={me} />}
      </div>
    </>
  );
}
