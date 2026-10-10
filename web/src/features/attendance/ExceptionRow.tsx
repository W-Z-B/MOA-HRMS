import { useState } from "react";
import type { AttendanceRecord } from "../../api/types";
import { dmy, hm } from "../../app/format";
import { StatusChip } from "./AttendanceScreen";

interface Props {
  record: AttendanceRecord;
  onCorrect: (
    recordId: number,
    body: { time_in?: string; time_out?: string; note: string; clear?: boolean },
  ) => Promise<void>;
  onOpenFile: (employeeId: number) => void;
}

/** One unresolved day, with the form Human Resources or a supervisor uses to close it out (item H-M02). */
export function ExceptionRow({ record: r, onCorrect, onOpenFile }: Props) {
  const [timeIn, setTimeIn] = useState(hm(r.time_in));
  const [timeOut, setTimeOut] = useState(hm(r.time_out));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(clear: boolean) {
    if (!note.trim()) {
      setError("Say why this day is being corrected.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onCorrect(r.id, {
        time_in: timeIn || undefined,
        time_out: timeOut || undefined,
        note: note.trim(),
        clear,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card-block stack" aria-label={`${r.employee_name}, ${dmy(r.date)}`}>
      <header className="spread">
        <div className="stacked">
          <p className="who">
            <a
              href={`#/people/${r.employee}`}
              onClick={(e) => {
                e.preventDefault();
                onOpenFile(r.employee);
              }}
            >
              {r.employee_name}
            </a>
          </p>
          <h3>{dmy(r.date)}</h3>
        </div>
        <StatusChip record={r} />
      </header>
      <p className="muted small">
        Scheduled {hm(r.scheduled_in) || "—"} to {hm(r.scheduled_out) || "—"} · {r.campus_name}
      </p>
      <div className="grid2">
        <label>
          Checked in
          <input type="time" value={timeIn} onChange={(e) => setTimeIn(e.target.value)} />
        </label>
        <label>
          Checked out
          <input type="time" value={timeOut} onChange={(e) => setTimeOut(e.target.value)} />
        </label>
      </div>
      <label>
        Why this is being corrected
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} required />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button disabled={busy} onClick={() => save(false)}>
          Save
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => {
            setTimeIn("");
            setTimeOut("");
            save(true);
          }}
        >
          Clear the times, mark present
        </button>
      </div>
    </article>
  );
}
