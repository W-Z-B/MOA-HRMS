import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { Campus, Employee, EmployeeInput, Paginated } from "../../api/types";

interface Props {
  existing: Employee | null;
  defaultCampus: number | null;
  onSaved: (employee: Employee) => void;
  onCancel: () => void;
}

const EMPTY: EmployeeInput = {
  employee_no: "",
  first_name: "",
  last_name: "",
  other_names: "",
  date_of_birth: "",
  gender: "X",
  campus: 0,
  status: "active",
  email: "",
  phone: "",
  address: "",
  next_of_kin_name: "",
  next_of_kin_phone: "",
};

/** Create or edit an employee. Identifiers are only sent when typed; blank means unchanged. */
export function EmployeeForm({ existing, defaultCampus, onSaved, onCancel }: Props) {
  const [form, setForm] = useState<EmployeeInput>(() =>
    existing
      ? {
          employee_no: existing.employee_no,
          first_name: existing.first_name,
          last_name: existing.last_name,
          other_names: existing.other_names,
          date_of_birth: existing.date_of_birth,
          gender: existing.gender,
          campus: existing.campus,
          status: existing.status,
          email: existing.email,
          phone: existing.phone,
          address: existing.address,
          next_of_kin_name: existing.next_of_kin_name,
          next_of_kin_phone: existing.next_of_kin_phone,
        }
      : { ...EMPTY, campus: defaultCampus ?? 0 },
  );
  const [ids, setIds] = useState({ national_id: "", nis_no: "", tin: "" });
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<Paginated<Campus>>("/org/campuses/").then((r) => setCampuses(r.results)).catch(() => setCampuses([]));
  }, []);

  const set = <K extends keyof EmployeeInput>(key: K, value: EmployeeInput[K]) => setForm({ ...form, [key]: value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payload: EmployeeInput = { ...form };
    for (const [key, value] of Object.entries(ids)) if (value.trim()) payload[key as keyof typeof ids] = value.trim();
    try {
      const saved = existing
        ? await patch<Employee>(`/employees/${existing.id}/`, payload)
        : await post<Employee>("/employees/", payload);
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err, "Could not save the employee."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <h2>{existing ? `Edit ${existing.full_name}` : "New employee"}</h2>
      <div className="grid2">
        <label>
          Employee number
          <input id="emp-no" value={form.employee_no} onChange={(e) => set("employee_no", e.target.value)} required />
        </label>
        <label>
          Campus
          <select id="emp-campus" value={form.campus || ""} onChange={(e) => set("campus", Number(e.target.value))} required>
            <option value="">Choose</option>
            {campuses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          First name
          <input id="emp-first" value={form.first_name} onChange={(e) => set("first_name", e.target.value)} required />
        </label>
        <label>
          Last name
          <input id="emp-last" value={form.last_name} onChange={(e) => set("last_name", e.target.value)} required />
        </label>
        <label>
          Other names
          <input id="emp-other" value={form.other_names} onChange={(e) => set("other_names", e.target.value)} />
        </label>
        <label>
          Date of birth
          <input id="emp-dob" type="date" value={form.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} required />
        </label>
        <label>
          Gender
          <select id="emp-gender" value={form.gender} onChange={(e) => set("gender", e.target.value as EmployeeInput["gender"])}>
            <option value="F">Female</option>
            <option value="M">Male</option>
            <option value="X">Other or not stated</option>
          </select>
        </label>
        <label>
          Status
          <select id="emp-status" value={form.status} onChange={(e) => set("status", e.target.value as EmployeeInput["status"])}>
            <option value="active">Active</option>
            <option value="on_leave">On leave</option>
            <option value="suspended">Suspended</option>
            <option value="separated">Separated</option>
          </select>
        </label>
        <label>
          Email
          <input id="emp-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
        </label>
        <label>
          Phone
          <input id="emp-phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
        </label>
        <label className="span2">
          Address
          <input id="emp-address" value={form.address} onChange={(e) => set("address", e.target.value)} />
        </label>
        <label>
          Next of kin
          <input id="emp-nok" value={form.next_of_kin_name} onChange={(e) => set("next_of_kin_name", e.target.value)} />
        </label>
        <label>
          Next of kin phone
          <input id="emp-nok-phone" value={form.next_of_kin_phone} onChange={(e) => set("next_of_kin_phone", e.target.value)} />
        </label>
      </div>
      <fieldset>
        <legend>Identifiers (encrypted; leave blank to keep the current value)</legend>
        <div className="grid2">
          <label>
            National ID
            <input id="emp-nid" value={ids.national_id} onChange={(e) => setIds({ ...ids, national_id: e.target.value })} autoComplete="off" />
          </label>
          <label>
            NIS number
            <input id="emp-nis" value={ids.nis_no} onChange={(e) => setIds({ ...ids, nis_no: e.target.value })} autoComplete="off" />
          </label>
          <label>
            TIN
            <input id="emp-tin" value={ids.tin} onChange={(e) => setIds({ ...ids, tin: e.target.value })} autoComplete="off" />
          </label>
        </div>
      </fieldset>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button type="submit" disabled={busy}>
          {existing ? "Save changes" : "Create employee"}
        </button>
      </div>
    </form>
  );
}
