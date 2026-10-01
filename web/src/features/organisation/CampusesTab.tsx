import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, patch, post } from "../../api/client";
import { ORG_WRITE_ROLES, hasAnyRole, type CampusDetail, type Me } from "../../api/types";
import { Messages } from "./Messages";
import { useAction } from "./useAction";

const EMPTY = { code: "", name: "", address: "", region: "" };
type Draft = typeof EMPTY;

/** GSA's campuses (item 1.25): rarely changed, but kept here rather than by a developer. */
export function CampusesTab({ me }: { me: Me }) {
  const [campuses, setCampuses] = useState<CampusDetail[] | null>(null);
  const [editing, setEditing] = useState<CampusDetail | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loadError, setLoadError] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, ORG_WRITE_ROLES);

  const load = useCallback(() => {
    getAll<CampusDetail>("/org/campuses/")
      .then(setCampuses)
      .catch((err) => setLoadError(errorMessage(err, "Could not load the campuses.")));
  }, []);
  const { busy, error, notice, run } = useAction(load);

  useEffect(load, [load]);

  function open(campus: CampusDetail | "new") {
    setEditing(campus);
    setDraft(campus === "new" ? EMPTY : { code: campus.code, name: campus.name, address: campus.address, region: campus.region });
  }

  function save(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      if (editing === "new" || editing === null) await post("/org/campuses/", draft);
      else await patch(`/org/campuses/${editing.id}/`, draft);
      setEditing(null);
      return `${draft.name} saved.`;
    });
  }

  const set = (key: keyof Draft, value: string) => setDraft({ ...draft, [key]: value });

  return (
    <section aria-labelledby="campuses-heading">
      <h2 id="campuses-heading" className="sr-only">
        Campuses
      </h2>
      <Messages error={loadError ?? error} notice={notice} />
      {campuses === null && !loadError && <p className="loading">Loading…</p>}
      {campuses !== null && (
        <ul className="plain accounts" aria-label="Campuses">
          {campuses.map((campus) => (
            <li key={campus.id}>
              <div>
                <strong>{campus.name}</strong> <span className="muted small">{campus.code}</span>
                <br />
                <span className="muted small">
                  {[campus.address, campus.region].filter(Boolean).join(" · ") || "No address on file"}
                </span>
              </div>
              {mayWrite && (
                <div className="actions">
                  <button className="link" onClick={() => open(campus)} aria-label={`Change ${campus.name}`}>
                    Change
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
            Add a campus
          </button>
        </div>
      )}
      {editing !== null && (
        <form className="card-block stack" onSubmit={save} aria-label={editing === "new" ? "New campus" : `Change ${draft.name}`}>
          <div className="grid2">
            <label>
              Code
              <input value={draft.code} onChange={(e) => set("code", e.target.value)} maxLength={10} required />
            </label>
            <label>
              Name
              <input value={draft.name} onChange={(e) => set("name", e.target.value)} maxLength={120} required />
            </label>
            <label>
              Address
              <input value={draft.address} onChange={(e) => set("address", e.target.value)} maxLength={255} />
            </label>
            <label>
              Region
              <input value={draft.region} onChange={(e) => set("region", e.target.value)} maxLength={80} />
            </label>
          </div>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Save the campus
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
