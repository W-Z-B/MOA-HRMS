import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll } from "../../api/client";
import type { Hire } from "../../api/types";
import { localToday } from "../../app/format";

interface Props {
  onCreate: (fields: {
    hire: number;
    employee_no: string;
    date_of_birth: string;
    gender: string;
    appointment_type: string;
    start_date?: string;
  }) => Promise<void>;
}

/** Starts onboarding from an accepted hire that has no staff record yet (``Hire.employee`` still empty). */
export function StartOnboardingForm({ onCreate }: Props) {
  const [hires, setHires] = useState<Hire[]>([]);
  const [hireId, setHireId] = useState<number | "">("");
  const [employeeNo, setEmployeeNo] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [gender, setGender] = useState("X");
  const [appointmentType, setAppointmentType] = useState("permanent");
  const [startDate, setStartDate] = useState(localToday());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAll<Hire>("/recruitment/hires/")
      .then((rows) => setHires(rows.filter((h) => h.employee === null)))
      .catch(() => setHires([]));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!hireId) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate({
        hire: hireId,
        employee_no: employeeNo,
        date_of_birth: dateOfBirth,
        gender,
        appointment_type: appointmentType,
        start_date: startDate || undefined,
      });
      setHireId("");
      setEmployeeNo("");
      setDateOfBirth("");
      setHires((rows) => rows.filter((h) => h.id !== hireId));
    } catch (err) {
      setError(errorMessage(err, "Could not start onboarding."));
    } finally {
      setBusy(false);
    }
  }

  if (hires.length === 0) {
    return <p className="panel-card padded">No accepted hire is waiting to be onboarded.</p>;
  }

  return (
    <form className="stack sub-form" onSubmit={submit} aria-label="Start onboarding">
      <h3>Start onboarding</h3>
      <label>
        Accepted hire
        <select value={hireId} onChange={(e) => setHireId(e.target.value ? Number(e.target.value) : "")} required>
          <option value="">Choose…</option>
          {hires.map((hire) => (
            <option key={hire.id} value={hire.id}>
              {hire.candidate_name} — {hire.vacancy_title}
            </option>
          ))}
        </select>
      </label>
      <div className="grid2">
        <label>
          Employee number
          <input value={employeeNo} onChange={(e) => setEmployeeNo(e.target.value)} required />
        </label>
        <label>
          Date of birth
          <input type="date" value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} required />
        </label>
      </div>
      <div className="grid2">
        <label>
          Gender
          <select value={gender} onChange={(e) => setGender(e.target.value)}>
            <option value="F">Female</option>
            <option value="M">Male</option>
            <option value="X">Other or not stated</option>
          </select>
        </label>
        <label>
          Appointment type
          <select value={appointmentType} onChange={(e) => setAppointmentType(e.target.value)}>
            <option value="permanent">Permanent</option>
            <option value="contract">Contract</option>
            <option value="temporary">Temporary</option>
            <option value="sessional">Sessional lecturer or instructor</option>
            <option value="seasonal">Seasonal farm or estate worker</option>
          </select>
        </label>
      </div>
      <label>
        Start date
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          Start onboarding
        </button>
      </div>
    </form>
  );
}
