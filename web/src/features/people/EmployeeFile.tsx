import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import {
  HR_ROLES,
  hasAnyRole,
  type Assignment,
  type Employee,
  type EmployeeDocument,
  type LeaveBalance,
  type Me,
  type Paginated,
  type Position,
  type Reveal,
} from "../../api/types";
import { dmy, inDays } from "../../app/format";
import { WriteLetter } from "../letters/WriteLetter";
import { BackgroundTab } from "./BackgroundTab";
import { BankTab } from "./BankTab";
import { ContactsTab } from "./ContactsTab";
import { ContractTab } from "./ContractTab";
import { DocumentUpload } from "./DocumentUpload";
import { HistoryTab } from "./HistoryTab";

type FileTab =
  | "personal"
  | "assignments"
  | "contract"
  | "background"
  | "contacts"
  | "bank"
  | "documents"
  | "leave"
  | "history";

const TAB_LABEL: Record<FileTab, string> = {
  personal: "Personal",
  assignments: "Appointments",
  contract: "Contract",
  background: "Background",
  contacts: "Contacts",
  bank: "Bank",
  documents: "Documents",
  leave: "Leave",
  history: "History",
};
// Who sees which tab: the server enforces the same rules; this only hides what would be refused.
const BANK_ROLES = ["hr_officer", "hr_manager", "administrator", "finance", "auditor"];
const HISTORY_ROLES = ["hr_officer", "hr_manager", "administrator", "principal", "auditor"];
const DEPENDANT_ROLES = ["hr_officer", "hr_manager", "administrator", "finance", "auditor"];

const STATUS_LABEL: Record<Employee["status"], string> = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  separated: "Separated",
};

interface Props {
  employee: Employee;
  me: Me;
  onEdit: () => void;
}

/** Tabbed employee file: personal details (with audited reveal), appointments, contract, background,
 * contacts, bank details, documents, leave and the history of every change. */
