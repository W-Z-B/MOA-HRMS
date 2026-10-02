import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import { GRADE_WRITE_ROLES, hasAnyRole, type Grade, type Me, type SalaryScale } from "../../api/types";
import { dmy, gyd } from "../../app/format";
import { Messages } from "./Messages";
import { useAction } from "./useAction";

const EMPTY = { scale: "", code: "", step: "1", amount: "", effective_from: "" };

/**
 * Salary scales and their grades (item 1.25). A new amount is a new line from a date, so the history of
 * what each grade paid stays on record. Amounts show only to the roles that see pay.
 */
export function GradesTab({ me }: { me: Me }) {
  const [scales, setScales] = useState<SalaryScale[] | null>(null);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [draft, setDraft] = useState(EMPTY);
  const [newScale, setNewScale] = useState({ code: "", name: "" });
  const [loadError, setLoadError] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, GRADE_WRITE_ROLES);

  const load = useCallback(() => {
    getAll<SalaryScale>("/org/salary-scales/")
      .then(setScales)
      .catch((err) => setLoadError(errorMessage(err, "Could not load the salary scales.")));
    getAll<Grade>("/org/grades/").then(setGrades).catch(() => setGrades([]));
  }, []);
  const { busy, error, notice, run } = useAction(load);

  useEffect(load, [load]);

  function addGrade(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      await post("/org/grades/", { ...draft, scale: Number(draft.scale), step: Number(draft.step) });
      setDraft(EMPTY);
      return `Grade ${draft.code}, step ${draft.step}: ${gyd(draft.amount)} a month from ${dmy(draft.effective_from)}.`;
    });
  }

  function addScale(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      await post("/org/salary-scales/", newScale);
      setNewScale({ code: "", name: "" });
      return `Scale ${newScale.code} added.`;
    });
  }

  return (
    <section aria-labelledby="grades-heading">
      <h2 id="grades-heading" className="sr-only">
        Salary scales and grades
      </h2>
      <Messages error={loadError ?? error} notice={notice} />
      {scales === null && !loadError && <p className="loading">Loading…</p>}
      {scales?.map((scale) => {
        const rows = grades.filter((g) => g.scale === scale.id);
        return (
          <section key={scale.id} className="card-block" aria-label={`Scale ${scale.code}`}>
            <h3>
              {scale.name} <span className="muted small">{scale.code}</span>
            </h3>
            {rows.length === 0 ? (
              <p className="muted">No grades on this scale yet.</p>
            ) : (
              <table className="cards">
                <caption className="sr-only">Grades on scale {scale.code}</caption>
                <thead>
                  <tr>
                    <th scope="col">Grade</th>
                    <th scope="col">Step</th>
                    <th scope="col">A month</th>
                    <th scope="col">From</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((grade) => (
                    <tr key={grade.id}>
                      <td data-label="Grade">{grade.code}</td>
                      <td data-label="Step">{grade.step}</td>
                      <td data-label="A month" className="num">
                        {grade.amount === null ? <span className="muted">Not shown to your role</span> : gyd(grade.amount)}
                      </td>
                      <td data-label="From">{dmy(grade.effective_from)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}
      {mayWrite && scales !== null && (
        <>
          <form className="card-block stack" onSubmit={addGrade} aria-label="Add a grade or a new amount">
            <h3>Add a grade, or a new amount for one</h3>
            <p className="muted small">A new amount for a grade and step is a new line from its date; the earlier amount stays on record.</p>
            <div className="grid2">
              <label>
                Scale
                <select value={draft.scale} onChange={(e) => setDraft({ ...draft, scale: e.target.value })} required>
                  <option value="">Choose</option>
                  {scales.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.code} {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Grade
                <input value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} maxLength={20} required />
              </label>
              <label>
                Step
                <input type="number" min={1} value={draft.step} onChange={(e) => setDraft({ ...draft, step: e.target.value })} required />
              </label>
              <label>
                A month (G$)
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  inputMode="decimal"
                  value={draft.amount}
                  onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
                  required
                />
              </label>
              <label>
                From
                <input
                  type="date"
                  value={draft.effective_from}
                  onChange={(e) => setDraft({ ...draft, effective_from: e.target.value })}
                  required
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" disabled={busy}>
                Add
              </button>
            </div>
          </form>
          <form className="sub-form stack" onSubmit={addScale} aria-label="Add a salary scale">
            <h3>Add a salary scale</h3>
            <div className="grid2">
              <label>
                Code
                <input value={newScale.code} onChange={(e) => setNewScale({ ...newScale, code: e.target.value })} maxLength={20} required />
              </label>
              <label>
                Name
                <input value={newScale.name} onChange={(e) => setNewScale({ ...newScale, name: e.target.value })} maxLength={120} required />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="secondary" disabled={busy}>
                Add the scale
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}
