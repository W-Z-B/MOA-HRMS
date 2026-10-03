import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { Me, ReportResult, ReportRow, ReportSummary } from "../../api/types";
import { dmy, localToday } from "../../app/format";

interface Props {
  me?: Me;
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
  frozen: "Frozen",
  permanent: "Permanent",
  temporary: "Temporary",
  contract: "Contract",
  other: "Other",
  active: "Active",
  total: "On the staff list",
  username: "Username",
  role: "Role",
  where: "Where",
  given: "Given on",
  given_by: "Given by",
  last_signed_in: "Last signed in",
  authenticator: "Authenticator",
  to_check: "To check",
};
const heading = (key: string) => HEADINGS[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Reports drawn as bars as well as a table (item 2.30): which parts make up each bar, and in which colour. */
const CHARTS: Record<string, { label: string; parts: { key: string; name: string; tone: string }[]; total?: string }> = {
  "headcount-by-campus": {
    label: "campus",
    parts: [
      { key: "permanent", name: "Permanent", tone: "tone-1" },
      { key: "temporary", name: "Temporary", tone: "tone-2" },
      { key: "contract", name: "Contract", tone: "tone-3" },
      { key: "other", name: "Other", tone: "tone-4" },
    ],
  },
  "establishment-vs-actual": {
    label: "unit",
    parts: [
      { key: "filled", name: "Filled", tone: "tone-1" },
      { key: "vacant", name: "Vacant", tone: "tone-3" },
      { key: "frozen", name: "Frozen", tone: "tone-4" },
    ],
  },
};

const n = (value: string | number | undefined) => Number(value ?? 0);

/** One line that sums a report up. */
function headline(key: string, rows: ReportRow[], scope: string): string {
  const sum = (field: string) => rows.reduce((total, row) => total + n(row[field]), 0);
  if (key === "headcount-by-campus") return `${sum("active")} active staff on ${scope}`;
  if (key === "establishment-vs-actual")
    return `${sum("filled")} of ${sum("approved")} approved posts filled · ${sum("vacant")} vacant · ${sum("frozen")} frozen`;
  return rows.length === 1 ? "1 row" : `${rows.length} rows`;
}

function Bars({ chart, rows }: { chart: (typeof CHARTS)[string]; rows: ReportRow[] }) {
  const size = (row: ReportRow) => chart.parts.reduce((total, part) => total + n(row[part.key]), 0);
  const largest = Math.max(...rows.map(size), 1);
  return (
    <div className="chart" aria-hidden="true">
      <ul className="legend">
        {chart.parts.map((part) => (
          <li key={part.key}>
            <span className={`swatch ${part.tone}`} />
            {part.name}
          </li>
        ))}
      </ul>
      {rows.map((row, at) => (
        <div className="chart-row" key={at}>
          <div className="spread">
            <span className="strong">{row[chart.label]}</span>
            <span className="muted num">
              {chart.label === "unit" ? `${n(row.filled)} of ${n(row.approved)} filled` : `${n(row.active)} staff`}
            </span>
          </div>
          <div className="stack-bar">
            {chart.parts.map((part) =>
              n(row[part.key]) > 0 ? (
                <span key={part.key} className={part.tone} style={{ width: `${(n(row[part.key]) / largest) * 100}%` }} />
              ) : null,
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Reports this person's roles may run, on live data, narrowed by the campus switch (item 2.30): each report a
 * card to choose; headcount and the establishment drawn as bars beside their table. The table holds every
 * figure, so the bars add nothing a screen reader would miss.
 */
export function ReportsScreen({ me, campusId, onNavigate }: Props) {
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  // The last answer, tagged with the report and campus it is for; a newer choice makes it stale.
  const [answer, setAnswer] = useState<{ key: string; result?: ReportResult; error?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = reports?.find((r) => r.key === chosen) ?? reports?.[0] ?? null;
  const runKey = selected ? `${selected.key}|${campusId ?? ""}` : "";
  const campus = me?.campuses?.find((c) => c.id === campusId);
  const scope = campus ? campus.name : "all campuses you work with";

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
  const chart = selected ? CHARTS[selected.key] : undefined;

  const columns = result && result.rows.length > 0 ? Object.keys(result.rows[0]).filter((k) => k !== "employee_id") : [];
  const totals =
    chart && result && result.rows.length > 1
      ? Object.fromEntries(columns.map((k) => [k, typeof result.rows[0][k] === "number" ? result.rows.reduce((t, r) => t + n(r[k]), 0) : ""]))
      : null;

  const cell = (row: ReportRow, key: string) => {
    const value = row[key];
    if (key === "employee_no" && row.employee_id)
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
      <div className="page-head">
        <div className="stacked">
          <h1>Reports</h1>
          <p className="muted lead">
            Figures as at {dmy(localToday())} for {scope}.
          </p>
        </div>
      </div>
      {(error || runError) && (
        <p role="alert" className="error">
          {error ?? runError}
        </p>
      )}
      {reports === null && !error && <p className="loading">Loading…</p>}
      {reports !== null && reports.length === 0 && <p className="muted">No reports are open to your role.</p>}
      {reports !== null && reports.length > 0 && (
        <div className="report-cards" role="radiogroup" aria-label="Report">
          {reports.map((r) => (
            <button
              key={r.key}
              role="radio"
              aria-checked={selected?.key === r.key}
              className={selected?.key === r.key ? "report-card active" : "report-card"}
              onClick={() => setChosen(r.key)}
            >
              <span className="report-title">{r.name}</span>
              {r.description && <span className="report-desc">{r.description}</span>}
            </button>
          ))}
        </div>
      )}
      {selected && busy && <p className="loading">Running {selected.name.toLowerCase()}…</p>}
      {selected && result && !busy && (
        <section className="panel-card padded report" aria-labelledby="report-heading">
          <div className="stacked">
            <h2 id="report-heading">{result.name}</h2>
            <p className="muted" aria-live="polite">
              {headline(selected.key, result.rows, scope)}
            </p>
          </div>
          {result.rows.length === 0 ? (
            <p className="muted">Nothing to show.</p>
          ) : (
            <>
              {chart && <Bars chart={chart} rows={result.rows} />}
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
                  {totals && (
                    <tr className="total">
                      {columns.map((key, at) => (
                        <td key={key} data-label={heading(key)} className="num">
                          {at === 0 ? "Total" : totals[key]}
                        </td>
                      ))}
                    </tr>
                  )}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}
    </>
  );
}
