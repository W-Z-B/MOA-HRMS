import { useCallback, useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import type { Paginated } from "../../api/types";

export interface FieldSpec {
  name: string;
  label: string;
  type?: "text" | "date" | "number" | "tel" | "select";
  options?: { value: string; label: string }[];
  required?: boolean;
}

interface Props<T> {
  title: string;
  /** Collection URL under /api/v1, for example "/qualifications/". */
  endpoint: string;
  employeeId: number;
  fields: FieldSpec[];
  describe: (row: T) => ReactNode;
  /** A short name for one row, read out with the remove button: "Remove BSc Agriculture". */
  nameOf: (row: T) => string;
  canEdit: boolean;
  emptyText: string;
  addLabel: string;
}

/**
 * A part of the employee file that is a list of records: shown, added to and removed from in place.
 * Used for qualifications, previous employment, dependants and emergency contacts.
 */
export function RecordList<T extends { id: number }>(props: Props<T>) {
  const { title, endpoint, employeeId, fields, describe, nameOf, canEdit, emptyText, addLabel } = props;
  const headingId = useId();
  const [rows, setRows] = useState<T[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get<Paginated<T>>(`${endpoint}?employee=${employeeId}`)
      .then((page) => setRows(page.results))
      .catch((err) => setError(errorMessage(err, `Could not load ${title.toLowerCase()}.`)));
  }, [endpoint, employeeId, title]);

  useEffect(load, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { employee: employeeId };
    for (const field of fields) {
      const value = (values[field.name] ?? "").trim();
      if (value) body[field.name] = field.type === "number" ? Number(value) : value;
    }
    try {
      await post(endpoint, body);
      setValues({});
      setAdding(false);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not save it."));
    } finally {
      setBusy(false);
    }
  }

  async function removeRow(row: T) {
    setBusy(true);
    setError(null);
    try {
      await remove(`${endpoint}${row.id}/`);
      setConfirming(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not remove it."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="records" aria-labelledby={headingId}>
      <h3 id={headingId}>{title}</h3>
      {rows === null && !error && <p className="loading">Loading…</p>}
      {rows !== null && rows.length === 0 && <p className="muted">{emptyText}</p>}
      {rows !== null && rows.length > 0 && (
        <ul className="plain">
          {rows.map((row) => (
            <li key={row.id}>
              <div>{describe(row)}</div>
              {canEdit &&
                (confirming === row.id ? (
                  <span className="actions">
                    <button className="secondary" disabled={busy} onClick={() => removeRow(row)}>
                      Confirm removal
                    </button>
                    <button className="link" onClick={() => setConfirming(null)}>
                      Keep it
                    </button>
                  </span>
                ) : (
                  <button className="link" aria-label={`Remove ${nameOf(row)}`} onClick={() => setConfirming(row.id)}>
                    Remove
                  </button>
                ))}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {canEdit && !adding && (
        <button className="secondary" onClick={() => setAdding(true)}>
          {addLabel}
        </button>
      )}
      {canEdit && adding && (
        <form className="stack sub-form" onSubmit={add} aria-label={addLabel}>
          <div className="grid2">
            {fields.map((field) => {
              const id = `${headingId}-${field.name}`;
              const value = values[field.name] ?? "";
              const change = (next: string) => setValues({ ...values, [field.name]: next });
              return (
                <label key={field.name} htmlFor={id}>
                  {field.label}
                  {!field.required && <span className="muted small"> (optional)</span>}
                  {field.type === "select" ? (
                    <select id={id} value={value} onChange={(e) => change(e.target.value)} required={field.required}>
                      <option value="">Choose</option>
                      {field.options?.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id={id}
                      type={field.type ?? "text"}
                      inputMode={field.type === "tel" || field.type === "number" ? "numeric" : undefined}
                      value={value}
                      onChange={(e) => change(e.target.value)}
                      required={field.required}
                    />
                  )}
                </label>
              );
            })}
          </div>
          <div className="actions">
            <button type="button" className="secondary" disabled={busy} onClick={() => setAdding(false)}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Save
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
