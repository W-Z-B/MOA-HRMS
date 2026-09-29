import { useEffect, useState } from "react";
import { ApiError, get } from "../../api/client";
import { HR_ROLES, hasAnyRole, type Employee, type Me, type Paginated } from "../../api/types";
import { EmployeeFile } from "./EmployeeFile";
import { EmployeeForm } from "./EmployeeForm";

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

type Panel = { mode: "view" } | { mode: "create" } | { mode: "edit" };

/** Wireframe 2: searchable directory; the panel shows the selected file, or a create or edit form. */
export function DirectoryScreen({ me, campusId, initialId, onNavigate }: Props) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<Employee[]>([]);
  const [count, setCount] = useState(0);
  const [selected, setSelected] = useState<Employee | null>(null);
  const [panel, setPanel] = useState<Panel>({ mode: "view" });
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const isHr = hasAnyRole(me, HR_ROLES);

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
  }, [query, status, campusId, version]);

  useEffect(() => {
    if (initialId && selected?.id !== initialId) {
      get<Employee>(`/employees/${initialId}/`).then(setSelected).catch(() => setSelected(null));
    }
  }, [initialId, selected?.id]);

  function select(employee: Employee) {
    setSelected(employee);
    setPanel({ mode: "view" });
    onNavigate(`/people/${employee.id}`);
  }

  function saved(employee: Employee) {
    setSelected(employee);
    setPanel({ mode: "view" });
    setVersion((v) => v + 1);
    onNavigate(`/people/${employee.id}`);
  }

  return (
    <div className="split">
      <section>
        <div className="panel-head">
          <h1>People</h1>
          {isHr && (
            <button onClick={() => setPanel({ mode: "create" })}>
              New employee
            </button>
          )}
        </div>
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
        {panel.mode === "create" && (
          <EmployeeForm existing={null} defaultCampus={campusId} onSaved={saved} onCancel={() => setPanel({ mode: "view" })} />
        )}
        {panel.mode === "edit" && selected && (
          <EmployeeForm existing={selected} defaultCampus={campusId} onSaved={saved} onCancel={() => setPanel({ mode: "view" })} />
        )}
        {panel.mode === "view" &&
          (selected ? (
            <EmployeeFile key={selected.id} employee={selected} me={me} onEdit={() => setPanel({ mode: "edit" })} />
          ) : (
            <p className="muted">Select a person to open their file{isHr ? ", or create a new employee" : ""}.</p>
          ))}
      </aside>
    </div>
  );
}
