import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, patch, post } from "../../api/client";
import { ORG_WRITE_ROLES, hasAnyRole, type CampusDetail, type Me, type OrgUnit, type Position, type TrainingRequirement } from "../../api/types";
import { Messages } from "./Messages";
import { useAction } from "./useAction";

const EMPTY = { title: "", course_code: "", post_title: "", org_unit: "", campus: "", due_days: "30", renewal_months: "", notes: "" };
type Draft = typeof EMPTY;

function toDraft(r: TrainingRequirement): Draft {
  return {
    title: r.title,
    course_code: r.course_code,
    post_title: r.post_title,
    org_unit: r.org_unit === null ? "" : String(r.org_unit),
    campus: r.campus === null ? "" : String(r.campus),
    due_days: String(r.due_days),
    renewal_months: r.renewal_months === null ? "" : String(r.renewal_months),
    notes: r.notes,
  };
}

function toBody(d: Draft) {
  return {
    title: d.title,
    course_code: d.course_code,
    post_title: d.post_title,
    org_unit: d.org_unit ? Number(d.org_unit) : null,
    campus: d.campus ? Number(d.campus) : null,
    due_days: Number(d.due_days),
    renewal_months: d.renewal_months ? Number(d.renewal_months) : null,
    notes: d.notes,
  };
}

/** Required training by post, unit and campus (item 5.24). The LMS reads this list, enrols the staff it
 * names, reminds them and reports each completion back to their training record. */
export function TrainingTab({ me }: { me: Me }) {
  const [rows, setRows] = useState<TrainingRequirement[] | null>(null);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [campuses, setCampuses] = useState<CampusDetail[]>([]);
  const [titles, setTitles] = useState<string[]>([]);
  const [editing, setEditing] = useState<TrainingRequirement | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loadError, setLoadError] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, ORG_WRITE_ROLES);

  const load = useCallback(() => {
    getAll<TrainingRequirement>("/training/requirements/")
      .then(setRows)
      .catch((err) => setLoadError(errorMessage(err, "Could not load the required training.")));
  }, []);
  const { busy, error, notice, run } = useAction(load);

  useEffect(load, [load]);
  useEffect(() => {
    if (!mayWrite) return;
    getAll<OrgUnit>("/org/units/").then(setUnits).catch(() => setUnits([]));
    getAll<CampusDetail>("/org/campuses/").then(setCampuses).catch(() => setCampuses([]));
    getAll<Position>("/org/positions/")
      .then((posts) => setTitles([...new Set(posts.map((p) => p.title))].sort()))
      .catch(() => setTitles([]));
  }, [mayWrite]);

  function open(row: TrainingRequirement | "new") {
    setEditing(row);
    setDraft(row === "new" ? EMPTY : toDraft(row));
  }

  function save(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      if (editing === "new" || editing === null) await post("/training/requirements/", toBody(draft));
      else await patch(`/training/requirements/${editing.id}/`, toBody(draft));
      setEditing(null);
      return `${draft.title} saved.`;
    });
  }

  function toggle(row: TrainingRequirement) {
    void run(async () => {
      await patch(`/training/requirements/${row.id}/`, { is_active: !row.is_active });
      return row.is_active ? `${row.title} retired.` : `${row.title} required again.`;
    });
  }

  const set = (key: keyof Draft, value: string) => setDraft({ ...draft, [key]: value });
  const renewal = (r: TrainingRequirement) => (r.renewal_months ? `every ${r.renewal_months} months` : "once");

  return (
    <section aria-labelledby="training-heading">
      <h2 id="training-heading" className="sr-only">
        Required training
      </h2>
      <p className="muted">
        Courses staff must take, by post, unit and campus. The learning system enrols the staff named, reminds them, and reports each
        completion to their training record.
      </p>
      <Messages error={loadError ?? error} notice={notice} />
      {rows === null && !loadError && <p className="loading">Loading…</p>}
      {rows !== null && rows.length === 0 && <p className="muted">No required training yet.</p>}
      {rows !== null && rows.length > 0 && (
        <ul className="plain accounts" aria-label="Required training">
          {rows.map((r) => (
            <li key={r.id}>
              <div>
                <strong>{r.title}</strong> {r.course_code && <span className="muted small">{r.course_code}</span>}
                {!r.is_active && <span className="pill">Retired</span>}
                <br />
                <span className="muted small">
                  For {r.applies_to} · due within {r.due_days} days · {renewal(r)}
                </span>
              </div>
              {mayWrite && (
                <div className="actions">
                  <button className="link" onClick={() => open(r)} aria-label={`Change ${r.title}`}>
                    Change
                  </button>
                  <button className="link" onClick={() => toggle(r)} disabled={busy} aria-label={`${r.is_active ? "Retire" : "Require again"} ${r.title}`}>
                    {r.is_active ? "Retire" : "Require again"}
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
            Add required training
          </button>
        </div>
      )}
      {editing !== null && (
        <form className="card-block stack" onSubmit={save} aria-label={editing === "new" ? "New required training" : `Change ${draft.title}`}>
          <div className="grid2">
            <label>
              Course
              <input value={draft.title} onChange={(e) => set("title", e.target.value)} maxLength={160} required />
            </label>
            <label>
              Course code in the LMS
              <input value={draft.course_code} onChange={(e) => set("course_code", e.target.value)} maxLength={40} />
            </label>
            <label>
              Post
              <input list="training-post-titles" value={draft.post_title} onChange={(e) => set("post_title", e.target.value)} maxLength={120} />
              <datalist id="training-post-titles">
                {titles.map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </label>
            <label>
              Unit
              <select value={draft.org_unit} onChange={(e) => set("org_unit", e.target.value)}>
                <option value="">Any unit</option>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.code} {u.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Campus
              <select value={draft.campus} onChange={(e) => set("campus", e.target.value)}>
                <option value="">Every campus</option>
                {campuses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Due within (days)
              <input type="number" min={1} max={730} value={draft.due_days} onChange={(e) => set("due_days", e.target.value)} required />
            </label>
            <label>
              Renew every (months)
              <input type="number" min={1} max={120} value={draft.renewal_months} onChange={(e) => set("renewal_months", e.target.value)} placeholder="Once" />
            </label>
            <label>
              Notes
              <input value={draft.notes} onChange={(e) => set("notes", e.target.value)} />
            </label>
          </div>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Save the requirement
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
