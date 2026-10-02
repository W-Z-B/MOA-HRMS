import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post, remove } from "../../api/client";
import type { Assignment, Contract, Employee, Entitlement, LeaveType, Paginated } from "../../api/types";
import { dmy, gyd, inDays } from "../../app/format";

interface Props {
  employee: Employee;
  isHr: boolean;
}

const TYPE_LABEL: Record<Contract["contract_type"], string> = {
  fixed_term: "Fixed term",
  open_ended: "Open ended",
  sessional: "Sessional",
};

/** Contract of the current appointment: hours, rate, notice and the leave written into it. */
export function ContractTab({ employee, isHr }: Props) {
  const [contract, setContract] = useState<Contract | null>(null);
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [entitlements, setEntitlements] = useState<Entitlement[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([
      get<Paginated<Assignment>>(`/assignments/?employee=${employee.id}`),
      get<Paginated<Contract>>(`/contracts/?employee=${employee.id}`),
      get<Paginated<LeaveType>>("/leave/types/"),
    ])
      .then(async ([assignments, contracts, leaveTypes]) => {
        const current = assignments.results.find((a) => a.status === "active" && !a.is_acting) ?? null;
        const own = contracts.results.find((c) => c.assignment === current?.id) ?? null;
        setAssignment(current);
        setContract(own);
        setTypes(leaveTypes.results.filter((t) => t.over_balance !== "allow"));
        // Entitlements are HR's to read; other readers see the terms without them.
        const rows = own && isHr ? await get<Paginated<Entitlement>>(`/leave/entitlements/?contract=${own.id}`) : null;
        setEntitlements(rows?.results ?? []);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the contract.")))
      .finally(() => setLoaded(true));
  }, [employee.id, isHr]);

  useEffect(load, [load]);

  if (!loaded) return <p className="muted">Loading…</p>;
  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!assignment) return <p className="muted">No current appointment, so there is no contract to show.</p>;

  return (
    <>
      {contract ? (
        <dl>
          <dt>Contract</dt>
          <dd>
            {TYPE_LABEL[contract.contract_type]}
            {contract.term_months ? `, ${contract.term_months} months` : ""}
          </dd>
          <dt>Signed</dt>
          <dd>{dmy(contract.signed_on) || "not recorded"}</dd>
          <dt>Hours a week</dt>
          <dd>{contract.hours_per_week ? parseFloat(contract.hours_per_week) : "not recorded"}</dd>
          <dt>Hourly rate</dt>
          <dd>
            {contract.hourly_rate_effective
              ? `${gyd(contract.hourly_rate_effective)}${contract.hourly_rate ? "" : " (from the grade and hours)"}`
              : isHr
                ? "not recorded"
                : "shown to HR and Finance"}
          </dd>
          <dt>Notice</dt>
          <dd>{contract.notice_period_days ? inDays(contract.notice_period_days) : "not recorded"}</dd>
          <dt>Other terms</dt>
          <dd>{contract.other_terms || "none"}</dd>
          {isHr && (
            <>
              <dt>Leave each year</dt>
              <dd>
                {types.map((t) => {
                  const own = entitlements.find((e) => e.leave_type === t.id);
                  return (
                    <span key={t.id} className="line">
                      {t.name}: {own ? `${inDays(own.annual_days)} (this contract)` : "the standard"}
                    </span>
                  );
                })}
              </dd>
            </>
          )}
        </dl>
      ) : (
        <p className="muted">No contract is on file for {assignment.position_title}.</p>
      )}
      {isHr && (
        <ContractForm
          key={contract?.id ?? "new"}
          assignment={assignment}
          contract={contract}
          entitlements={entitlements}
          types={types}
          onSaved={load}
        />
      )}
    </>
  );
}

interface FormProps {
  assignment: Assignment;
  contract: Contract | null;
  entitlements: Entitlement[];
  types: LeaveType[];
  onSaved: () => void;
}

function ContractForm({ assignment, contract, entitlements, types, onSaved }: FormProps) {
  const [kind, setKind] = useState<string>(contract?.contract_type ?? "open_ended");
  const [months, setMonths] = useState(contract?.term_months ? String(contract.term_months) : "");
  const [signed, setSigned] = useState(contract?.signed_on ?? "");
  const [hours, setHours] = useState(contract?.hours_per_week ? String(parseFloat(contract.hours_per_week)) : "");
  const [rate, setRate] = useState(contract?.hourly_rate ?? "");
  const [notice, setNotice] = useState(contract?.notice_period_days ? String(contract.notice_period_days) : "");
  const [other, setOther] = useState(contract?.other_terms ?? "");
  const [days, setDays] = useState<Record<number, string>>(() =>
    Object.fromEntries(entitlements.map((e) => [e.leave_type, String(parseFloat(e.annual_days))])),
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const terms = {
      assignment: assignment.id,
      contract_type: kind,
      term_months: months ? Number(months) : null,
      signed_on: signed || null,
      hours_per_week: hours || null,
      hourly_rate: rate || null,
      notice_period_days: notice ? Number(notice) : null,
      other_terms: other,
    };
    try {
      const saved = contract
        ? await patch<Contract>(`/contracts/${contract.id}/`, terms)
        : await post<Contract>("/contracts/", terms);
      // An empty box means the standard entitlement: the contract then carries no figure of its own.
      for (const type of types) {
        const existing = entitlements.find((row) => row.leave_type === type.id);
        const wanted = (days[type.id] ?? "").trim();
        if (existing && !wanted) await remove(`/leave/entitlements/${existing.id}/`);
        else if (existing && wanted !== String(parseFloat(existing.annual_days)))
          await patch(`/leave/entitlements/${existing.id}/`, { annual_days: wanted });
        else if (!existing && wanted)
          await post("/leave/entitlements/", { contract: saved.id, leave_type: type.id, annual_days: wanted });
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save the contract."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={submit}>
      <h3>{contract ? "Change the terms" : "Record the contract"}</h3>
      <div className="grid2">
        <label>
          Contract type
          <select id="con-type" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="open_ended">Open ended</option>
            <option value="fixed_term">Fixed term</option>
            <option value="sessional">Sessional</option>
          </select>
        </label>
        <label>
          Term in months
          <input id="con-months" type="number" min="1" max="120" value={months} onChange={(e) => setMonths(e.target.value)} />
        </label>
        <label>
          Signed on
          <input id="con-signed" type="date" value={signed} onChange={(e) => setSigned(e.target.value)} />
        </label>
        <label>
          Hours a week
          <input id="con-hours" type="number" min="1" max="84" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
        </label>
        <label>
          Hourly rate (G$)
          <input
            id="con-rate"
            type="number"
            min="0"
            step="0.01"
            value={rate}
            placeholder="From the grade"
            onChange={(e) => setRate(e.target.value)}
          />
        </label>
        <label>
          Notice in days
          <input id="con-notice" type="number" min="0" max="365" value={notice} onChange={(e) => setNotice(e.target.value)} />
        </label>
        {types.map((t) => (
          <label key={t.id}>
            {t.name}, days a year
            <input
              id={`con-days-${t.code}`}
              type="number"
              min="0"
              max="365"
              step="0.5"
              value={days[t.id] ?? ""}
              placeholder="The standard"
              onChange={(e) => setDays({ ...days, [t.id]: e.target.value })}
            />
          </label>
        ))}
        <label className="span2">
          Other terms
          <input id="con-other" value={other} onChange={(e) => setOther(e.target.value)} />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          Save contract
        </button>
      </div>
    </form>
  );
}
