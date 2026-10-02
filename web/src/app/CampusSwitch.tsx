import type { Campus } from "../api/types";
import { shortCampus } from "./people";

interface Props {
  campuses: Campus[];
  value: number | null;
  onChange: (id: number | null) => void;
}

/** All campuses or one: narrows every list and figure, on every page, until changed. */
export function CampusSwitch({ campuses, value, onChange }: Props) {
  const choices: { id: number | null; label: string }[] = [
    { id: null, label: "All campuses" },
    ...campuses.map((c) => ({ id: c.id, label: shortCampus(c.name) })),
  ];
  return (
    <div className="campus-switch" role="group" aria-label="Campus">
      {choices.map((choice) => (
        <button
          key={choice.label}
          type="button"
          aria-pressed={value === choice.id}
          className={value === choice.id ? "active" : undefined}
          onClick={() => onChange(choice.id)}
        >
          {choice.label}
        </button>
      ))}
    </div>
  );
}