export function EmployeeFile({ employee, me, onEdit }: Props) {
  const [tab, setTab] = useState<FileTab>("personal");
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [documents, setDocuments] = useState<EmployeeDocument[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const isHr = hasAnyRole(me, HR_ROLES);
  const tabs = (Object.keys(TAB_LABEL) as FileTab[]).filter(
    (t) => (t !== "bank" || hasAnyRole(me, BANK_ROLES)) && (t !== "history" || hasAnyRole(me, HISTORY_ROLES)),
  );

  useEffect(() => {
    const ok = <T,>(set: (v: T) => void) => (v: T) => {
      set(v);
      setError(null);
    };
    if (tab === "assignments") {
      get<Paginated<Assignment>>(`/assignments/?employee=${employee.id}`)
        .then((r) => ok(setAssignments)(r.results))
        .catch(() => setError("Could not load assignments."));
    } else if (tab === "documents") {
      get<Paginated<EmployeeDocument>>(`/documents/?employee=${employee.id}`)
        .then((r) => ok(setDocuments)(r.results))
        .catch(() => setError("Could not load documents."));
    } else if (tab === "leave") {
      get<{ balances: LeaveBalance[] }>(`/leave/ledger/balances/?employee=${employee.id}`)
        .then((r) => ok(setBalances)(r.balances))
        .catch(() => setError("Could not load balances."));
    }
  }, [tab, employee.id, version]);

  async function doReveal() {
    try {
      setReveal(await post<Reveal>(`/employees/${employee.id}/reveal/`));
    } catch (err) {
      setError(errorMessage(err, "Reveal failed."));
    }
  }

  return (
    <>
      <div className="panel-head">
        <div>
          <h2>{employee.full_name}</h2>
          <p className="muted">
            {employee.employee_no} · {employee.campus_name} · {STATUS_LABEL[employee.status]}
          </p>
        </div>
        {isHr && (
          <button className="secondary" onClick={onEdit}>
            Edit
          </button>
        )}
      </div>
      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {tab === "personal" && (
        <dl>
          <dt>Position</dt>
          <dd>{employee.position_title ?? "Unassigned"}</dd>
          <dt>Date of birth</dt>
          <dd>{dmy(employee.date_of_birth)}</dd>
          <dt>Email</dt>
          <dd>{employee.email || "not recorded"}</dd>
          <dt>Phone</dt>
          <dd>{employee.phone || "not recorded"}</dd>
          <dt>Address</dt>
          <dd>{employee.address || "not recorded"}</dd>
          <dt>National ID</dt>
          <dd>{reveal?.national_id ?? employee.national_id_masked ?? "not recorded"}</dd>
          <dt>NIS number</dt>
          <dd>{reveal?.nis_no ?? employee.nis_no_masked ?? "not recorded"}</dd>
          <dt>TIN</dt>
          <dd>{reveal?.tin ?? employee.tin_masked ?? "not recorded"}</dd>
          {isHr && !reveal && (
            <dd>
              <button className="secondary" onClick={doReveal}>
                Reveal identifiers (audited)
              </button>
            </dd>
          )}
        </dl>
      )}

      {tab === "assignments" && (
        <>
          {assignments.length === 0 ? (
            <p className="muted">No assignments.</p>
          ) : (
            <ul className="plain">
              {assignments.map((a) => (
                <li key={a.id}>
                  <strong>{a.position_title}</strong> {a.is_acting && <em>(acting)</em>}
                  <br />
                  <span className="muted small">
                    {a.appointment_type}, from {dmy(a.start_date)}
                    {a.end_date ? ` to ${dmy(a.end_date)}` : ""}
                    {a.probation_end ? `, probation ends ${dmy(a.probation_end)}` : ""} · {a.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {isHr && <AssignmentForm employee={employee} onSaved={() => setVersion((v) => v + 1)} />}
        </>
      )}

      {tab === "contract" && <ContractTab employee={employee} isHr={isHr} />}

      {tab === "background" && <BackgroundTab employeeId={employee.id} canEdit={isHr} />}

      {tab === "contacts" && (
        <ContactsTab employeeId={employee.id} canEdit={isHr} canSeeDependants={hasAnyRole(me, DEPENDANT_ROLES)} />
      )}

      {tab === "bank" && <BankTab employeeId={employee.id} me={me} />}

      {tab === "history" && <HistoryTab key={version} employeeId={employee.id} />}

      {tab === "documents" && (
        <>
          {documents.length === 0 ? (
            <p className="muted">No documents on file.</p>
          ) : (
            <ul className="plain">
              {documents.map((d) => (
                <li key={d.id}>
                  <a href={d.download_url}>{d.title}</a>{" "}
                  <span className="muted small">
                    {d.filename} · v{d.version} · {d.doc_type} · {d.classification}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {isHr && <WriteLetter employee={employee} onIssued={() => setVersion((v) => v + 1)} />}
          {isHr && <DocumentUpload employee={employee} onSaved={() => setVersion((v) => v + 1)} />}
        </>
      )}

      {tab === "leave" &&
        (balances.length === 0 ? (
          <p className="muted">No leave ledger entries.</p>
        ) : (
          <dl>
            {balances.map((b) => (
              <div key={b.leave_type}>
                <dt>{b.name}</dt>
                <dd className="num">
                  {inDays(b.balance)}
                  {Number(b.pending) > 0 && ` (${inDays(b.pending)} awaiting a decision)`}
                </dd>
              </div>
            ))}
          </dl>
        ))}
    </>
  );
}

function AssignmentForm({ employee, onSaved }: { employee: Employee; onSaved: () => void }) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [position, setPosition] = useState("");
  const [type, setType] = useState("permanent");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [probation, setProbation] = useState("");
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Paginated<Position>>(`/org/positions/?campus=${employee.campus}&status=approved`)
      .then((r) => setPositions(r.results))
      .catch(() => setPositions([]));
  }, [employee.campus]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post("/assignments/", {
        employee: employee.id,
        position: Number(position),
        appointment_type: type,
        start_date: start,
        end_date: end || null,
        probation_end: probation || null,
        is_acting: acting,
      });
      setPosition("");
      setStart("");
      setEnd("");
      setProbation("");
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not add the assignment."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={submit}>
      <h3>Add assignment</h3>
      <label>
        Position
        <select id="asg-position" value={position} onChange={(e) => setPosition(e.target.value)} required>
          <option value="">Choose</option>
          {positions.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.is_vacant && !acting}>
              {p.number} {p.title} ({p.org_unit_name}){p.is_vacant ? "" : ", filled"}
            </option>
          ))}
        </select>
      </label>
      <div className="grid2">
        <label>
          Appointment type
          <select id="asg-type" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="permanent">Permanent</option>
            <option value="contract">Contract</option>
            <option value="temporary">Temporary</option>
            <option value="sessional">Sessional</option>
            <option value="seasonal">Seasonal</option>
          </select>
        </label>
        <label>
          Start
          <input id="asg-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
        </label>
        <label>
          End (optional)
          <input id="asg-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
        <label>
          Probation ends (optional)
          <input id="asg-probation" type="date" value={probation} onChange={(e) => setProbation(e.target.value)} />
        </label>
      </div>
      <label className="inline">
        <input id="asg-acting" type="checkbox" checked={acting} onChange={(e) => setActing(e.target.checked)} /> Acting appointment
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Add assignment</button>
      </div>
    </form>
  );
}
