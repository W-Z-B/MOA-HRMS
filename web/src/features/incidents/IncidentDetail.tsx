import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, getAll, post } from "../../api/client";
import {
  INCIDENT_KEEP_ROLES,
  hasAnyRole,
  type Employee,
  type Incident,
  type IncidentKind,
  type IncidentPerson,
  type Me,
  type MySafetyAction,
} from "../../api/types";
import { ActionForm as SharedActionForm } from "../../app/ActionForm";
import { dmy, dmyTime, localToday } from "../../app/format";

const ActionForm = SharedActionForm<Incident>;
const WHO: [string, string][] = [
  ["staff", "Member of staff"],
  ["student", "Student"],
  ["contractor", "Contractor"],
  ["visitor", "Visitor"],
];
const TREATMENTS: [string, string][] = [
  ["", "Not known yet"],
  ["none", "None needed"],
  ["first_aid", "First aid"],
  ["doctor", "Doctor or clinic"],
  ["hospital", "Hospital"],
];
/** Why no notice is listed, when none is. */
const NO_NOTICE: Record<IncidentKind, string> = {
  accident:
    "None so far. One is due when an accident kills a member of staff, or keeps them from full wages for more than a day: record them below.",
  near_miss: "None: a near miss needs no notice unless it was a dangerous occurrence.",
  dangerous: "None: away from an industrial establishment the Act asks for no notice of a dangerous occurrence.",
  disease: "None until the member of staff affected is recorded below.",
};

function PersonUpdate({ incident, person, onDone }: { incident: Incident; person: IncidentPerson; onDone: (fresh: Incident) => void }) {
  const [off, setOff] = useState(person.off_work_from ?? "");
  const [back, setBack] = useState(person.back_at_work_on ?? "");
  const [nis, setNis] = useState(person.nis_form_on ?? "");
  const [died, setDied] = useState(person.died_on ?? "");
  const [treatment, setTreatment] = useState(person.treatment ?? "");
  const [injury, setInjury] = useState(person.injury ?? "");
  return (
    <details>
      <summary>Update {person.name}</summary>
      <ActionForm
        label={`Update ${person.name}`}
        submit="Save"
        method="PATCH"
        path={`/incidents/${incident.id}/people/${person.id}/`}
        fields={() => ({
          injury,
          treatment,
          off_work_from: off || null,
          back_at_work_on: back || null,
          nis_form_on: nis || null,
          died_on: died || null,
        })}
        onDone={onDone}
      >
        <label>
          Injury or illness
          <textarea rows={2} value={injury} onChange={(e) => setInjury(e.target.value)} />
        </label>
        <div className="grid2">
          <label>
            Treatment
            <select value={treatment} onChange={(e) => setTreatment(e.target.value)}>
              {TREATMENTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            First day off work
            <input type="date" value={off} onChange={(e) => setOff(e.target.value)} />
          </label>
          <label>
            Back at work on
            <input type="date" value={back} onChange={(e) => setBack(e.target.value)} />
          </label>
          {person.who === "staff" && (
            <label>
              NIS notice of accident given on
              <input type="date" value={nis} onChange={(e) => setNis(e.target.value)} />
            </label>
          )}
          <label>
            Died on
            <input type="date" value={died} onChange={(e) => setDied(e.target.value)} />
          </label>
        </div>
      </ActionForm>
    </details>
  );
}

function AddPerson({ incident, staff, onDone }: { incident: Incident; staff: Employee[]; onDone: (fresh: Incident) => void }) {
  const [who, setWho] = useState("staff");
  const [employee, setEmployee] = useState("");
  const [name, setName] = useState("");
  const [injury, setInjury] = useState("");
  const [treatment, setTreatment] = useState("");
  const [off, setOff] = useState("");
  const recorded = new Set(incident.people.map((p) => p.employee));
  return (
    <ActionForm
      label="Record someone hurt"
      path={`/incidents/${incident.id}/people/`}
      fields={() => ({
        who,
        employee: who === "staff" ? Number(employee) : null,
        name: who === "staff" ? "" : name,
        injury,
        treatment,
        off_work_from: off || null,
      })}
      onDone={(fresh) => {
        setEmployee("");
        setName("");
        setInjury("");
        setOff("");
        onDone(fresh);
      }}
    >
      <div className="grid2">
        <label>
          Who
          <select value={who} onChange={(e) => setWho(e.target.value)}>
            {WHO.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {who === "staff" ? (
          <label>
            Member of staff
            <select value={employee} onChange={(e) => setEmployee(e.target.value)} required>
              <option value="">Choose</option>
              {staff
                .filter((e) => !recorded.has(e.id))
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name} ({e.employee_no})
                  </option>
                ))}
            </select>
          </label>
        ) : (
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
          </label>
        )}
        <label>
          Treatment
          <select value={treatment} onChange={(e) => setTreatment(e.target.value)}>
            {TREATMENTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          First day off work <span className="muted small">(if any)</span>
          <input type="date" value={off} onChange={(e) => setOff(e.target.value)} />
        </label>
      </div>
      <label>
        Injury or illness, and the part of the body
        <textarea rows={2} value={injury} onChange={(e) => setInjury(e.target.value)} />
      </label>
    </ActionForm>
  );
}

