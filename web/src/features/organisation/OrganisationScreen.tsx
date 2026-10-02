import type { Me } from "../../api/types";
import { CampusesTab } from "./CampusesTab";
import { ChartTab } from "./ChartTab";
import { GradesTab } from "./GradesTab";
import { PostsTab } from "./PostsTab";
import { UnitsTab } from "./UnitsTab";

interface Props {
  me: Me;
  campusId: number | null;
  path: string;
  onNavigate: (to: string) => void;
}

const TABS = [
  { key: "posts", path: "/organisation", label: "Posts" },
  { key: "units", path: "/organisation/units", label: "Units" },
  { key: "chart", path: "/organisation/chart", label: "Chart" },
  { key: "grades", path: "/organisation/grades", label: "Salary scales" },
  { key: "campuses", path: "/organisation/campuses", label: "Campuses" },
] as const;

/** The establishment: posts, the units they sit in, the chart they make (item 1.10), the grades they are paid on,
 * and the campuses (item 1.25). */
export function OrganisationScreen({ me, campusId, path, onNavigate }: Props) {
  const current = TABS.find((t) => t.path === path) ?? TABS[0];
  return (
    <>
      <h1>Organisation</h1>
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
      </div>
    </>
  );
}
