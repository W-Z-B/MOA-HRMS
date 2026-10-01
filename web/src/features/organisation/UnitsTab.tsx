import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, patch, post, remove } from "../../api/client";
import { ORG_WRITE_ROLES, hasAnyRole, type Campus, type Employee, type Me, type OrgUnit } from "../../api/types";
import { Messages } from "./Messages";
import { useAction } from "./useAction";

const EMPTY = { code: "", name: "", unit_type: "department", campus: "", parent: "", head: "" };
type Draft = typeof EMPTY;
const TYPES: [OrgUnit["unit_type"], string][] = [
  ["department", "Department"],
  ["farm", "Farm"],
  ["unit", "Unit"],
  ["section", "Section"],
];

/** Units in the order they sit: each under the unit above it, campus by campus. */
function ordered(units: OrgUnit[]): { unit: OrgUnit; depth: number }[] {
  const children = new Map<number | null, OrgUnit[]>();
  for (const unit of units) {
    const key = unit.parent !== null && units.some((u) => u.id === unit.parent) ? unit.parent : null;
    children.set(key, [...(children.get(key) ?? []), unit]);
  }
  const rows: { unit: OrgUnit; depth: number }[] = [];
  const walk = (parent: number | null, depth: number) => {
    for (const unit of children.get(parent) ?? []) {
      rows.push({ unit, depth });
      walk(unit.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

/** Departments, farms, units and sections, how they nest, and who heads each (item 1.25). */
export function UnitsTab({ me, campusId }: { me: Me; campusId: number | null }) {
  const [units, setUnits] = useState<OrgUnit[] | null>(null);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [staff, setStaff] = useState<Employee[]>([]);
  const [editing, setEditing] = useState<OrgUnit | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loadError, setLoadError] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, ORG_WRITE_ROLES);

  const load = useCallback(() => {
    getAll<OrgUnit>(`/org/units/${campusId ? `?campus=${campusId}` : ""}`)
      .then(setUnits)
      .catch((err) => setLoadError(errorMessage(err, "Could not load the units.")));
  }, [campusId]);
  const { busy, error, notice, run } = useAction(load);

  useEffect(load, [load]);
  useEffect(() => {
    getAll<Campus>("/org/campuses/").then(setCampuses).catch(() => setCampuses([]));
  }, []);

  function open(unit: OrgUnit | "new") {
    setEditing(unit);
    setDraft(
      unit === "new"
        ? { ...EMPTY, campus: campusId ? String(campusId) : "" }
        : {
            code: unit.code,
            name: unit.name,
            unit_type: unit.unit_type,
            campus: String(unit.campus),
            parent: unit.parent ? String(unit.parent) : "",
            head: unit.head ? String(unit.head) : "",
          },
    );
  }

  // Who can head a unit: the active staff of its campus, fetched when the form chooses the campus.
  useEffect(() => {
    if (editing === null || !draft.campus) return;
    getAll<Employee>(`/employees/?campus=${draft.campus}&status=active`).then(setStaff).catch(() => setStaff([]));
  }, [editing, draft.campus]);

  function save(e: FormEvent) {
    e.preventDefault();
    const body = {
      ...draft,
      campus: Number(draft.campus),
      parent: draft.parent ? Number(draft.parent) : null,
      head: draft.head ? Number(draft.head) : null,
    };
    void run(async () => {
      if (editing === "new" || editing === null) await post("/org/units/", body);
      else await patch(`/org/units/${editing.id}/`, body);
      setEditing(null);
      return `${draft.name} saved.`;
    });
  }

  const drop = (unit: OrgUnit) =>
    run(async () => {
      await remove(`/org/units/${unit.id}/`);
      return `${unit.name} removed.`;
    });

  const set = (key: keyof Draft, value: string) => setDraft({ ...draft, [key]: value });
  const parents = (units ?? []).filter(
    (u) => String(u.campus) === draft.campus && (editing === "new" || editing === null || u.id !== editing.id),
  );

  return (
    <section aria-labelledby="units-heading">
      <h2 id="units-heading" className="sr-only">
        Units
      </h2>
      <Messages error={loadError ?? error} notice={notice} />
      {units === null && !loadError && <p className="loading">Loading…</p>}
      {units !== null && units.length === 0 && <p className="muted">No units here.</p>}
      {units !== null && units.length > 0 && (
        <ul className="plain accounts" aria-label="Units">
          {ordered(units).map(({ unit, depth }) => (
            <li key={unit.id} className="unit" style={{ marginLeft: `${Math.min(depth, 4) * 16}px` }}>
              <div>
                <strong>{unit.name}</strong> <span className="chip">{unit.unit_type_name}</span>
                <br />
                <span className="muted small">
                  {unit.code} · {unit.campus_name}
                  {unit.parent_name ? ` · under ${unit.parent_name}` : ""}
                  {unit.head_name ? ` · headed by ${unit.head_name}` : ""}
                </span>
              </div>
              {mayWrite && (
                <div className="actions">
                  <button className="link" onClick={() => open(unit)} aria-label={`Change ${unit.name}`}>
                    Change
                  </button>
                  <button className="link" disabled={busy} onClick={() => drop(unit)} aria-label={`Remove ${unit.name}`}>
                    Remove
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {mayWrite && editing === null && (
        <div className="actions">
          <button className="secondary" onClick={() => open("new")}>
            Add a unit
          </button>
        </div>
      )}
      {editing !== null && (
        <form className="card-block stack" onSubmit={save} aria-label={editing === "new" ? "New unit" : `Change ${draft.name}`}>
          <div className="grid2">
            <label>
              Code
              <input value={draft.code} onChange={(e) => set("code", e.target.value)} maxLength={20} required />
            </label>
            <label>
              Name
              <input value={draft.name} onChange={(e) => set("name", e.target.value)} maxLength={120} required />
            </label>
            <label>
              Kind
              <select value={draft.unit_type} onChange={(e) => set("unit_type", e.target.value)}>
                {TYPES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Campus
              <select
                value={draft.campus}
                onChange={(e) => setDraft({ ...draft, campus: e.target.value, parent: "", head: "" })}
                required
              >
                <option value="">Choose</option>
                {campuses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Sits under
              <select value={draft.parent} onChange={(e) => set("parent", e.target.value)}>
                <option value="">Nothing (top level)</option>
                {parents.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Headed by
              <select value={draft.head} onChange={(e) => set("head", e.target.value)}>
                <option value="">Nobody yet</option>
                {staff.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name} ({person.employee_no})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted small">The head of a unit decides the leave of the staff in it.</p>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Save the unit
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
