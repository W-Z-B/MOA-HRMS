import { useEffect, useState } from "react";
import { get } from "../../api/client";
import type { Employee, Paginated } from "../../api/types";

interface Props {
  campusId: number | null;
}

const STATUS_LABEL: Record<Employee["status"], string> = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  separated: "Separated",
};

/** Wireframe 2: searchable directory with filters; selected employee opens a file panel. */
export function DirectoryScreen({ campusId }: Props) {
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
        .catch((err) => setError(err.detail ?? "Could not load employees."));
    }, 250);
    return () => clearTimeout(handle);
  }, [query, status, campusId]);

  return (
    <div className="split">
      <section>
        <h1>People</h1>
        <div className="filters">
          <input
            id="people-search"
            placeholder="Search name or employee number"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
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
              <tr key={e.id} onClick={() => setSelected(e)} className={selected?.id === e.id ? "selected" : ""}>
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
        {selected ? (
          <>
            <h2>{selected.full_name}</h2>
            <dl>
              <dt>Employee number</dt>
              <dd>{selected.employee_no}</dd>
              <dt>Position</dt>
              <dd>{selected.position_title ?? "Unassigned"}</dd>
              <dt>Campus</dt>
              <dd>{selected.campus_name}</dd>
              <dt>NIS number</dt>
              <dd>{selected.nis_no_masked ?? "not recorded"}</dd>
              <dt>TIN</dt>
              <dd>{selected.tin_masked ?? "not recorded"}</dd>
              <dt>Email</dt>
              <dd>{selected.email || "not recorded"}</dd>
              <dt>Phone</dt>
              <dd>{selected.phone || "not recorded"}</dd>
            </dl>
            <p className="muted">
              Identifiers stay masked here. HR roles can reveal them through the audited reveal action (Sprint 2
              adds the button and the file tabs).
            </p>
          </>
        ) : (
          <p className="muted">Select a person to open their file.</p>
        )}
      </aside>
    </div>
  );
}
