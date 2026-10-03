import { useEffect, useState } from "react";
import { ApiError, get, getAll } from "../../api/client";
import { HR_ROLES, hasAnyRole, type Employee, type Me, type OrgUnit, type Paginated } from "../../api/types";
import { initials } from "../../app/format";
import { shortCampus } from "../../app/people";
import { STATUS_LABEL } from "./labels";

interface Props {
  me: Me;
  campusId: number | null;
  onNavigate: (to: string) => void;
}

/**
 * People (item 2.30): one list with search and filters for status and unit, narrowed by the campus switch.
 * A file opens as a page of its own. On a phone each row reads as a card.
 */
export function PeopleScreen({ me, campusId, onNavigate }: Props) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [unit, setUnit] = useState("");
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [rows, setRows] = useState<Employee[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isHr = hasAnyRole(me, HR_ROLES);
  const campus = me.campuses?.find((c) => c.id === campusId);
  const scope = campus ? campus.name : (me.campuses?.length ?? 0) > 1 ? "all campuses" : (me.campuses?.[0]?.name ?? "your campus");

  useEffect(() => {
    getAll<OrgUnit>(`/org/units/${campusId ? `?campus=${campusId}` : ""}`)
      .then((all) => setUnits([...all].sort((a, b) => a.name.localeCompare(b.name))))
      .catch(() => setUnits([]));
  }, [campusId]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (status) params.set("status", status);
    if (unit) params.set("org_unit", unit);
    if (campusId) params.set("campus", String(campusId));
    let current = true;
    const handle = setTimeout(() => {
      get<Paginated<Employee>>(`/employees/?${params}`)
        .then((page) => {
          if (!current) return;
          setRows(page.results);
          setCount(page.count);
          setNext(page.next);
          setError(null);
        })
        .catch((err) => current && setError(err instanceof ApiError ? err.detail : "Could not load the staff list."));
    }, 250);
    return () => {
      current = false;
      clearTimeout(handle);
    };
  }, [query, status, unit, campusId]);

  async function more() {
    if (!next) return;
    const url = new URL(next, window.location.origin);
    try {
      const page = await get<Paginated<Employee>>(`${url.pathname.replace(/^\/api\/v1/, "")}${url.search}`);
      setRows((shown) => [...shown, ...page.results]);
      setNext(page.next);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not load more staff.");
    }
  }

  const filtered = Boolean(query.trim() || status || unit);
  const open = (e: { preventDefault: () => void }, employee: Employee) => {
    e.preventDefault();
    onNavigate(`/people/${employee.id}`);
  };

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>People</h1>
          <p className="muted lead" aria-live="polite">
            {count === null ? "Loading…" : `${count} staff on ${scope}`}
          </p>
        </div>
        {isHr && (
          <div className="actions">
            <button className="secondary" onClick={() => onNavigate("/people/scanning")}>
              File scanned papers
            </button>
            <button onClick={() => onNavigate("/people/new")}>New employee</button>
          </div>
        )}
      </div>
      <div className="filters" role="search" aria-label="Find staff">
        <input
          type="search"
          className="grow-field"
          aria-label="Search staff"
          placeholder="Search by name, employee number or post"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select aria-label="Unit" value={unit} onChange={(e) => setUnit(e.target.value)}>
          <option value="">All units</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {count === 0 && filtered ? (
        <div className="panel-card padded spread">
          <span>No one matches those filters.</span>
          <button
            className="secondary"
            onClick={() => {
              setQuery("");
              setStatus("");
              setUnit("");
            }}
          >
            Clear the filters
          </button>
        </div>
      ) : (
        <table className="people" aria-label="Staff">
          <thead>
            <tr>
              <th>Employee</th>
              <th>Position</th>
              <th>Campus</th>
              <th>Appointment</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} onClick={(event) => open(event, e)}>
                <td className="who">
                  <span className="who-cell">
                    <span className="initials" aria-hidden="true">
                      {initials(e.full_name)}
                    </span>
                    <span className="stacked">
                      {/* The row opens on a click anywhere; the link makes it reachable by keyboard and screen reader. */}
                      <a
                        href={`#/people/${e.id}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          open(event, e);
                        }}
                      >
                        {e.full_name}
                      </a>
                      <span className="muted small num">
                        {e.employee_no}
                        <span className="phone-only"> · {shortCampus(e.campus_name)}</span>
                      </span>
                    </span>
                  </span>
                </td>
                <td className="post">
                  <span className="stacked">
                    <span>{e.position_title ?? <span className="muted">Unassigned</span>}</span>
                    {e.unit_name && <span className="muted small">{e.unit_name}</span>}
                  </span>
                </td>
                <td className="wide-only">{e.campus_name}</td>
                <td className="wide-only">{e.appointment_type ?? <span className="muted">None</span>}</td>
                <td className="wide-only">
                  <span className={e.status === "active" ? "chip chip-approved" : "chip"}>{STATUS_LABEL[e.status]}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {next && (
        <div className="actions more">
          <button className="secondary" onClick={more}>
            Show more
          </button>
          <span className="muted small">
            Showing {rows.length} of {count}
          </span>
        </div>
      )}
    </>
  );
}
