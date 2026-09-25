import { useEffect, useState } from "react";
import { ApiError, get, post } from "../../api/client";
import {
  HR_ROLES,
  hasAnyRole,
  type Assignment,
  type Employee,
  type EmployeeDocument,
  type LeaveBalance,
  type Me,
  type Paginated,
  type Reveal,
} from "../../api/types";

interface Props {
  me: Me;
  campusId: number | null;
  initialId: number | null;
  onNavigate: (to: string) => void;
}

const STATUS_LABEL: Record<Employee["status"], string> = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  separated: "Separated",
};

type FileTab = "personal" | "assignments" | "documents" | "leave";

/** Wireframe 2: searchable directory; the selected employee opens a tabbed file. */
export function DirectoryScreen({ me, campusId, initialId, onNavigate }: Props) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<Employee[]>([]);
  const [count, setCount] = useState(0);
  const [selected, setSelected] = useState<Employee | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    if (campusId) params.set("campus", String(campusId));
    const handle = setTimeout(() => {
      get<Paginated<Employee>>(`/employees/?${params}`)
        .then((r) => {
          setRows(r.results);
          setCount(r.count);
          setError(null);
        })
        .catch((err) => setError(err instanceof ApiError ? err.detail : "Could not load employees."));
    }, 250);
    return () => clearTimeout(handle);
  }, [query, status, campusId]);

  useEffect(() => {
    if (initialId && selected?.id !== initialId) {
      get<Employee>(`/employees/${initialId}/`).then(setSelected).catch(() => setSelected(null));
    }
  }, [initialId, selected?.id]);

  function select(employee: Employee) {
    setSelected(employee);
    onNavigate(`/people/${employee.id}`);
  }

  return (
    <div className="split">
      <section>
        <h1>People</h1>
        <div className="filters">
          <input id="people-search" placeholder="Search name or employee number" value={query} onChange={(e) => setQuery(e.target.value)} />
          <select id="people-status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Any status</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <span className="muted">{count} staff</span>
        </div>
        {error && <p className="error">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>No.</th>
              <th>Name</th>
              <th>Position</th>
              <th>Campus</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} onClick={() => select(e)} className={selected?.id === e.id ? "selected" : ""}>
                <td>{e.employee_no}</td>
                <td>{e.full_name}</td>
                <td>{e.position_title ?? <span className="muted">Unassigned</span>}</td>
                <td>{e.campus_name}</td>
                <td>{STATUS_LABEL[e.status]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <aside className="panel">
        {selected ? <EmployeeFile key={selected.id} employee={selected} me={me} /> : <p className="muted">Select a person to open their file.</p>}
      </aside>
    </div>
  );
}

function EmployeeFile({ employee, me }: { employee: Employee; me: Me }) {
  const [tab, setTab] = useState<FileTab>("personal");
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [documents, setDocuments] = useState<EmployeeDocument[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canReveal = hasAnyRole(me, HR_ROLES);

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
  }, [tab, employee.id]);

  async function doReveal() {
    try {
      setReveal(await post<Reveal>(`/employees/${employee.id}/reveal/`));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Reveal failed.");
    }
  }

  return (
    <>
      <h2>{employee.full_name}</h2>
      <p className="muted">
        {employee.employee_no} · {employee.campus_name} · {STATUS_LABEL[employee.status]}
      </p>
      <div className="tabs" role="tablist">
        {(["personal", "assignments", "documents", "leave"] as FileTab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}

      {tab === "personal" && (
        <dl>
          <dt>Position</dt>
          <dd>{employee.position_title ?? "Unassigned"}</dd>
          <dt>Email</dt>
          <dd>{employee.email || "not recorded"}</dd>
          <dt>Phone</dt>
          <dd>{employee.phone || "not recorded"}</dd>
          <dt>National ID</dt>
          <dd>{reveal?.national_id ?? employee.national_id_masked ?? "not recorded"}</dd>
          <dt>NIS number</dt>
          <dd>{reveal?.nis_no ?? employee.nis_no_masked ?? "not recorded"}</dd>
          <dt>TIN</dt>
          <dd>{reveal?.tin ?? employee.tin_masked ?? "not recorded"}</dd>
          {canReveal && !reveal && (
            <dd>
              <button className="secondary" onClick={doReveal}>
                Reveal identifiers (audited)
              </button>
            </dd>
          )}
        </dl>
      )}
      {tab === "assignments" &&
        (assignments.length === 0 ? (
          <p className="muted">No assignments.</p>
        ) : (
          <ul className="plain">
            {assignments.map((a) => (
              <li key={a.id}>
                <strong>{a.position_title}</strong> {a.is_acting && <em>(acting)</em>}
                <br />
                <span className="muted small">
                  {a.appointment_type}, from {a.start_date}
                  {a.end_date ? ` to ${a.end_date}` : ""}
                  {a.probation_end ? `, probation ends ${a.probation_end}` : ""} · {a.status}
                </span>
              </li>
            ))}
          </ul>
        ))}
      {tab === "documents" &&
        (documents.length === 0 ? (
          <p className="muted">No documents on file.</p>
        ) : (
          <ul className="plain">
            {documents.map((d) => (
              <li key={d.id}>
                <a href={d.file} target="_blank" rel="noreferrer">
                  {d.title}
                </a>{" "}
                <span className="muted small">
                  v{d.version} · {d.doc_type} · {d.classification}
                </span>
              </li>
            ))}
          </ul>
        ))}
      {tab === "leave" &&
        (balances.length === 0 ? (
          <p className="muted">No leave ledger entries.</p>
        ) : (
          <dl>
            {balances.map((b) => (
              <div key={b.leave_type}>
                <dt>{b.name}</dt>
                <dd className="num">{b.balance} days</dd>
              </div>
            ))}
          </dl>
        ))}
    </>
  );
}
