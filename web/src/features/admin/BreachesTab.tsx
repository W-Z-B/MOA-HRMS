import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, plainMessage, post } from "../../api/client";
import { RETENTION_WRITE_ROLES, hasAnyRole, type Breach, type Me, type Paginated } from "../../api/types";
import { dmyTime } from "../../app/format";

const EMPTY = { discovered_at: "", happened: "", summary: "", data_affected: "", people_affected: "", risk: "medium" };
const FOLLOW_UP = [
  ["contained_at", "Contained"],
  ["commissioner_told_at", "Data Protection Commissioner told"],
  ["people_told_at", "The people affected told"],
] as const;

/** A datetime from the server as the value of a datetime-local field, in the browser's time. */
function local(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** The breach register (item 1.32): what happened, to whose data, and what was done about it. */
export function BreachesTab({ me }: { me: Me }) {
  const [breaches, setBreaches] = useState<Breach[] | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [adding, setAdding] = useState(false);
  const [edits, setEdits] = useState<Record<number, Partial<Record<string, string>>>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, RETENTION_WRITE_ROLES);

  const load = useCallback(() => {
    get<Paginated<Breach>>("/privacy/breaches/")
      .then((page) => setBreaches(page.results))
      .catch((err) => setError(errorMessage(err, "Could not load the breach register.")));
  }, []);

  useEffect(load, [load]);

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    } finally {
      setBusy(false);
    }
  }

  function record(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      const made = await post<Breach>("/privacy/breaches/", {
        ...form,
        people_affected: form.people_affected ? Number(form.people_affected) : null,
      });
      setForm(EMPTY);
      setAdding(false);
      return `Recorded as ${made.reference}. The administrators have been told.`;
    });
  }

  const value = (breach: Breach, key: string) => edits[breach.id]?.[key] ?? local(breach[key as keyof Breach] as string | null);
  const setValue = (breach: Breach, key: string, next: string) =>
    setEdits({ ...edits, [breach.id]: { ...edits[breach.id], [key]: next } });

  const save = (breach: Breach) =>
    run(async () => {
      const changes = Object.fromEntries(
        Object.entries(edits[breach.id] ?? {}).map(([key, next]) => [key, next === "" ? null : next]),
      );
      await patch(`/privacy/breaches/${breach.id}/`, changes);
      setEdits({ ...edits, [breach.id]: {} });
      return `${breach.reference} updated.`;
    });
  const close = (breach: Breach) =>
    run(async () => {
      await post(`/privacy/breaches/${breach.id}/close/`);
      return `${breach.reference} closed.`;
    });

  const field = (name: keyof typeof EMPTY) => ({
    value: form[name],
    onChange: (e: { target: { value: string } }) => setForm({ ...form, [name]: e.target.value }),
  });

  return (
    <section aria-labelledby="breaches-heading">
      <h2 id="breaches-heading" className="sr-only">
        Breach register
      </h2>
      <p className="muted">
        Record every personal data breach, however small: what happened, whose data, and what was done. Recording one
        tells the administrators at once.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {mayWrite && !adding && (
        <div className="actions">
          <button onClick={() => setAdding(true)}>Record a breach</button>
        </div>
      )}
      {adding && (
        <form className="card-block stack" onSubmit={record} aria-label="Record a breach">
          <div className="grid2">
            <label>
              Discovered
              <input type="datetime-local" {...field("discovered_at")} required />
            </label>
            <label>
              When it happened, if known
              <input {...field("happened")} maxLength={160} />
            </label>
            <label>
              People affected, if known
              <input type="number" min={0} inputMode="numeric" {...field("people_affected")} />
            </label>
            <label>
              Risk to them
              <select {...field("risk")}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
          </div>
          <label>
            What happened
            <textarea {...field("summary")} rows={3} required />
          </label>
          <label>
            What personal data, and whose
            <textarea {...field("data_affected")} rows={2} required />
          </label>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setAdding(false)}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Record it
            </button>
          </div>
        </form>
      )}
      {breaches !== null && breaches.length === 0 && <p className="muted">No breaches recorded.</p>}
      {breaches !== null && breaches.length > 0 && (
        <ul className="plain accounts" aria-label="Breaches">
          {breaches.map((breach) => (
            <li key={breach.id} className={breach.closed_at ? "state-switched_off" : "state-invited"}>
              <div>
                <strong>{breach.reference}</strong>{" "}
                <span className={`chip chip-risk-${breach.risk}`}>Risk: {breach.risk_name.toLowerCase()}</span>{" "}
                <span className="chip">{breach.closed_at ? "Closed" : breach.contained_at ? "Contained" : "Open"}</span>
                <br />
                <span className="small">{breach.summary}</span>
                <br />
                <span className="muted small">
                  {breach.data_affected}
                  {breach.people_affected !== null ? ` · ${breach.people_affected} people` : ""} · discovered{" "}
                  {dmyTime(breach.discovered_at)}
                  {breach.recorded_by ? ` · recorded by ${breach.recorded_by}` : ""}
                </span>
                {breach.actions && <p className="small">Done: {breach.actions}</p>}
              </div>
              {mayWrite && !breach.closed_at && (
                <div className="stack">
                  <div className="grid2">
                    {FOLLOW_UP.map(([key, label]) => (
                      <label key={key}>
                        {label}
                        <input
                          type="datetime-local"
                          value={value(breach, key)}
                          onChange={(e) => setValue(breach, key, e.target.value)}
                        />
                      </label>
                    ))}
                  </div>
                  <label>
                    What has been done
                    <textarea
                      rows={2}
                      value={edits[breach.id]?.actions ?? breach.actions}
                      onChange={(e) => setValue(breach, "actions", e.target.value)}
                    />
                  </label>
                  <div className="actions">
                    <button
                      className="secondary"
                      disabled={busy || Object.keys(edits[breach.id] ?? {}).length === 0}
                      onClick={() => save(breach)}
                    >
                      Save {breach.reference}
                    </button>
                    <button disabled={busy || !breach.contained_at} onClick={() => close(breach)}>
                      Close {breach.reference}
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
