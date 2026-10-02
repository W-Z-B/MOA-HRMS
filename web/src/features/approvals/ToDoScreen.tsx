import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, get, post } from "../../api/client";
import { isOfficeUser, type Delegation, type Employee, type Me, type WaitingItem } from "../../api/types";
import { dmy } from "../../app/format";

function StandIns({ me }: { me: Me }) {
  const [delegations, setDelegations] = useState<Delegation[] | null>(null);
  const [staff, setStaff] = useState<Employee[]>([]);
  const [open, setOpen] = useState(false);
  const [delegate, setDelegate] = useState("");
  const [starts, setStarts] = useState("");
  const [ends, setEnds] = useState("");
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getAll<Delegation>("/approvals/delegations/")
      .then(setDelegations)
      .catch(() => setDelegations([]));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (!open) return;
    getAll<Employee>("/employees/?has_account=1&status=active")
      .then((all) => setStaff(all.filter((e) => e.id !== me.employee_id)))
      .catch(() => setStaff([]));
  }, [open, me.employee_id]);

  async function name(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const made = await post<Delegation>("/approvals/delegations/", { delegate: Number(delegate), starts, ends, reason });
      setOpen(false);
      setDelegate("");
      setReason("");
      setNotice(`${made.delegate_name} stands in for you from ${dmy(made.starts)} to ${dmy(made.ends)}, and is told.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "The stand-in was not named."));
    }
  }

  async function end(d: Delegation) {
    setError(null);
    try {
      await post(`/approvals/delegations/${d.id}/end/`);
      setNotice(`${d.delegate_name} no longer stands in for you.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "That did not work."));
    }
  }

  const mine = (delegations ?? []).filter((d) => d.delegator === me.employee_id && !d.cancelled);
  const held = (delegations ?? []).filter((d) => d.delegate === me.employee_id && d.in_force);

  return (
    <section className="card-block stack" aria-labelledby="stand-ins-heading">
      <h2 id="stand-ins-heading">While you are away</h2>
      <p className="muted small">
        Name a colleague to decide what is sent to you while you are away: they see it under To do, and are told.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {mine.length > 0 && (
        <ul className="plain" aria-label="Your stand-ins">
          {mine.map((d) => (
            <li key={d.id}>
              {d.delegate_name}, {dmy(d.starts)} to {dmy(d.ends)}
              {d.reason ? ` (${d.reason})` : ""} {d.in_force && <span className="chip chip-step-done">In force</span>}{" "}
              <button className="link" onClick={() => end(d)} aria-label={`End ${d.delegate_name} standing in`}>
                End it
              </button>
            </li>
          ))}
        </ul>
      )}
      {held.length > 0 && (
        <p>You stand in for {held.map((d) => `${d.delegator_name} until ${dmy(d.ends)}`).join(", ")}.</p>
      )}
      {!open ? (
        <div className="actions">
          <button className="secondary" onClick={() => setOpen(true)}>
            Name a stand-in
          </button>
        </div>
      ) : (
        <form className="stack sub-form" onSubmit={name} aria-label="Name a stand-in">
          <div className="grid2">
            <label>
              Who
              <select value={delegate} onChange={(e) => setDelegate(e.target.value)} required>
                <option value="">Choose</option>
                {staff.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Why (optional)
              <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={160} placeholder="Annual leave" />
            </label>
            <label>
              From
              <input type="date" value={starts} onChange={(e) => setStarts(e.target.value)} required />
            </label>
            <label>
              Until
              <input type="date" value={ends} onChange={(e) => setEnds(e.target.value)} required />
            </label>
          </div>
          <div className="actions">
            <button type="submit">Name the stand-in</button>
            <button type="button" className="link" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

/** Everything waiting for my decision, from every module, oldest first (item 1.33), and my stand-ins. */
export function ToDoScreen({ me, onNavigate }: { me: Me; onNavigate: (to: string) => void }) {
  const [items, setItems] = useState<WaitingItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<WaitingItem[]>("/approvals/waiting/")
      .then(setItems)
      .catch((err) => setError(errorMessage(err, "Could not load what is waiting for you.")));
  }, []);

  return (
    <>
      <h1>To do</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {items === null && !error && <p className="loading">Loading…</p>}
      {items !== null && items.length === 0 && <p className="muted">Nothing is waiting for you.</p>}
      {items !== null && items.length > 0 && (
        <ul className="plain accounts" aria-label="Waiting for you">
          {items.map((item) => (
            <li key={`${item.kind}:${item.link}:${item.title}`} className={item.overdue ? "career-blocked" : undefined}>
              <div>
                <span className="chip">{item.kind_name}</span> <strong>{item.title}</strong>
                <br />
                <span className="muted small">
                  Waiting since {dmy(item.since)}
                  {item.waited_days > 0 ? `, ${item.waited_days} working ${item.waited_days === 1 ? "day" : "days"}` : ""}
                  {item.for_whom ? ` · ${item.for_whom}` : ""}
                </span>
                {item.overdue && <span className="chip chip-career-blocked"> Past its time limit</span>}
              </div>
              <div className="actions">
                <button className="link" onClick={() => onNavigate(item.link)} aria-label={`Open: ${item.title}`}>
                  Open it
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {isOfficeUser(me) && me.employee_id !== null && <StandIns me={me} />}
    </>
  );
}