function RecordNotice({ incident, onDone }: { incident: Incident; onDone: (fresh: Incident) => void }) {
  const unsent = incident.duties.flatMap((d) =>
    d.to
      .filter((t) => t.sent_on === null)
      .map((t) => ({
        key: `${d.duty}|${d.person ?? ""}|${t.recipient}`,
        label: `${d.duty_name}${d.person_name ? ` (${d.person_name})` : ""}: ${t.recipient_name}`,
      })),
  );
  const [which, setWhich] = useState("");
  const [sentOn, setSentOn] = useState("");
  const [how, setHow] = useState("");
  const [reference, setReference] = useState("");
  if (unsent.length === 0) return null;
  const chosen = which || unsent[0].key;
  return (
    <ActionForm
      label="Record a notice sent"
      path={`/incidents/${incident.id}/notices/`}
      fields={() => {
        const [duty, person, recipient] = chosen.split("|");
        return { duty, recipient, person: person ? Number(person) : null, sent_on: sentOn, how, their_reference: reference };
      }}
      onDone={(fresh) => {
        setWhich("");
        setReference("");
        onDone(fresh);
      }}
    >
      <label>
        Notice
        <select value={chosen} onChange={(e) => setWhich(e.target.value)}>
          {unsent.map((u) => (
            <option key={u.key} value={u.key}>
              {u.label}
            </option>
          ))}
        </select>
      </label>
      <div className="grid2">
        <label>
          Sent on
          <input type="date" value={sentOn} onChange={(e) => setSentOn(e.target.value)} required />
        </label>
        <label>
          How
          <input value={how} onChange={(e) => setHow(e.target.value)} required maxLength={80} placeholder="By hand" />
        </label>
        <label>
          Their reference <span className="muted small">(if any)</span>
          <input value={reference} onChange={(e) => setReference(e.target.value)} maxLength={80} />
        </label>
      </div>
    </ActionForm>
  );
}

/** Marks a safety action done today, with a word on what was done: by its owner, or by HR. */
export function MarkDone({ id, what, onDone }: { id: number; what: string; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post<MySafetyAction>(`/incidents/actions/${id}/done/`, { done_on: localToday(), note });
      onDone();
    } catch (err) {
      setError(errorMessage(err, "That was not recorded."));
    }
  }

  return (
    <form className="inline-form" onSubmit={send} aria-label={`Mark done: ${what}`}>
      <label>
        What was done <span className="muted small">(optional)</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <button type="submit" className="secondary">
        Mark done
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}

