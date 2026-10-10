import { useState, type FormEvent } from "react";
import { errorMessage } from "../../api/client";

interface Props {
  onCreate: (fields: { name: string; year: number; starts: string; ends: string; is_open: boolean }) => Promise<void>;
}

/** Opens a review cycle (item H-M03): annual by default, since nothing on a contract or appointment
 * suggests any other rhythm. */
export function NewCycleForm({ onCreate }: Props) {
  const year = new Date().getFullYear();
  const [name, setName] = useState("Annual appraisal");
  const [cycleYear, setCycleYear] = useState(year);
  const [starts, setStarts] = useState(`${year}-01-01`);
  const [ends, setEnds] = useState(`${year}-12-31`);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onCreate({ name, year: cycleYear, starts, ends, is_open: true });
    } catch (err) {
      setError(errorMessage(err, "Could not open that cycle."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={submit} aria-label="Open a cycle">
      <h3>Open a cycle</h3>
      <div className="grid2">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Year
          <input type="number" value={cycleYear} onChange={(e) => setCycleYear(Number(e.target.value))} required />
        </label>
      </div>
      <div className="grid2">
        <label>
          Starts
          <input type="date" value={starts} onChange={(e) => setStarts(e.target.value)} required />
        </label>
        <label>
          Ends
          <input type="date" value={ends} onChange={(e) => setEnds(e.target.value)} required />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          Open cycle
        </button>
      </div>
    </form>
  );
}
