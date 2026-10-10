import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import type { Employee, Interview } from "../../api/types";

interface Props {
  applicationId: number;
  onScheduled: (interview: Interview) => void;
  onCancel: () => void;
}

/** One interviewer, one time: no double-booking is the server's own exclusion constraint
 * (recruitment.Interview), so this form only has to show the refusal in words when it fires. */
export function ScheduleInterviewForm({ applicationId, onScheduled, onCancel }: Props) {
  const [interviewers, setInterviewers] = useState<Employee[]>([]);
  const [interviewer, setInterviewer] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAll<Employee>("/employees/")
      .then(setInterviewers)
      .catch(() => setInterviewers([]));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!interviewer || !startsAt) return;
    setBusy(true);
    setError(null);
    try {
      const interview = await post<Interview>("/recruitment/interviews/", {
        application: applicationId,
        interviewer: Number(interviewer),
        starts_at: new Date(startsAt).toISOString(),
        location,
      });
      onScheduled(interview);
    } catch (err) {
      setError(errorMessage(err, "The interview could not be scheduled."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={submit} aria-label="Schedule interview">
      <h4>Schedule the interview</h4>
      <label>
        Interviewer
        <select value={interviewer} onChange={(e) => setInterviewer(e.target.value)} required>
          <option value="">Choose who will interview…</option>
          {interviewers.map((person) => (
            <option key={person.id} value={person.id}>
              {person.employee_no} {person.full_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Starts at
        <input type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} required />
      </label>
      <label>
        Location (a room, or a link GSA supplies)
        <input value={location} onChange={(e) => setLocation(e.target.value)} maxLength={255} />
      </label>
      <p className="muted small">Ends 45 minutes after it starts unless the server is told otherwise.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          Schedule
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
