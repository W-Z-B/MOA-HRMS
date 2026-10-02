import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, plainMessage, post } from "../../api/client";
import { SETUP_WRITE_ROLES, hasAnyRole, type LeaveTypeRules, type Me, type Paginated } from "../../api/types";

const BEYOND: Record<LeaveTypeRules["over_balance"], string> = {
  allow: "Allowed at discretion",
  refuse: "Refused",
  evidence: "Only with evidence",
};
const APPOINTMENTS: [string, string][] = [
  ["permanent", "Permanent"],
  ["contract", "Contract"],
  ["temporary", "Temporary"],
  ["sessional", "Sessional"],
  ["seasonal", "Seasonal"],
];
type Draft = Omit<LeaveTypeRules, "id">;
const BLANK: Draft = {
  code: "",
  name: "",
  annual_entitlement_days: "0",
  accrues_monthly: false,
  carry_over_max_days: "0",
  max_balance_days: null,
  is_paid: true,
  requires_evidence: false,
  over_balance: "allow",
  evidence_name: "Supporting document",
  evidence_is_medical: false,
  appointment_types: [],
  term_time_restricted: false,
};
const days = (value: string | null) => (value === null ? "—" : `${parseFloat(value)} days`);

/**
 * Leave types and their rules (item 1.25): what each gives, whether it builds up month by month, what
 * carries over, and what happens beyond the balance. Rules are data: changing one needs no new release.
 */
export function LeaveTypesTab({ me }: { me: Me }) {
  const [types, setTypes] = useState<LeaveTypeRules[] | null>(null);
  const [editing, setEditing] = useState<LeaveTypeRules | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, SETUP_WRITE_ROLES);

  const load = useCallback(() => {
    get<Paginated<LeaveTypeRules>>("/leave/types/")
      .then((page) => setTypes(page.results))
      .catch((err) => setError(errorMessage(err, "Could not load the leave types.")));
  }, []);

  useEffect(load, [load]);

  function open(type: LeaveTypeRules | "new") {
    setEditing(type);
    setDraft(type === "new" ? BLANK : { ...type });
    setNotice(null);
    setError(null);
  }

  function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...draft, max_balance_days: draft.max_balance_days || null };
    const work = editing === "new" || editing === null ? post("/leave/types/", body) : patch(`/leave/types/${editing.id}/`, body);
    work
      .then(() => {
        setNotice(`${draft.name} saved. New requests follow it at once.`);
        setEditing(null);
        load();
      })
      .catch((err) => setError(plainMessage(err, "The leave type was not saved.")))
      .finally(() => setBusy(false));
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft({ ...draft, [key]: value });
  const toggleAppointment = (code: string) =>
    set(
      "appointment_types",
      draft.appointment_types.includes(code)
        ? draft.appointment_types.filter((c) => c !== code)
        : [...draft.appointment_types, code],
    );

  return (
    <section aria-labelledby="leave-types-heading">
      <h2 id="leave-types-heading" className="sr-only">
        Leave types
      </h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {types === null && !error && <p className="loading">Loading…</p>}
      {types !== null && (
        <table className="cards">
          <caption className="sr-only">Leave types and their rules</caption>
          <thead>
            <tr>
              <th scope="col">Leave</th>
              <th scope="col">A year</th>
              <th scope="col">Builds up monthly</th>
              <th scope="col">Carries over</th>
              <th scope="col">Paid</th>
              <th scope="col">Beyond the balance</th>
              <th scope="col">Evidence</th>
              <th scope="col">For</th>
              {mayWrite && <th scope="col">Change</th>}
            </tr>
          </thead>
          <tbody>
            {types.map((type) => (
              <tr key={type.id}>
                <td data-label="Leave">
                  {type.name} <span className="muted small">{type.code}</span>
                </td>
                <td data-label="A year">{days(type.annual_entitlement_days)}</td>
                <td data-label="Builds up monthly">{type.accrues_monthly ? "Yes" : "No"}</td>
                <td data-label="Carries over">{days(type.carry_over_max_days)}</td>
                <td data-label="Paid">{type.is_paid ? "Yes" : "No"}</td>
                <td data-label="Beyond the balance">{BEYOND[type.over_balance]}</td>
                <td data-label="Evidence">
                  {type.requires_evidence || type.over_balance === "evidence"
                    ? `${type.evidence_name}${type.evidence_is_medical ? " (medical)" : ""}`
                    : "—"}
                </td>
                <td data-label="For">
                  {type.appointment_types.length === 0
                    ? "Everyone"
                    : type.appointment_types.map((c) => APPOINTMENTS.find(([code]) => code === c)?.[1] ?? c).join(", ")}
                </td>
                {mayWrite && (
                  <td data-label="Change">
                    <button className="link" onClick={() => open(type)} aria-label={`Change ${type.name}`}>
                      Change
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {mayWrite && editing === null && (
        <div className="actions">
          <button className="secondary" onClick={() => open("new")}>
            Add a leave type
          </button>
        </div>
      )}
      {editing !== null && (
        <form className="card-block stack" onSubmit={save} aria-label={editing === "new" ? "New leave type" : `Change ${draft.name}`}>
          <div className="grid2">
            <label>
              Code
              <input
                value={draft.code}
                onChange={(e) => set("code", e.target.value.toUpperCase())}
                maxLength={20}
                readOnly={editing !== "new"}
                required
              />
            </label>
            <label>
              Name
              <input value={draft.name} onChange={(e) => set("name", e.target.value)} maxLength={80} required />
            </label>
            <label>
              Days a year
              <input
                type="number"
                min={0}
                step="0.5"
                value={draft.annual_entitlement_days}
                onChange={(e) => set("annual_entitlement_days", e.target.value)}
                required
              />
            </label>
            <label>
              Days carried over at most
              <input
                type="number"
                min={0}
                step="0.5"
                value={draft.carry_over_max_days}
                onChange={(e) => set("carry_over_max_days", e.target.value)}
                required
              />
            </label>
            <label>
              Beyond the balance
              <select value={draft.over_balance} onChange={(e) => set("over_balance", e.target.value as Draft["over_balance"])}>
                <option value="allow">Allowed at discretion</option>
                <option value="refuse">Refused</option>
                <option value="evidence">Only with evidence</option>
              </select>
            </label>
            <label>
              Evidence is called
              <input value={draft.evidence_name} onChange={(e) => set("evidence_name", e.target.value)} maxLength={60} />
            </label>
          </div>
          <fieldset>
            <legend>Rules</legend>
            {(
              [
                ["accrues_monthly", "Builds up a twelfth of the year each month"],
                ["is_paid", "Paid"],
                ["requires_evidence", "Evidence with every request"],
                ["evidence_is_medical", "Evidence is medical: the employee and HR only"],
                ["term_time_restricted", "Not taken during term (academic staff)"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="inline">
                <input type="checkbox" checked={draft[key]} onChange={(e) => set(key, e.target.checked)} /> {label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>For appointments (none ticked: everyone)</legend>
            {APPOINTMENTS.map(([code, label]) => (
              <label key={code} className="inline">
                <input type="checkbox" checked={draft.appointment_types.includes(code)} onChange={() => toggleAppointment(code)} />{" "}
                {label}
              </label>
            ))}
          </fieldset>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
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
