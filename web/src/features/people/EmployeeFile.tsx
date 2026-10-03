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
import { dmy, dmyTime, inDays, initials, localToday, num, since } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { WriteLetter } from "../letters/WriteLetter";
import { SigningPanel } from "../signing/SigningPanel";
import { BackgroundTab } from "./BackgroundTab";
import { BankTab } from "./BankTab";
import { CareerSection } from "./CareerSection";
import { ContactsTab } from "./ContactsTab";
import { ContractTab } from "./ContractTab";
import { DocumentUpload } from "./DocumentUpload";
import { LeavingSection } from "./LeavingSection";
import { HistoryTab } from "./HistoryTab";
import { ItemsTab } from "./ItemsTab";
import { STATUS_LABEL } from "./labels";

type FileTab =
  | "personal"
  | "appointments"
  | "contract"
  | "leave"
  | "documents"
  | "contacts"
  | "background"
  | "bank"
  | "items"
  | "history";

/** The tabs in the design's order, with the heading each tab's panel carries. */
const TABS: [FileTab, string, string][] = [
  ["personal", "Personal", "Personal details"],
  ["appointments", "Appointments", "Appointments"],
  ["contract", "Contract", "Contract"],
  ["leave", "Leave", "Leave"],
  ["documents", "Documents", "Documents"],
  ["contacts", "Contacts", "Contacts"],
  ["background", "Background", "Background"],
  ["bank", "Bank", "Bank details"],
  ["items", "Items issued", "Items issued"],
  ["history", "History", "History"],
];
// Who sees which tab: the server enforces the same rules; this only hides what would be refused.
const BANK_ROLES = ["hr_officer", "hr_manager", "administrator", "finance", "auditor"];
const HISTORY_ROLES = ["hr_officer", "hr_manager", "administrator", "principal", "auditor"];
const DEPENDANT_ROLES = ["hr_officer", "hr_manager", "administrator", "finance", "auditor"];
// Whose leave balances may be read on someone else's file (leave.views: HR, the Principal, Finance, supervisors).
const BALANCE_ROLES = ["hr_officer", "hr_manager", "administrator", "principal", "finance", "supervisor"];

interface Props {
  employeeId: number;
  me: Me;
  /** The tab the address names, as /people/12/bank. */
  initialTab: string | null;
  onNavigate: (to: string) => void;
}

/**
 * One staff file as a page of its own (item 2.30): who the person is and the facts that matter most above
 * the tabs; each tab a panel below. The tab is kept in the address, so To do can open the Bank tab directly.
 */
