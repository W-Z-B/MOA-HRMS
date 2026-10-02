import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { errorMessage, get, getAll, post } from "../../api/client";
import { CASE_OPEN_ROLES, hasAnyRole, type CaseKind, type CaseRecord, type Employee, type Me } from "../../api/types";
import { dmy } from "../../app/format";

const STEPS: [string, string][] = [
  ["allegation", "Allegation put in writing"],
  ["response", "Response from the employee"],
  ["investigation", "Investigation"],
  ["meeting", "Meeting"],
  ["hearing", "Hearing"],
  ["note", "Note"],
];
const OUTCOMES: Record<CaseKind, [string, string][]> = {
  discipline: [
    ["no_action", "No action"],
    ["counselling", "Counselling"],
    ["verbal_warning", "Verbal warning"],
    ["written_warning", "Written warning"],
    ["final_warning", "Final written warning"],
    ["suspension", "Suspension"],
    ["dismissal", "Dismissal"],
    ["withdrawn", "Withdrawn"],
  ],
  grievance: [
    ["upheld", "Grievance upheld"],
    ["partly_upheld", "Grievance partly upheld"],
    ["not_upheld", "Grievance not upheld"],
    ["withdrawn", "Withdrawn"],
  ],
};
const APPEAL_OUTCOMES: [string, string][] = [
  ["confirmed", "Decision confirmed"],
  ["varied", "Decision varied"],
  ["overturned", "Decision overturned"],
];

