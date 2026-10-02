import { useEffect, useState } from "react";
import { errorMessage, getAll } from "../../api/client";
import type { Letter } from "../../api/types";
import { dmy } from "../../app/format";

/** The register of letters issued, newest first, found by reference, name or employee number (item 1.19). */
export function IssuedTab() {
  const [letters, setLetters] = useState<Letter[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = query.trim();
    const timer = setTimeout(
      () => {
        getAll<Letter>(`/letters/${q ? `?q=${encodeURIComponent(q)}` : ""}`)
          .then((rows) => {
            setLetters(rows);
            setError(null);
          })
          .catch((err) => setError(errorMessage(err, "Could not load the letters.")));
      },
      q ? 250 : 0,
    );
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <section aria-labelledby="issued-heading">
      <h2 id="issued-heading" className="sr-only">
        Letters issued
      </h2>
      <div className="filters">
        <label className="grow">
          <span className="sr-only">Find a letter</span>
          <input
            type="search"
            placeholder="Reference, name or employee number"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {letters === null && !error && <p className="loading">Loading…</p>}
      {letters !== null && letters.length === 0 && (
        <p className="muted">{query.trim() ? "No letter matches." : "No letters have been issued yet."}</p>
      )}
      {letters !== null && letters.length > 0 && (
        <table className="cards" aria-label="Letters issued">
          <thead>
            <tr>
              <th>Reference</th>
              <th>Letter</th>
              <th>To</th>
              <th>Issued</th>
            </tr>
          </thead>
          <tbody>
            {letters.map((l) => (
              <tr key={l.id}>
                <td data-label="Reference">
                  <a href={l.download_url}>{l.reference}</a>
                </td>
                <td data-label="Letter">
                  {l.template_name} <span className="muted small">version {l.template_version}</span>
                </td>
                <td data-label="To">
                  {l.employee_name} <span className="muted small">{l.employee_no}</span>
                </td>
                <td data-label="Issued">
                  {dmy(l.issued_on)}
                  {l.issued_by ? <span className="muted small"> by {l.issued_by}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
