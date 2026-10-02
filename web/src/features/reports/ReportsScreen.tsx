import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { ReportResult, ReportRow, ReportSummary } from "../../api/types";

interface Props {
  campusId: number | null;
  onNavigate: (to: string) => void;
}

const HEADINGS: Record<string, string> = {
  employee_no: "No.",
  name: "Name",
  campus: "Campus",
  unit: "Unit",
  field: "What",
  problem: "To check",
  approved: "Approved posts",
  filled: "Filled",
  vacant: "Vacant",
  active: "Active",
  total: "Total",
};
const heading = (key: string) => HEADINGS[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Reports this person's roles may run, on live data. The campus switch in the top bar limits them. */
export function ReportsScreen({ campusId, onNavigate }: Props) {
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [selected, setSelected] = useState<ReportSummary | null>(null);
  // The last answer, tagged with the report and campus it is for; a newer choice makes it stale.
  const [answer, setAnswer] = useState<{ key: string; result?: ReportResult; error?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const runKey = selected ? `${selected.key}|${campusId ?? ""}` : "";

  useEffect(() => {
    get<ReportSummary[]>("/reports/")
      .then(setReports)
      .catch((err) => setError(errorMessage(err, "Could not load the reports.")));
  }, []);

  useEffect(() => {
    if (!selected) return;
    let current = true;
    const query = campusId ? `?campus=${campusId}` : "";
    get<ReportResult>(`/reports/${selected.key}/${query}`)
      .then((r) => current && setAnswer({ key: runKey, result: r }))
      .catch((err) => current && setAnswer({ key: runKey, error: errorMessage(err, "Could not run the report.") }));
    return () => {
      current = false;
    };
  }, [selected, campusId, runKey]);

  const fresh = answer && answer.key === runKey ? answer : null;
  const busy = selected !== null && fresh === null;
  const result = fresh?.result ?? null;
  const runError = fresh?.error ?? null;

  const columns = result && result.rows.length > 0 ? Object.keys(result.rows[0]).filter((k) => k !== "employee_id") : [];

  const cell = (row: ReportRow, key: string) => {
    const value = row[key];
    if (key === "employee_no" && row.employee_id !== undefined)
      return (
        <a
          href={`#/people/${row.employee_id}`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(`/people/${row.employee_id}`);
          }}
        >
          {value}
        </a>
      );
    return value;
  };

  return (
    <>
      <h1>Reports</h1>
      {(error || runError) && (
        <p role="alert" className="error">
          {error ?? runError}
        </p>
      )}
      {reports === null && !error && <p className="loading">Loading…</p>}
      {reports !== null && reports.length === 0 && <p className="muted">No reports are open to your role.</p>}
      {reports !== null && reports.length > 0 && (
        <ul className="plain report-list" aria-label="Reports">
          {reports.map((r) => (
            <li key={r.key}>
              <button
                className={selected?.key === r.key ? "report active" : "report"}
                aria-pressed={selected?.key === r.key}
                onClick={() => setSelected(r)}
              >
                {r.name}
              </button>
              {r.description && <span className="muted small">{r.description}</span>}
            </li>
          ))}
        </ul>
      )}
      {selected && busy && <p className="loading">Running {selected.name.toLowerCase()}…</p>}
      {selected && result && !busy && (
        <section aria-labelledby="report-heading">
          <h2 id="report-heading">{result.name}</h2>
          <p className="muted small" aria-live="polite">
            {result.rows.length === 1 ? "1 row" : `${result.rows.length} rows`}
            {campusId ? ", this campus only" : ", all campuses you work with"}
          </p>
          {result.rows.length === 0 ? (
            <p className="muted">Nothing to show.</p>
          ) : (
            <table className="cards">
              <thead>
                <tr>
                  {columns.map((key) => (
                    <th key={key} scope="col">
                      {heading(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, index) => (
                  <tr key={index}>
                    {columns.map((key) => (
                      <td key={key} data-label={heading(key)} className={typeof row[key] === "number" ? "num" : undefined}>
                        {cell(row, key)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </>
  );
}