/** A small form that posts to one of a case's actions and hands back the case as it now stands. */
function ActionForm({
  label,
  path,
  fields,
  onDone,
  children,
}: {
  label: string;
  path: string;
  fields: () => Record<string, unknown>;
  onDone: (fresh: CaseRecord) => void;
  children: ReactNode;
}) {
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onDone(await post<CaseRecord>(path, fields()));
    } catch (err) {
      setError(errorMessage(err, "That was not recorded."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={send} aria-label={label}>
      <h4>{label}</h4>
      {children}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">{label}</button>
      </div>
    </form>
  );
}

function CaseDetail({ initial, onChanged }: { initial: CaseRecord; onChanged: () => void }) {
  const [c, setCase] = useState(initial);
  const [staff, setStaff] = useState<Employee[]>([]);
  const [officer, setOfficer] = useState("");
  const [part, setPart] = useState("");
  const [stepKind, setStepKind] = useState("allegation");
  const [stepOn, setStepOn] = useState("");
  const [stepText, setStepText] = useState("");
  const [outcome, setOutcome] = useState(OUTCOMES[initial.kind][0][0]);
  const [reasons, setReasons] = useState("");
  const [decidedOn, setDecidedOn] = useState("");
  const [lodgedOn, setLodgedOn] = useState("");
  const [grounds, setGrounds] = useState("");
  const [appealOutcome, setAppealOutcome] = useState("confirmed");
  const [appealReasons, setAppealReasons] = useState("");
  const [heardOn, setHeardOn] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/cases/${c.id}`;

  useEffect(() => {
    getAll<Employee>("/employees/?has_account=1&status=active")
      .then(setStaff)
      .catch(() => setStaff([]));
  }, []);

  const done = (message: string) => (fresh: CaseRecord) => {
    setCase(fresh);
    setNotice(message);
    onChanged();
  };

  async function close() {
    setError(null);
    try {
      done("The case is closed.")(await post<CaseRecord>(`${base}/close/`));
    } catch (err) {
      setError(errorMessage(err, "The case was not closed."));
    }
  }

  const named = new Set(c.officers.map((o) => o.user));
  const candidates = staff.filter((e) => e.user !== null && !named.has(e.user) && e.id !== c.employee);

  return (
    <section className="card-block stack" aria-labelledby={`case-${c.id}`}>
      <h2 id={`case-${c.id}`}>
        {c.reference}: {c.employee_name}
      </h2>
      <p>
        <span className="chip">{c.kind_name}</span> <span className="chip">{c.state_name}</span>{" "}
        <span className="muted small">opened {dmy(c.opened_on)}</span>
      </p>
      <p className="case-summary">{c.summary}</p>
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {c.kind === "discipline" && (
        <p className="small" aria-label="Fair steps">
          {c.fair_steps.allegation ? "The allegation is on record in writing." : "The allegation is not yet put in writing."}{" "}
          {c.fair_steps.answered ? "The employee has been heard." : "The employee has not yet been heard."}
        </p>
      )}

      <h3>Named on the case</h3>
      <ul className="plain" aria-label="Named on the case">
        {c.officers.map((o) => (
          <li key={o.id}>
            {o.name}, {o.part.toLowerCase()}
            {o.named_by_name && o.named_by_name !== o.name ? <span className="muted small"> (named by {o.named_by_name})</span> : null}
          </li>
        ))}
      </ul>
      {c.state !== "closed" && (
        <ActionForm
          label="Name someone on the case"
          path={`${base}/officers/`}
          fields={() => ({ user: Number(officer), part })}
          onDone={(fresh) => {
            setOfficer("");
            setPart("");
            done("Named. They are told, and can now see the case.")(fresh);
          }}
        >
          <div className="grid2">
            <label>
              Who
              <select value={officer} onChange={(e) => setOfficer(e.target.value)} required>
                <option value="">Choose</option>
                {candidates.map((e) => (
                  <option key={e.id} value={e.user ?? ""}>
                    {e.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              As
              <input value={part} onChange={(e) => setPart(e.target.value)} required maxLength={80} placeholder="Chair of the hearing" />
            </label>
          </div>
        </ActionForm>
      )}

      <h3>Steps</h3>
      {c.entries.length === 0 ? (
        <p className="muted">No steps recorded yet.</p>
      ) : (
        <ol className="case-steps" aria-label="Steps">
          {c.entries.map((entry) => (
            <li key={entry.id}>
              <strong>{entry.kind_name}</strong>, {dmy(entry.on)}
              {entry.by ? <span className="muted small"> · recorded by {entry.by}</span> : null}
              <br />
              {entry.text}
            </li>
          ))}
        </ol>
      )}
      {c.state !== "closed" && (
        <ActionForm
          label="Record a step"
          path={`${base}/entries/`}
          fields={() => ({ kind: stepKind, on: stepOn, text: stepText })}
          onDone={(fresh) => {
            setStepText("");
            done("The step is recorded.")(fresh);
          }}
        >
          <div className="grid2">
            <label>
              Step
              <select value={stepKind} onChange={(e) => setStepKind(e.target.value)}>
                {STEPS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              On
              <input type="date" value={stepOn} onChange={(e) => setStepOn(e.target.value)} required />
            </label>
          </div>
          <label>
            What happened
            <textarea rows={3} value={stepText} onChange={(e) => setStepText(e.target.value)} required />
          </label>
        </ActionForm>
      )}

      <h3>Decision</h3>
      {c.decided_on ? (
        <p>
          <strong>{c.outcome_name}</strong>, {dmy(c.decided_on)}
          {c.decided_by_name ? ` by ${c.decided_by_name}` : ""}. {c.outcome_reasons}
          {c.lapses_on ? <span className="muted small"> It lapses on {dmy(c.lapses_on)}.</span> : null}
        </p>
      ) : (
        <ActionForm
          label="Record the decision"
          path={`${base}/decide/`}
          fields={() => ({ outcome, reasons, decided_on: decidedOn })}
          onDone={done("The decision is recorded.")}
        >
          <div className="grid2">
            <label>
              Outcome
              <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                {OUTCOMES[c.kind].map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Decided on
              <input type="date" value={decidedOn} onChange={(e) => setDecidedOn(e.target.value)} required />
            </label>
          </div>
          <label>
            Reasons
            <textarea rows={3} value={reasons} onChange={(e) => setReasons(e.target.value)} required />
          </label>
        </ActionForm>
      )}

      {c.appeal_lodged_on && (
        <p>
          Appeal lodged {dmy(c.appeal_lodged_on)}: {c.appeal_grounds}
          {c.appeal_decided_on ? ` Heard ${dmy(c.appeal_decided_on)} by ${c.appeal_decided_by_name}: ${c.appeal_outcome_name}. ${c.appeal_reasons}` : ""}
        </p>
      )}
      {c.state === "decided" && !c.appeal_lodged_on && (
        <ActionForm
          label="Record an appeal"
          path={`${base}/appeal/`}
          fields={() => ({ lodged_on: lodgedOn, grounds })}
          onDone={done("The appeal is recorded. Someone who did not make the decision hears it.")}
        >
          <label>
            Lodged on
            <input type="date" value={lodgedOn} onChange={(e) => setLodgedOn(e.target.value)} required />
          </label>
          <label>
            Grounds
            <textarea rows={2} value={grounds} onChange={(e) => setGrounds(e.target.value)} required />
          </label>
        </ActionForm>
      )}
      {c.state === "appeal" && (
        <ActionForm
          label="Record the appeal decision"
          path={`${base}/appeal-decision/`}
          fields={() => ({ outcome: appealOutcome, reasons: appealReasons, decided_on: heardOn })}
          onDone={done("The appeal decision is recorded.")}
        >
          <div className="grid2">
            <label>
              Outcome of the appeal
              <select value={appealOutcome} onChange={(e) => setAppealOutcome(e.target.value)}>
                {APPEAL_OUTCOMES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Heard on
              <input type="date" value={heardOn} onChange={(e) => setHeardOn(e.target.value)} required />
            </label>
          </div>
          <label>
            Reasons
            <textarea rows={2} value={appealReasons} onChange={(e) => setAppealReasons(e.target.value)} required />
          </label>
        </ActionForm>
      )}
      {c.state === "decided" && (
        <div className="actions">
          <button className="secondary" onClick={close}>
            Close the case
          </button>
        </div>
      )}
    </section>
  );
}

function OpenCase({ onOpened }: { onOpened: (opened: CaseRecord) => void }) {
  const [open, setOpen] = useState(false);
  const [staff, setStaff] = useState<Employee[]>([]);
  const [kind, setKind] = useState<CaseKind>("discipline");
  const [employee, setEmployee] = useState("");
  const [summary, setSummary] = useState("");
  const [on, setOn] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    getAll<Employee>("/employees/?status=active")
      .then(setStaff)
      .catch(() => setStaff([]));
  }, [open]);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const opened = await post<CaseRecord>("/cases/", { kind, employee: Number(employee), summary, opened_on: on });
      setOpen(false);
      setSummary("");
      onOpened(opened);
    } catch (err) {
      setError(errorMessage(err, "The case was not opened."));
    }
  }

  if (!open)
    return (
      <div className="actions">
        <button className="secondary" onClick={() => setOpen(true)}>
          Open a case
        </button>
      </div>
    );
  return (
    <form className="stack sub-form" onSubmit={send} aria-label="Open a case">
      <div className="grid2">
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value as CaseKind)}>
            <option value="discipline">Discipline</option>
            <option value="grievance">Grievance</option>
          </select>
        </label>
        <label>
          About
          <select value={employee} onChange={(e) => setEmployee(e.target.value)} required>
            <option value="">Choose</option>
            {staff.map((e) => (
              <option key={e.id} value={e.id}>
                {e.full_name} ({e.employee_no})
              </option>
            ))}
          </select>
        </label>
        <label>
          Opened on
          <input type="date" value={on} onChange={(e) => setOn(e.target.value)} required />
        </label>
      </div>
      <label>
        {kind === "discipline" ? "The allegation" : "The grievance"}
        <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} required />
      </label>
      <p className="muted small">You are named on the case. Only the HR Manager and those named can see it.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Open the case</button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** The discipline and grievance register (item 1.15): only the cases this person may see. */
export function CasesScreen({ me, caseId, onNavigate }: { me: Me; caseId: number | null; onNavigate: (to: string) => void }) {
  const [cases, setCases] = useState<CaseRecord[] | null>(null);
  const [loaded, setLoaded] = useState<CaseRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getAll<CaseRecord>("/cases/")
      .then(setCases)
      .catch((err) => setError(errorMessage(err, "Could not load the cases.")));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (caseId === null) return;
    get<CaseRecord>(`/cases/${caseId}/`)
      .then(setLoaded)
      .catch((err) => setError(errorMessage(err, "That case is not one you may see.")));
  }, [caseId]);
  const shown = caseId !== null && loaded?.id === caseId ? loaded : null;

  return (
    <>
      <h1>Cases</h1>
      <p className="muted">
        Discipline and grievance. Only the HR Manager and those named on a case can see it, and nobody a case about
        themselves.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {cases !== null && cases.length === 0 && <p className="muted">No case is open to you.</p>}
      {cases !== null && cases.length > 0 && (
        <table className="cards" aria-label="Cases">
          <thead>
            <tr>
              <th>Reference</th>
              <th>About</th>
              <th>Kind</th>
              <th>State</th>
              <th>Opened</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id}>
                <td data-label="Reference">
                  <button className="link" onClick={() => onNavigate(`/cases/${c.id}`)}>
                    {c.reference}
                  </button>
                </td>
                <td data-label="About">{c.employee_name}</td>
                <td data-label="Kind">{c.kind_name}</td>
                <td data-label="State">{c.state_name}</td>
                <td data-label="Opened">{dmy(c.opened_on)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {hasAnyRole(me, CASE_OPEN_ROLES) && (
        <OpenCase
          onOpened={(opened) => {
            load();
            onNavigate(`/cases/${opened.id}`);
          }}
        />
      )}
      {shown && <CaseDetail key={shown.id} initial={shown} onChanged={load} />}
    </>
  );
}
