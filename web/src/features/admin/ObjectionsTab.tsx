import { useCallback, useEffect, useState, type FormEvent } from "react";
import { getAll, plainMessage, post } from "../../api/client";
import {
  OFFICER_ROLES,
  RESTRICTION_WRITE_ROLES,
  hasAnyRole,
  type Employee,
  type Me,
  type Objection,
  type RecordRestriction,
} from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

const PARTS: [string, string][] = [
  ["personal", "Personal details"],
  ["contact", "Contact details"],
  ["emergency", "Emergency contacts"],
  ["dependants", "Dependants"],
  ["qualifications", "Qualifications"],
  ["previous", "Work before GSA"],
  ["bank", "Bank details"],
  ["appointment", "Appointment or contract"],
  ["leave", "Leave records"],
  ["other", "Something else"],
];
const GROUNDS: [string, string][] = [
  ["unlawful", "Its processing is unlawful"],
  ["legal_claim", "Kept only for the person's legal claim"],
  ["contested", "Its accuracy is contested"],
];

function Decide({ objection, onDone }: { objection: Objection; onDone: () => void }) {
  const [outcome, setOutcome] = useState("upheld");
  const [reasons, setReasons] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post(`/privacy/objections/${objection.id}/decide/`, { outcome, reasons });
      onDone();
    } catch (err) {
      setError(plainMessage(err, "The decision was not recorded."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={send} aria-label={`Decide the objection of ${objection.employee_name}`}>
      <div className="grid2">
        <label>
          Decision
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="upheld">Upheld: that use stops</option>
            <option value="not_upheld">Not upheld: compelling grounds, or a legal claim</option>
          </select>
        </label>
      </div>
      <label>
        Reasons <span className="muted small">(the person is told them)</span>
        <textarea rows={2} value={reasons} onChange={(e) => setReasons(e.target.value)} required />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Record the decision</button>
      </div>
    </form>
  );
}

function Lift({ restriction, onDone }: { restriction: RecordRestriction; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post(`/privacy/restrictions/${restriction.id}/lift/`, { reason });
      onDone();
    } catch (err) {
      setError(plainMessage(err, "The restriction was not lifted."));
    }
  }

  return (
    <form className="inline-form" onSubmit={send} aria-label={`Lift the restriction on ${restriction.part_name} for ${restriction.employee_name}`}>
      <label>
        Why it is lifted <span className="muted small">(the person is told)</span>
        <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={1000} />
      </label>
      <button type="submit" className="secondary">
        Lift it
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}

function Restrict({ onDone }: { onDone: (message: string) => void }) {
  const [staff, setStaff] = useState<Employee[]>([]);
  const [employee, setEmployee] = useState("");
  const [part, setPart] = useState("bank");
  const [ground, setGround] = useState("unlawful");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAll<Employee>("/employees/?status=active")
      .then(setStaff)
      .catch(() => setStaff([]));
  }, []);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const made = await post<RecordRestriction>("/privacy/restrictions/", { employee: Number(employee), part, ground, note });
      setNote("");
      onDone(`${made.part_name} in the record of ${made.employee_name} is restricted. They are told.`);
    } catch (err) {
      setError(plainMessage(err, "Nothing was restricted."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={send} aria-label="Restrict part of a record">
      <div className="grid2">
        <label>
          Whose record
          <select value={employee} onChange={(e) => setEmployee(e.target.value)} required>
            <option value="">Choose</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name} ({s.employee_no})
              </option>
            ))}
          </select>
        </label>
        <label>
          Which part
          <select value={part} onChange={(e) => setPart(e.target.value)}>
            {PARTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Why
          <select value={ground} onChange={(e) => setGround(e.target.value)}>
            {GROUNDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Note
        <input value={note} onChange={(e) => setNote(e.target.value)} required maxLength={1000} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Restrict it</button>
      </div>
    </form>
  );
}

/**
 * Objections and restrictions (item 1.46). The data protection officer decides objections; the officer and HR
 * restrict part of a record for a legal reason, and lift a restriction with the reason the person is told.
 */
export function ObjectionsTab({ me }: { me: Me }) {
  const [objections, setObjections] = useState<Objection[] | null>(null);
  const [held, setHeld] = useState<RecordRestriction[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const officer = hasAnyRole(me, OFFICER_ROLES);
  const restricts = hasAnyRole(me, RESTRICTION_WRITE_ROLES);

  const load = useCallback(() => {
    getAll<Objection>("/privacy/objections/")
      .then(setObjections)
      .catch((err) => setError(plainMessage(err, "Could not load the objections.")));
    getAll<RecordRestriction>("/privacy/restrictions/?in_force=1")
      .then(setHeld)
      .catch(() => setHeld([]));
  }, []);
  useEffect(load, [load]);

  const done = (message: string) => () => {
    setNotice(message);
    load();
  };

  return (
    <section className="stack" aria-labelledby="objections-heading">
      <h2 id="objections-heading">Objections</h2>
      <p className="muted">
        People may object in writing to how part of their record is used. That part is held back until the data
        protection officer decides. An objection stands unless GSA shows compelling legitimate grounds that override
        the person&apos;s interests, or needs the data for a legal claim.
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
      {objections !== null && objections.length === 0 && <p className="muted">No objections.</p>}
      <ul className="plain stack" aria-label="Objections">
        {(objections ?? []).map((o) => (
          <li key={o.id} className="card-block">
            <p>
              <strong>{o.employee_name}</strong> <span className="muted small">{o.employee_no}</span>, about{" "}
              {o.part_name.toLowerCase()} <span className="chip">{o.state_name}</span>
              {o.overdue && (
                <>
                  {" "}
                  <span className="chip chip-rejected">Late</span>
                </>
              )}
            </p>
            <p className="small">{o.grounds}</p>
            <p className="muted small">
              Made {dmyTime(o.created_at)}
              {o.state === "open"
                ? ` · decide by ${dmy(o.due_by)}`
                : ` · decided by ${o.decided_by_name ?? "the officer"}: ${o.reasons}`}
            </p>
            {officer && o.state === "open" && !o.is_mine && <Decide objection={o} onDone={done("The decision is recorded. The person is told.")} />}
          </li>
        ))}
      </ul>

      <h2>Restrictions in force</h2>
      {held.length === 0 ? (
        <p className="muted">No part of any record is held back.</p>
      ) : (
        <ul className="plain stack" aria-label="Restrictions in force">
          {held.map((r) => (
            <li key={r.id}>
              <strong>{r.employee_name}</strong>: {r.part_name.toLowerCase()} <span className="muted small">({r.ground_name.toLowerCase()}, since {dmy(r.created_at)})</span>
              {r.note && <span className="small"> · {r.note}</span>}
              {restricts && r.ground !== "objection" && <Lift restriction={r} onDone={done("Lifted. The person is told why.")} />}
            </li>
          ))}
        </ul>
      )}
      {restricts && <Restrict onDone={(message) => done(message)()} />}
    </section>
  );
}
