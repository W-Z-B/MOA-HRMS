import { useCallback, useEffect, useState } from "react";
import { errorMessage, get, plainMessage, post } from "../../api/client";
import type { CorrectionRequest, Paginated } from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

/**
 * Requests to correct a record (item 1.31): HR corrects the record and says so, or says why not. The
 * correction itself is made on the staff record, where the change keeps its reason.
 */
export function CorrectionsTab({ onNavigate }: { onNavigate: (to: string) => void }) {
  const [state, setState] = useState("open");
  const [requests, setRequests] = useState<CorrectionRequest[] | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<CorrectionRequest>>(`/privacy/corrections/${state ? `?state=${state}` : ""}`)
      .then((page) => setRequests(page.results))
      .catch((err) => setError(errorMessage(err, "Could not load the requests.")));
  }, [state]);

  useEffect(load, [load]);

  async function decide(request: CorrectionRequest, outcome: "corrected" | "declined") {
    setBusy(request.id);
    setError(null);
    setNotice(null);
    try {
      await post(`/privacy/corrections/${request.id}/decide/`, { outcome, note: notes[request.id] ?? "" });
      setNotice(
        outcome === "corrected"
          ? `${request.employee_name} is told the record has been corrected.`
          : `${request.employee_name} is told the record was not changed, and why.`,
      );
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="corrections-tab-heading">
      <h2 id="corrections-tab-heading" className="sr-only">
        Correction requests
      </h2>
      <div className="filters">
        <label>
          <span className="sr-only">Show</span>
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="open">Waiting for an answer</option>
            <option value="corrected">Corrected</option>
            <option value="declined">Not changed</option>
            <option value="">All</option>
          </select>
        </label>
      </div>
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
      {requests === null && !error && <p className="loading">Loading…</p>}
      {requests !== null && requests.length === 0 && <p className="muted">No requests here.</p>}
      {requests !== null && requests.length > 0 && (
        <ul className="plain accounts" aria-label="Correction requests">
          {requests.map((r) => (
            <li key={r.id} className={r.overdue ? "state-invited" : undefined}>
              <div>
                <strong>{r.employee_name}</strong> <span className="muted small">{r.employee_no}</span>{" "}
                <span className={`chip chip-correction-${r.state}`}>{r.state_name}</span>
                <br />
                <span className="small">
                  {r.subject_name}. Wrong: {r.wrong} · Should say: {r.should_be}
                </span>
                <br />
                <span className={r.overdue ? "small overdue" : "muted small"}>
                  Asked {dmyTime(r.created_at)}
                  {r.state === "open"
                    ? ` · answer due by ${dmy(r.due_by)}${r.overdue ? " (overdue)" : ""}`
                    : ` · answered by ${r.decided_by_name ?? "Human Resources"}${r.decision_note ? `: ${r.decision_note}` : ""}`}
                </span>
              </div>
              {r.state === "open" && r.is_mine && (
                <p className="muted small">This is about you, so someone else in Human Resources answers it.</p>
              )}
              {r.state === "open" && !r.is_mine && (
                <div className="actions">
                  <a
                    href={`#/people/${r.employee}`}
                    onClick={(e) => {
                      e.preventDefault();
                      onNavigate(`/people/${r.employee}`);
                    }}
                  >
                    Open the record
                  </a>
                  <label className="grow">
                    <span className="sr-only">Answer to {r.employee_name}</span>
                    <input
                      placeholder="Answer (needed when not changed)"
                      value={notes[r.id] ?? ""}
                      onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
                      maxLength={1000}
                    />
                  </label>
                  <button disabled={busy !== null} onClick={() => decide(r, "corrected")}>
                    Corrected
                  </button>
                  <button
                    className="secondary"
                    disabled={busy !== null || !(notes[r.id] ?? "").trim()}
                    onClick={() => decide(r, "declined")}
                  >
                    Not changed
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
