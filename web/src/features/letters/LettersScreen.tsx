import type { Me } from "../../api/types";
import { IssuedTab } from "./IssuedTab";
import { TemplatesTab } from "./TemplatesTab";

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
}

const TABS = [
  { key: "issued", path: "/letters", label: "Issued" },
  { key: "templates", path: "/letters/templates", label: "Templates" },
] as const;

/** Letters (item 1.19): the register of letters issued, and the templates they are written from. A letter is
 * written from the staff file, under Documents. */
export function LettersScreen({ me, path, onNavigate }: Props) {
  const current = TABS.find((t) => t.path === path) ?? TABS[0];
  return (
    <>
      <h1>Letters</h1>
      <p className="muted">Letters are written from a person's file, under Documents.</p>
      <div className="tabs" role="tablist" aria-label="Letters">
        {TABS.map((t) => (
          <button
            key={t.key}
            id={`letters-tab-${t.key}`}
            role="tab"
            aria-selected={t.key === current.key}
            aria-controls="letters-panel"
            className={t.key === current.key ? "tab active" : "tab"}
            onClick={() => onNavigate(t.path)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id="letters-panel" role="tabpanel" aria-labelledby={`letters-tab-${current.key}`}>
        {current.key === "issued" && <IssuedTab />}
        {current.key === "templates" && <TemplatesTab me={me} />}
      </div>
    </>
  );
}
