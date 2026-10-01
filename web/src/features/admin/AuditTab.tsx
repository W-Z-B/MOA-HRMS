import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { AuditChainState, AuditChoices, AuditEntry, Paginated } from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

const EMPTY = { action: "", record: "", who: "", employee_no: "", since: "", until: "", q: "" };
type Filters = typeof EMPTY;

function shown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "blank";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return dmy(value);
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function query(filters: Filters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value.trim()) params.set(key, value.trim());
  return params.toString();
}

/**
 * Every audit entry, newest first, with filters and a spreadsheet export, and whether the chain of
 * fingerprints shows that nothing has been changed or removed (item 1.26).
 */
export function AuditTab() {
  const [form, setForm] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [state, setState] = useState<AuditChainState | null>(null);
  const [choices, setChoices] = useState<AuditChoices>({ actions: [], records: [] });
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const search = query(filters);

  useEffect(() => {
    let current = true;
    get<Paginated<AuditEntry>>(`/audit/${search ? `?${search}` : ""}`)
      .then((page) => {
        if (!current) return;
        setEntries(page.results);
        setNext(page.next);
        setCount(page.count);
        setError(null);
      })
      .catch((err) => current && setError(errorMessage(err, "Could not load the audit log.")));
    return () => {
      current = false;
    };
  }, [search]);

  useEffect(() => {
    get<AuditChainState>("/audit/chain/").then(setState).catch(() => setState(null));
    get<AuditChoices>("/audit/choices/").then(setChoices).catch(() => setChoices({ actions: [], records: [] }));
  }, []);

  async function checkNow() {
    setChecking(true);
    setError(null);
    try {
      setState(await post<AuditChainState>("/audit/chain/"));
    } catch (err) {
      setError(errorMessage(err, "The check did not run. Try again."));
    } finally {
      setChecking(false);
    }
  }

  async function showMore() {
    if (!next) return;
    try {
      const page = await get<Paginated<AuditEntry>>(`/audit/${new URL(next, window.location.origin).search}`);
      setEntries((shownSoFar) => [...(shownSoFar ?? []), ...page.results]);
      setNext(page.next);
    } catch (err) {
      setError(errorMessage(err, "Could not load more entries."));
    }
  }

  function apply(e: FormEvent) {
    e.preventDefault();
    setFilters(form);
  }

  const field = (name: keyof Filters) => ({
    value: form[name],
    onChange: (e: { target: { value: string } }) => setForm({ ...form, [name]: e.target.value }),
  });
  const check = state?.latest_check ?? null;

  return (
    <section aria-labelledby="audit-heading">
      <h2 id="audit-heading" className="sr-only">
        Audit log
      </h2>
      {state !== null && (
        <div className="actions chain-state">
          {check === null && (
            <p className="notice">
              The log holds {state.entries} entries and has not been checked against its fingerprints yet.
            </p>
          )}
          {check !== null && check.intact && (
            <p role="status" className="notice good">
              Nothing changed or removed: {check.rows} entries checked {dmyTime(check.checked_at)} by{" "}
              {check.checked_by}.
            </p>
          )}
          {check !== null && !check.intact && (
            <p role="alert" className="notice bad">
              The log has been altered. {check.detail} Found {dmyTime(check.checked_at)}.
            </p>
          )}
          <button className="secondary" disabled={checking} onClick={checkNow}>
            {checking ? "Checking…" : "Check every entry now"}
          </button>
        </div>
      )}
      <form className="sub-form stack" onSubmit={apply} aria-label="Find audit entries">
        <div className="grid2">
          <label>
            What was done
            <select {...field("action")}>
              <option value="">Anything</option>
              {choices.actions.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Kind of record
            <select {...field("record")}>
              <option value="">Any</option>
              {choices.records.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Who did it
            <input {...field("who")} placeholder="Name or username" />
          </label>
          <label>
            About employee number
            <input {...field("employee_no")} placeholder="E0001" />
          </label>
          <label>
            From
            <input type="date" {...field("since")} />
          </label>
          <label>
            To
            <input type="date" {...field("until")} />
          </label>
          <label className="span2">
            Words in the reason
            <input {...field("q")} />
          </label>
        </div>
        <div className="actions">
          <button type="submit">Show</button>
          <a className="button" href={`/api/v1/audit/export/${search ? `?${search}` : ""}`} download>
            Download as a spreadsheet (CSV)
          </a>
        </div>
        <p className="muted small">The download holds what is shown here, up to 100,000 entries, and is itself recorded.</p>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {entries === null && !error && <p className="loading">Loading…</p>}
      {entries !== null && (
        <p className="muted small" aria-live="polite">
          {count === 1 ? "1 entry" : `${count} entries`}
        </p>
      )}
      {entries !== null && entries.length > 0 && (
        <ol className="plain history" aria-label="Audit entries">
          {entries.map((entry) => (
            <li key={entry.id}>
              <p>
                <strong>
                  {entry.record}
                  {entry.entity_id !== null ? ` ${entry.entity_id}` : ""}: {entry.action_name.toLowerCase()}
                </strong>{" "}
                <span className="muted small">
                  by {entry.actor}
                  {entry.actor_username && entry.actor_username !== entry.actor ? ` (${entry.actor_username})` : ""},{" "}
                  {dmyTime(entry.at)}
                  {entry.source_ip ? ` from ${entry.source_ip}` : ""}
                </span>
              </p>
              {entry.employee_no && <p className="small">About {entry.employee_no}</p>}
              {entry.reason && <p className="small">Reason: {entry.reason}</p>}
              {entry.changes.length > 0 && (
                <ul className="small changes">
                  {entry.changes.map((change) => (
                    <li key={change.field}>
                      {change.field} changed from {shown(change.before)} to {shown(change.after)}
                    </li>
                  ))}
                </ul>
              )}
              <p className="muted small">Entry {entry.id}</p>
            </li>
          ))}
        </ol>
      )}
      {next && (
        <div className="actions">
          <button className="secondary" onClick={showMore}>
            Show more
          </button>
        </div>
      )}
    </section>
  );
}
