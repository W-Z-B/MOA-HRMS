import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, patch, post, remove } from "../../api/client";
import { ORG_WRITE_ROLES, hasAnyRole, type Grade, type Me, type OrgUnit, type Position } from "../../api/types";
import { Messages } from "./Messages";
import { useAction } from "./useAction";

const EMPTY = { number: "", title: "", org_unit: "", grade: "", fte: "1", status: "approved" };
type Draft = typeof EMPTY;
const STATUS: [Position["status"], string][] = [
  ["approved", "Approved"],
  ["frozen", "Frozen"],
  ["abolished", "Abolished"],
];

/** The establishment: every post, where it sits, its grade, and who holds it (item 1.25). */
export function PostsTab({ me, campusId }: { me: Me; campusId: number | null }) {
  const [posts, setPosts] = useState<Position[] | null>(null);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [unit, setUnit] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<Position | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loadError, setLoadError] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, ORG_WRITE_ROLES);

  const params = new URLSearchParams();
  if (campusId) params.set("campus", String(campusId));
  if (unit) params.set("org_unit", unit);
  if (status) params.set("status", status);
  const query = params.toString();

  const load = useCallback(() => {
    getAll<Position>(`/org/positions/${query ? `?${query}` : ""}`)
      .then(setPosts)
      .catch((err) => setLoadError(errorMessage(err, "Could not load the posts.")));
  }, [query]);
  const { busy, error, notice, run } = useAction(load);

  useEffect(load, [load]);
  useEffect(() => {
    getAll<OrgUnit>(`/org/units/${campusId ? `?campus=${campusId}` : ""}`).then(setUnits).catch(() => setUnits([]));
    getAll<Grade>("/org/grades/").then(setGrades).catch(() => setGrades([]));
  }, [campusId]);

  function open(position: Position | "new") {
    setEditing(position);
    setDraft(
      position === "new"
        ? EMPTY
        : {
            number: position.number,
            title: position.title,
            org_unit: String(position.org_unit),
            grade: String(position.grade),
            fte: position.fte,
            status: position.status,
          },
    );
  }

  function save(e: FormEvent) {
    e.preventDefault();
    const body = { ...draft, org_unit: Number(draft.org_unit), grade: Number(draft.grade) };
    void run(async () => {
      if (editing === "new" || editing === null) await post("/org/positions/", body);
      else await patch(`/org/positions/${editing.id}/`, body);
      setEditing(null);
      return `Post ${draft.number} saved.`;
    });
  }

  const drop = (position: Position) =>
    run(async () => {
      await remove(`/org/positions/${position.id}/`);
      return `Post ${position.number} removed.`;
    });

  const vacant = posts?.filter((p) => p.status === "approved" && p.is_vacant).length ?? 0;
  const set = (key: keyof Draft, value: string) => setDraft({ ...draft, [key]: value });

  return (
    <section aria-labelledby="posts-heading">
      <h2 id="posts-heading" className="sr-only">
        Posts
      </h2>
      <div className="filters">
        <label>
          <span className="sr-only">Unit</span>
          <select value={unit} onChange={(e) => setUnit(e.target.value)}>
            <option value="">Every unit</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Every status</option>
            {STATUS.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {posts && (
          <span className="muted small" aria-live="polite">
            {posts.length} posts, {vacant} approved and vacant
          </span>
        )}
      </div>
      <Messages error={loadError ?? error} notice={notice} />
      {posts === null && !loadError && <p className="loading">Loading…</p>}
      {posts !== null && posts.length === 0 && <p className="muted">No posts here.</p>}
      {posts !== null && posts.length > 0 && (
        <table className="cards">
          <caption className="sr-only">Posts</caption>
          <thead>
            <tr>
              <th scope="col">Post</th>
              <th scope="col">Title</th>
              <th scope="col">Unit</th>
              <th scope="col">Grade</th>
              <th scope="col">Status</th>
              <th scope="col">Held by</th>
              {mayWrite && <th scope="col">Change</th>}
            </tr>
          </thead>
          <tbody>
            {posts.map((position) => (
              <tr key={position.id}>
                <td data-label="Post">{position.number}</td>
                <td data-label="Title">{position.title}</td>
                <td data-label="Unit">{position.org_unit_name}</td>
                <td data-label="Grade">{position.grade_name}</td>
                <td data-label="Status">{position.status_name}</td>
                <td data-label="Held by">{position.is_vacant ? <span className="muted">Vacant</span> : (position.holder ?? "Filled")}</td>
                {mayWrite && (
                  <td data-label="Change" className="actions">
                    <button className="link" onClick={() => open(position)} aria-label={`Change post ${position.number}`}>
                      Change
                    </button>
                    {position.is_vacant && (
                      <button className="link" disabled={busy} onClick={() => drop(position)} aria-label={`Remove post ${position.number}`}>
                        Remove
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {mayWrite && editing === null && (
        <div className="actions">
          <button className="secondary" onClick={() => open("new")}>
            Add a post
          </button>
        </div>
      )}
      {editing !== null && (
        <form className="card-block stack" onSubmit={save} aria-label={editing === "new" ? "New post" : `Change post ${draft.number}`}>
          <div className="grid2">
            <label>
              Post number
              <input value={draft.number} onChange={(e) => set("number", e.target.value)} maxLength={20} required />
            </label>
            <label>
              Title
              <input value={draft.title} onChange={(e) => set("title", e.target.value)} maxLength={120} required />
            </label>
            <label>
              Unit
              <select value={draft.org_unit} onChange={(e) => set("org_unit", e.target.value)} required>
                <option value="">Choose</option>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name} ({u.campus_name})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Grade
              <select value={draft.grade} onChange={(e) => set("grade", e.target.value)} required>
                <option value="">Choose</option>
                {grades.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.scale_code} {g.code}, step {g.step} (from {g.effective_from})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Full-time equivalent
              <input type="number" min="0.1" max="1" step="0.1" value={draft.fte} onChange={(e) => set("fte", e.target.value)} required />
            </label>
            <label>
              Status
              <select value={draft.status} onChange={(e) => set("status", e.target.value)}>
                {STATUS.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Save the post
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
