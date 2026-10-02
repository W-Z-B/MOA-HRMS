import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get } from "../../api/client";
import type { HistoryEntry, RecordAsAt } from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

/** Fields of the personal record shown in the "as it stood" view, in reading order. */
const AS_AT_FIELDS: [string, string][] = [
  ["employee_no", "Employee number"],
  ["first_name", "First name"],
  ["other_names", "Other names"],
  ["last_name", "Last name"],
  ["date_of_birth", "Date of birth"],
  ["email", "Email"],
  ["phone", "Phone"],
  ["address", "Address"],
  ["status", "Status"],
  ["national_id", "National ID"],
  ["nis_no", "NIS number"],
  ["tin", "TIN"],
];

function shown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "blank";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return dmy(value);
  return String(value);
}

/** Every change to the file, newest first, and the personal record as it stood on any day. */
export function HistoryTab({ employeeId }: { employeeId: number }) {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [day, setDay] = useState("");
  const [asAt, setAsAt] = useState<RecordAsAt | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<HistoryEntry[]>(`/employees/${employeeId}/history/`)
      .then(setEntries)
      .catch((err) => setError(errorMessage(err, "Could not load the history.")));
  }, [employeeId]);

  async function lookUp(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setAsAt(await get<RecordAsAt>(`/employees/${employeeId}/as-at/?date=${day}`));
    } catch (err) {
      setAsAt(null);
      setError(errorMessage(err, "Could not show the record for that day."));
    }
  }

  return (
    <>
      <form className="sub-form as-at" onSubmit={lookUp} aria-label="Show the record as it stood on a day">
        <label htmlFor="as-at-day">
          Show the personal record as it stood on
          <input id="as-at-day" type="date" value={day} onChange={(e) => setDay(e.target.value)} required />
        </label>
        <button type="submit" className="secondary">
          Show
        </button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {asAt && (
        <section className="card-block" aria-labelledby="as-at-heading">
          <h3 id="as-at-heading">
            As it stood on {dmy(asAt.date)}
            {asAt.current && <span className="muted small"> (unchanged since)</span>}
          </h3>
          <dl>
            {AS_AT_FIELDS.map(([name, label]) => (
              <div key={name}>
                <dt>{label}</dt>
                <dd>{shown(asAt.record[name])}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <h3>Changes</h3>
      {entries === null && !error && <p className="loading">Loading…</p>}
      {entries !== null && entries.length === 0 && <p className="muted">No changes recorded yet.</p>}
      {entries !== null && entries.length > 0 && (
        <ol className="plain history">
          {entries.map((entry) => (
            <li key={entry.id}>
              <p>
                <strong>
                  {entry.record}: {entry.action_name.toLowerCase()}
                </strong>{" "}
                <span className="muted small">
                  by {entry.actor}, {dmyTime(entry.at)}
                </span>
              </p>
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
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
