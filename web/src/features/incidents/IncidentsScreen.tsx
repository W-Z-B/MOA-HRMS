import { useCallback, useEffect, useState } from "react";
import { errorMessage, get, getAll } from "../../api/client";
import {
  INCIDENT_READ_ROLES,
  hasAnyRole,
  type Incident,
  type IncidentSummary,
  type Me,
  type MyIncident,
  type MySafetyAction,
} from "../../api/types";
import { dmy, dmyTime } from "../../app/format";
import { IncidentDetail, MarkDone } from "./IncidentDetail";
import { ReportForm } from "./ReportForm";

const STATES: [string, string][] = [
  ["", "All"],
  ["reported", "Reported"],
  ["investigating", "Being looked into"],
  ["closed", "Closed"],
];

/** A safety action given to me, marked done here. */
function MyAction({ item, onDone }: { item: MySafetyAction; onDone: () => void }) {
  return (
    <li>
      <strong>{item.what}</strong>{" "}
      <span className="muted small">
        {item.reference}, at {item.place}. By {dmy(item.due_on)}.
      </span>
      {item.overdue && (
        <>
          {" "}
          <span className="chip chip-rejected">Late</span>
        </>
      )}
      <MarkDone id={item.id} what={item.what} onDone={onDone} />
    </li>
  );
}

/** Accidents and incidents (item 1.16): anyone reports; HR keeps the register and sends the notices. */
export function IncidentsScreen({ me, incidentId, onNavigate }: { me: Me; incidentId: number | null; onNavigate: (to: string) => void }) {
  const reader = hasAnyRole(me, INCIDENT_READ_ROLES);
  const [reporting, setReporting] = useState(false);
  const [mine, setMine] = useState<MyIncident[]>([]);
  const [actions, setActions] = useState<MySafetyAction[]>([]);
  const [register, setRegister] = useState<IncidentSummary[] | null>(null);
  const [state, setState] = useState("");
  const [loaded, setLoaded] = useState<Incident | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMine = useCallback(() => {
    get<MyIncident[]>("/incidents/mine/")
      .then(setMine)
      .catch(() => setMine([]));
    get<MySafetyAction[]>("/incidents/actions/mine/")
      .then(setActions)
      .catch(() => setActions([]));
  }, []);
  const loadRegister = useCallback(() => {
    if (!reader) return;
    getAll<IncidentSummary>(`/incidents/${state ? `?state=${state}` : ""}`)
      .then(setRegister)
      .catch((err) => setError(errorMessage(err, "Could not load the register.")));
  }, [reader, state]);
  useEffect(loadMine, [loadMine]);
  useEffect(loadRegister, [loadRegister]);
  useEffect(() => {
    if (incidentId === null || !reader) return;
    get<Incident>(`/incidents/${incidentId}/`)
      .then(setLoaded)
      .catch((err) => setError(errorMessage(err, "That incident is not one you may see.")));
  }, [incidentId, reader]);
  const shown = incidentId !== null && loaded?.id === incidentId ? loaded : null;

  return (
    <>
      <h1>Incidents</h1>
      <p className="muted">
        Report an accident, a near miss, anything dangerous, or an illness caused by work. Human Resources keeps the
        register and sends the notices the Occupational Safety and Health Act requires.
      </p>
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
      {reporting ? (
        <ReportForm
          me={me}
          onCancel={() => setReporting(false)}
          onReported={(made) => {
            setReporting(false);
            setNotice(`Reported as ${made.reference}. Human Resources has been told.`);
            loadMine();
            loadRegister();
          }}
        />
      ) : (
        <div className="actions">
          <button
            onClick={() => {
              setNotice(null);
              setReporting(true);
            }}
          >
            Report an incident
          </button>
        </div>
      )}

      {actions.length > 0 && (
        <section className="stack" aria-labelledby="my-safety-actions">
          <h2 id="my-safety-actions">Actions given to you</h2>
          <ul className="plain stack">
            {actions.map((item) => (
              <MyAction
                key={item.id}
                item={item}
                onDone={() => {
                  setNotice("Marked done. Thank you.");
                  loadMine();
                }}
              />
            ))}
          </ul>
        </section>
      )}

      {mine.length > 0 && (
        <section className="stack" aria-labelledby="my-incidents">
          <h2 id="my-incidents">Reported by you, or about you</h2>
          <ul className="plain stack" aria-label="Reported by you, or about you">
            {mine.map((m) => (
              <li key={m.id}>
                <strong>{m.reference}</strong> {m.kind_name.toLowerCase()} at {m.place}, {dmyTime(m.occurred_at)}{" "}
                <span className="chip">{m.state_name}</span>
                {m.my_injury && (
                  <span className="muted small">
                    <br />
                    You were hurt: {m.my_injury.injury || "the injury is not recorded yet"}
                    {m.my_injury.off_work_from && `; off work from ${dmy(m.my_injury.off_work_from)}`}
                    {m.my_injury.back_at_work_on && ` to ${dmy(m.my_injury.back_at_work_on)}`}
                    {m.my_injury.nis_form_on && `; NIS notice of accident given ${dmy(m.my_injury.nis_form_on)}`}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {reader && (
        <section className="stack" aria-labelledby="incident-register">
          <h2 id="incident-register">The register</h2>
          <div className="filters">
            <label className="inline">
              Showing
              <select value={state} onChange={(e) => setState(e.target.value)}>
                {STATES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {register !== null && register.length === 0 && <p className="muted">Nothing in the register.</p>}
          {register !== null && register.length > 0 && (
            <table className="cards" aria-label="Incidents">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>When</th>
                  <th>What</th>
                  <th>Where</th>
                  <th>Hurt</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {register.map((i) => (
                  <tr key={i.id}>
                    <td data-label="Reference">
                      <button className="link" onClick={() => onNavigate(`/incidents/${i.id}`)}>
                        {i.reference}
                      </button>
                    </td>
                    <td data-label="When">{dmyTime(i.occurred_at)}</td>
                    <td data-label="What">{i.kind_name}</td>
                    <td data-label="Where">
                      {i.place}, {i.campus_name}
                    </td>
                    <td data-label="Hurt">{i.people_hurt}</td>
                    <td data-label="State">
                      {i.state_name}
                      {i.notices_overdue && (
                        <>
                          {" "}
                          <span className="chip chip-rejected">Notice late</span>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
      {shown && <IncidentDetail key={shown.id} me={me} initial={shown} onChanged={loadRegister} />}
    </>
  );
}