export function EmployeeFile({ employeeId, me, initialTab, onNavigate }: Props) {
  const isHr = hasAnyRole(me, HR_ROLES);
  const readsBalances = hasAnyRole(me, BALANCE_ROLES);
  const tabs = TABS.filter(
    ([t]) =>
      (t !== "bank" || hasAnyRole(me, BANK_ROLES)) &&
      (t !== "history" || hasAnyRole(me, HISTORY_ROLES)) &&
      (t !== "leave" || readsBalances),
  );
  const [tab, setTab] = useState<FileTab>(() => tabs.find(([t]) => t === initialTab)?.[0] ?? "personal");
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [documents, setDocuments] = useState<EmployeeDocument[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[] | null>(null);
  const [reveal, setReveal] = useState<{ ids: Reveal; at: string } | null>(null);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  useCrumb(employee?.full_name);

  useEffect(() => {
    let current = true;
    get<Employee>(`/employees/${employeeId}/`)
      .then((e) => current && setEmployee(e))
      .catch((err) => current && setLoadError(errorMessage(err, "Could not open this file.")));
    return () => {
      current = false;
    };
  }, [employeeId, version]);

  // Days left show above the tabs and on the Leave tab, for the roles that may read them.
  useEffect(() => {
    if (!readsBalances) return;
    let current = true;
    get<{ balances: LeaveBalance[] }>(`/leave/ledger/balances/?employee=${employeeId}`)
      .then((r) => current && setBalances(r.balances))
      .catch(() => current && setBalances([]));
    return () => {
      current = false;
    };
  }, [employeeId, readsBalances, version]);

  useEffect(() => {
    const ok = <T,>(set: (v: T) => void) => (v: T) => {
      set(v);
      setError(null);
    };
    if (tab === "appointments") {
      get<Paginated<Assignment>>(`/assignments/?employee=${employeeId}`)
        .then((r) => ok(setAssignments)(r.results))
        .catch(() => setError("Could not load the appointments."));
    } else if (tab === "documents") {
      get<Paginated<EmployeeDocument>>(`/documents/?employee=${employeeId}`)
        .then((r) => ok(setDocuments)(r.results))
        .catch(() => setError("Could not load the documents."));
    }
  }, [tab, employeeId, version]);

  function choose(next: FileTab) {
    setTab(next);
    setError(null);
    // The address follows the tab, without a new page: a link or a reload opens the same tab.
    window.history.replaceState(null, "", `#/people/${employeeId}/${next}`);
  }

  async function showIdentifiers() {
    try {
      const ids = await post<Reveal>(`/employees/${employeeId}/reveal/`);
      setReveal({ ids, at: new Date().toISOString() });
    } catch (err) {
      setError(errorMessage(err, "The identifiers could not be shown."));
    }
  }

  if (!employee)
    return loadError ? (
      <>
        <h1>Staff file</h1>
        <p role="alert" className="error">
          {loadError}
        </p>
      </>
    ) : (
      <p className="loading">Loading…</p>
    );

  const changed = () => setVersion((v) => v + 1);
  const annual = balances?.find((b) => b.code === "ANN");
  const heading = TABS.find(([t]) => t === tab)![2];
  const identifier = (masked: string | null, full: string | null | undefined) =>
    (reveal ? full : masked) || "Not recorded";
  const field = (value: string | null | undefined) => value || "Not recorded";

  return (
    <div className="file">
      <section className="file-head" aria-labelledby="file-name">
        <div className="file-who">
          <span className="initials big" aria-hidden="true">
            {initials(employee.full_name)}
          </span>
          <div className="stacked grow">
            <div className="file-title">
              <h1 id="file-name">{employee.full_name}</h1>
              <span className={employee.status === "active" ? "chip chip-approved" : "chip"}>
                {STATUS_LABEL[employee.status]}
              </span>
              {employee.appointment_type && <span className="chip">{employee.appointment_type}</span>}
            </div>
            <span className="muted">
              {[employee.employee_no, employee.position_title, employee.unit_name, employee.campus_name]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </div>
          {isHr && (
            <div className="actions">
              {tab !== "documents" && (
                <button
                  className="secondary"
                  onClick={() => {
                    setWriting(true);
                    choose("documents");
                  }}
                >
                  Write a letter
                </button>
              )}
              <button onClick={() => onNavigate(`/people/${employee.id}/edit`)}>Edit details</button>
            </div>
          )}
        </div>
        <dl className="facts">
          <div>
            <dt>Started</dt>
            <dd>{employee.started ? dmy(employee.started) : "Not appointed"}</dd>
            {employee.started && <dd className="fact-sub">{since(employee.started, localToday())}</dd>}
          </div>
          <div>
            <dt>Manager</dt>
            <dd>{employee.manager_name ?? (employee.started ? "Campus supervisors" : "None yet")}</dd>
            {employee.unit_name && <dd className="fact-sub">{employee.unit_name}</dd>}
          </div>
          {readsBalances && (
            <div>
              <dt>Annual leave left</dt>
              <dd>{annual ? inDays(Math.max(num(annual.available), 0)) : "None recorded"}</dd>
              {annual && (
                <dd className="fact-sub">
                  {num(annual.pending) > 0 ? `${inDays(annual.pending)} awaiting a decision` : "Nothing awaiting a decision"}
                </dd>
              )}
            </div>
          )}
          <div>
            <dt>Contract</dt>
            <dd>{employee.contract_type ?? "None on file"}</dd>
            {employee.started && <dd className="fact-sub">{employee.ends ? `Ends ${dmy(employee.ends)}` : "No end date"}</dd>}
          </div>
          {employee.probation_end && (
            <div>
              <dt>Probation ends</dt>
              <dd>{dmy(employee.probation_end)}</dd>
            </div>
          )}
        </dl>
      </section>

      {employee.restricted && employee.restricted.length > 0 && (
        <div className="notice restricted" role="note" aria-label="Held back from use">
          <strong>Held back from use at the person&apos;s request:</strong> {employee.restricted.join("; ")}. It is kept and
          may be corrected, but letters, changes to the appointment and the other systems wait until it is lifted.
        </div>
      )}

      <div className="tabs" role="tablist" aria-label="Employee file">
        {tabs.map(([t, label]) => (
          <button
            key={t}
            role="tab"
            id={`file-tab-${t}`}
            aria-selected={tab === t}
            aria-controls="file-panel"
            className={tab === t ? "tab active" : "tab"}
            onClick={() => choose(t)}
          >
            {label}
          </button>
        ))}
      </div>

      <section className="file-panel" role="tabpanel" id="file-panel" aria-labelledby={`file-tab-${tab}`}>
        <div className="spread file-panel-head">
          <h2>{heading}</h2>
          {tab === "personal" && isHr && (
            <button className="secondary" onClick={() => (reveal ? setReveal(null) : showIdentifiers())}>
              {reveal ? "Hide identifiers" : "Show identifiers"}
            </button>
          )}
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}

        {tab === "personal" && (
          <>
            <dl className="fields">
              <div>
                <dt>Date of birth</dt>
                <dd>{dmy(employee.date_of_birth)}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{field(employee.email)}</dd>
              </div>
              <div>
                <dt>Phone</dt>
                <dd>{field(employee.phone)}</dd>
              </div>
              <div>
                <dt>Address</dt>
                <dd>{field(employee.address)}</dd>
              </div>
              <div>
                <dt>National ID</dt>
                <dd>{identifier(employee.national_id_masked, reveal?.ids.national_id)}</dd>
              </div>
              <div>
                <dt>NIS number</dt>
                <dd>{identifier(employee.nis_no_masked, reveal?.ids.nis_no)}</dd>
              </div>
              <div>
                <dt>TIN</dt>
                <dd>{identifier(employee.tin_masked, reveal?.ids.tin)}</dd>
              </div>
            </dl>
            {isHr && (
              <p className="muted small">
                {reveal
                  ? `Shown at ${dmyTime(reveal.at).slice(-5)} by ${me.name}. Showing identifiers is recorded in the audit log.`
                  : "Identifiers stay hidden until you show them. Each time is recorded in the audit log."}
              </p>
            )}
          </>
        )}

        {tab === "appointments" && (
          <>
            {assignments.length === 0 ? (
              <p className="muted">No appointments.</p>
            ) : (
              <ul className="plain">
                {assignments.map((a) => (
                  <li key={a.id}>
                    <strong>{a.position_title}</strong> {a.is_acting && <em>(acting)</em>}
                    <br />
                    <span className="muted small">
                      {a.appointment_type}, from {dmy(a.start_date)}
                      {a.end_date ? ` to ${dmy(a.end_date)}` : ""}
                      {a.probation_end ? `, probation ends ${dmy(a.probation_end)}` : ""}
                      {a.confirmed_on ? `, confirmed ${dmy(a.confirmed_on)}` : ""} · {a.pay_grade_name} · {a.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <CareerSection employee={employee} me={me} onChanged={changed} />
            <LeavingSection employee={employee} me={me} onChanged={changed} />
            {isHr && <AssignmentForm employee={employee} onSaved={changed} />}
          </>
        )}

        {tab === "contract" && <ContractTab employee={employee} isHr={isHr} />}

        {tab === "leave" &&
          (balances === null ? (
            <p className="loading">Loading…</p>
          ) : balances.length === 0 ? (
            <p className="muted">No leave ledger entries.</p>
          ) : (
            <dl className="fields">
              {balances.map((b) => (
                <div key={b.leave_type}>
                  <dt>{b.name} left</dt>
                  <dd className="num">
                    {inDays(Math.max(num(b.available), 0))}
                    {num(b.pending) > 0 && ` (${inDays(b.pending)} awaiting a decision)`}
                  </dd>
                </div>
              ))}
            </dl>
          ))}

        {tab === "documents" && (
          <>
            {documents.length === 0 ? (
              <p className="muted">No documents on file yet.</p>
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
            <SigningPanel employee={employee} documents={documents} me={me} version={version} />
            {isHr && <WriteLetter key={writing ? "writing" : "closed"} employee={employee} onIssued={changed} startOpen={writing} />}
            {isHr && <DocumentUpload employee={employee} onSaved={changed} />}
          </>
        )}

        {tab === "contacts" && (
          <ContactsTab employeeId={employee.id} canEdit={isHr} canSeeDependants={hasAnyRole(me, DEPENDANT_ROLES)} />
        )}

        {tab === "background" && <BackgroundTab employeeId={employee.id} canEdit={isHr} />}

        {tab === "bank" && <BankTab employeeId={employee.id} me={me} />}

        {tab === "items" && <ItemsTab employee={employee} me={me} />}

        {tab === "history" && <HistoryTab key={version} employeeId={employee.id} />}
      </section>
    </div>
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
    <form className="stack sub-form" onSubmit={submit} aria-label="Add an appointment">
      <h3>Add an appointment</h3>
      <p className="muted small">
        For someone joining, or a second appointment. To move someone, raise their step, have them act or confirm them,
        record a change above, so their file keeps the story.
      </p>
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
