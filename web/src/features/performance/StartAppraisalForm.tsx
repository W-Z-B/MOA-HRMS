import { useState, type FormEvent } from "react";
import { errorMessage, get } from "../../api/client";
import type { AppraisalCycle, Employee, Paginated } from "../../api/types";

interface Props {
  cycles: AppraisalCycle[];
  onCreate: (fields: { employee: number; cycle: number; kind: string }) => Promise<void>;
}

/** Opens an appraisal for one employee within one cycle: the manager is fixed the moment this runs
 * (performance.services.manager_of, at the server). */
export function StartAppraisalForm({ cycles, onCreate }: Props) {
  const [search, setSearch] = useState("");
  const [matches, setMatches] = useState<Employee[]>([]);
  const [employeeId, setEmployeeId] = useState<number | "">("");
  const [cycleId, setCycleId] = useState<number | "">(cycles[0]?.id ?? "");
  const [kind, setKind] = useState("annual");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function find(e: FormEvent) {
    e.preventDefault();
    if (!search.trim()) return;
    try {
      const page = await get<Paginated<Employee>>(`/employees/?q=${encodeURIComponent(search)}`);
      setMatches(page.results);
    } catch {
      setMatches([]);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!employeeId || !cycleId) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate({ employee: employeeId, cycle: cycleId, kind });
      setMatches([]);
      setSearch("");
      setEmployeeId("");
    } catch (err) {
      setError(errorMessage(err, "Could not open that appraisal."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={submit} aria-label="Open an appraisal">
      <h3>Open an appraisal</h3>
      <div className="actions">
        <label className="grow">
          Find the employee
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or employee number" />
        </label>
        <button type="button" onClick={find} disabled={!search.trim()}>
          Search
        </button>
      </div>
      {matches.length > 0 && (
        <label>
          Employee
          <select value={employeeId} onChange={(e) => setEmployeeId(Number(e.target.value))} required>
            <option value="">Choose…</option>
            {matches.map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name} ({m.employee_no})
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="grid2">
        <label>
          Cycle
          <select value={cycleId} onChange={(e) => setCycleId(Number(e.target.value))} required>
            <option value="">Choose…</option>
            {cycles.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} {c.year}
              </option>
            ))}
          </select>
        </label>
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="annual">Annual appraisal</option>
            <option value="probation">Probation review</option>
          </select>
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy || !employeeId || !cycleId}>
          Open appraisal
        </button>
      </div>
    </form>
  );
}
