import { useState, type FormEvent } from "react";

interface Props {
  onCreate: (period: string) => Promise<void>;
}

/** Starts a new pay run, in draft, for the month chosen. */
export function NewRunForm({ onCreate }: Props) {
  const [period, setPeriod] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!period) return;
    setBusy(true);
    try {
      await onCreate(period);
      setPeriod("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card-block stack" onSubmit={submit} aria-label="Start a pay run">
      <h2>Start a pay run</h2>
      <label>
        Period
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} required />
      </label>
      <div className="actions">
        <button type="submit" disabled={busy || !period}>
          Start
        </button>
      </div>
    </form>
  );
}