/** One incident as the register holds it (item 1.16): HR sees and records everything; the Principal, supervisors
 * and the auditor see it without the injuries. */
export function IncidentDetail({ me, initial, onChanged }: { me: Me; initial: Incident; onChanged: () => void }) {
  const [incident, setIncident] = useState(initial);
  const [staff, setStaff] = useState<Employee[]>([]);
  const [cause, setCause] = useState(initial.cause);
  const [investigatedOn, setInvestigatedOn] = useState(initial.investigated_on ?? "");
  const [what, setWhat] = useState("");
  const [owner, setOwner] = useState("");
  const [dueOn, setDueOn] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const keeper = hasAnyRole(me, INCIDENT_KEEP_ROLES);
  const open = incident.state !== "closed";
  const base = `/incidents/${incident.id}`;

  useEffect(() => {
    if (!keeper) return;
    getAll<Employee>("/employees/?status=active")
      .then(setStaff)
      .catch(() => setStaff([]));
  }, [keeper]);

  const done = (message: string) => (fresh: Incident) => {
    setIncident(fresh);
    setNotice(message);
    setError(null);
    onChanged();
  };

  function refresh() {
    get<Incident>(`${base}/`)
      .then(done("The action is marked done."))
      .catch((err) => setError(errorMessage(err, "Could not load the incident again.")));
  }

  async function close() {
    setError(null);
    try {
      done("The incident is closed.")(await post<Incident>(`${base}/close/`));
    } catch (err) {
      setError(errorMessage(err, "The incident was not closed."));
    }
  }

  return (
    <section className="card-block stack" aria-labelledby={`incident-${incident.id}`}>
      <h2 id={`incident-${incident.id}`}>
        {incident.reference}: {incident.kind_name.toLowerCase()} at {incident.place}
      </h2>
      <p>
        <span className="chip">{incident.state_name}</span> <span className="chip">{incident.kind_name}</span>{" "}
        {incident.industrial && <span className="chip">Industrial establishment</span>}{" "}
        <span className="muted small">
          {dmyTime(incident.occurred_at)}, {incident.org_unit_name ? `${incident.org_unit_name}, ` : ""}
          {incident.campus_name}. Reported by {incident.reported_by ?? "someone no longer on the system"}.
        </span>
      </p>
      <p className="incident-text">{incident.description}</p>
      {incident.immediate_action && <p className="muted incident-text">Done at once: {incident.immediate_action}</p>}
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

      <h3>Notices the Act requires</h3>
      {incident.duties.length === 0 ? (
        <p className="muted">{NO_NOTICE[incident.kind]}</p>
      ) : (
        <ul className="plain stack" aria-label="Notices the Act requires">
          {incident.duties.map((d) => (
            <li key={`${d.duty}-${d.person ?? 0}`}>
              <strong>{d.duty_name}</strong>
              {d.person_name ? ` (${d.person_name})` : ""}, section {d.section}: due {dmy(d.due_on)}
              {d.overdue && (
                <>
                  {" "}
                  <span className="chip chip-rejected">Late</span>
                </>
              )}
              <ul className="plain">
                {d.to.map((t) => (
                  <li key={t.recipient} className="small">
                    {t.recipient_name}: {t.sent_on ? `sent ${dmy(t.sent_on)}` : "not sent"}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {keeper && open && <RecordNotice incident={incident} onDone={done("The notice is recorded.")} />}

      <h3>People hurt</h3>
      {incident.people.length === 0 ? (
        <p className="muted">Nobody is recorded as hurt.</p>
      ) : (
        <ul className="plain stack" aria-label="People hurt">
          {incident.people.map((p) => (
            <li key={p.id}>
              <strong>{p.name}</strong> <span className="muted small">{p.who_name}</span>
              {p.died_on && <span> · died {dmy(p.died_on)}</span>}
              {keeper && (
                <span className="small">
                  <br />
                  {p.injury || "Injury not recorded"}
                  {p.treatment_name ? `; ${p.treatment_name.toLowerCase()}` : ""}
                  {p.off_work_from &&
                    ` · off work from ${dmy(p.off_work_from)}${p.back_at_work_on ? ` to ${dmy(p.back_at_work_on)}` : ", not back yet"} (${p.days_off} days)`}
                  {p.nis_form_on && ` · NIS notice of accident given ${dmy(p.nis_form_on)}`}
                </span>
              )}
              {keeper && <PersonUpdate incident={incident} person={p} onDone={done("Saved.")} />}
            </li>
          ))}
        </ul>
      )}
      {!keeper && incident.people.length > 0 && <p className="muted small">What an injury was is read only by Human Resources.</p>}
      {keeper && open && <AddPerson incident={incident} staff={staff} onDone={done("Recorded.")} />}

      <h3>Investigation</h3>
      {incident.cause ? (
        <p>
          {incident.cause}
          {incident.investigated_on && (
            <span className="muted small">
              {" "}
              Found {dmy(incident.investigated_on)}
              {incident.investigated_by ? ` by ${incident.investigated_by}` : ""}.
            </span>
          )}
        </p>
      ) : (
        <p className="muted">Not recorded yet.</p>
      )}
      {keeper && open && (
        <ActionForm
          label="Record what the investigation found"
          path={`${base}/investigation/`}
          fields={() => ({ cause, investigated_on: investigatedOn })}
          onDone={done("The investigation is recorded.")}
        >
          <label>
            Why it happened
            <textarea rows={3} value={cause} onChange={(e) => setCause(e.target.value)} required />
          </label>
          <label>
            Found on
            <input type="date" value={investigatedOn} onChange={(e) => setInvestigatedOn(e.target.value)} required />
          </label>
        </ActionForm>
      )}

      <h3>Actions, so it does not happen again</h3>
      {incident.actions.length === 0 ? (
        <p className="muted">None given yet.</p>
      ) : (
        <ul className="plain stack" aria-label="Actions">
          {incident.actions.map((a) => (
            <li key={a.id}>
              {a.what} <span className="muted small">{a.owner_name}, by {dmy(a.due_on)}</span>
              {a.done_on ? (
                <span className="small">
                  {" "}
                  · done {dmy(a.done_on)}
                  {a.done_note ? `: ${a.done_note}` : ""}
                </span>
              ) : (
                a.overdue && (
                  <>
                    {" "}
                    <span className="chip chip-rejected">Late</span>
                  </>
                )
              )}
              {keeper && open && !a.done_on && <MarkDone id={a.id} what={a.what} onDone={refresh} />}
            </li>
          ))}
        </ul>
      )}
      {keeper && open && (
        <ActionForm
          label="Give someone an action"
          path={`${base}/actions/`}
          fields={() => ({ what, owner: Number(owner), due_on: dueOn })}
          onDone={(fresh) => {
            setWhat("");
            done("The action is given. They are told.")(fresh);
          }}
        >
          <label>
            What will be done
            <textarea rows={2} value={what} onChange={(e) => setWhat(e.target.value)} required />
          </label>
          <div className="grid2">
            <label>
              By whom
              <select value={owner} onChange={(e) => setOwner(e.target.value)} required>
                <option value="">Choose</option>
                {staff.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              By when
              <input type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} required />
            </label>
          </div>
        </ActionForm>
      )}

      {open && incident.outstanding.length > 0 && (
        <>
          <h3>Left to do</h3>
          <ul aria-label="Left to do">
            {incident.outstanding.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
      {open ? (
        keeper && (
          <div className="actions">
            <button className="secondary" onClick={close}>
              Close the incident
            </button>
          </div>
        )
      ) : (
        <p className="muted">
          Closed {dmy(incident.closed_on)}
          {incident.closed_by ? ` by ${incident.closed_by}` : ""}.
          {keeper && " Recording a death or a return to work opens it again."}
        </p>
      )}
    </section>
  );
}
