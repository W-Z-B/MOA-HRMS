import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, get, post } from "../../api/client";
import {
  isOfficeUser,
  type Delegation,
  type Employee,
  type LeaveRequest,
  type Me,
  type WaitingItem,
} from "../../api/types";
import { dmy, initials } from "../../app/format";
import { useFrame } from "../../app/frame";
import { DecisionRow } from "../home/decisions";
import { useLeaveToDecide } from "../home/leave";

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
    <section className="panel-card padded stack" aria-labelledby="stand-ins-heading">
      <div className="stacked">
        <h2 id="stand-ins-heading">While you are away</h2>
        <p className="muted small">
          Name a colleague to decide what is sent to you while you are away: they see it under To do, and are told.
          Each decision records who made it.
        </p>
      </div>
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

/** "Waiting since 01/10/2026, 4 working days · standing in for Michael Thomas" */
function waited(item: WaitingItem): string {
  const days = item.waited_days > 0 ? `, ${item.waited_days} working ${item.waited_days === 1 ? "day" : "days"}` : "";
  return `Waiting since ${dmy(item.since)}${days}${item.for_whom ? ` · ${item.for_whom}` : ""}`;
}

/** The request a leave item links to, as /leave/requests/12. */
const leaveId = (item: WaitingItem) => Number(item.link.match(/^\/leave\/requests\/(\d+)$/)?.[1] ?? 0);

/**
 * Everything waiting for my decision, from every module, oldest first (item 1.33). Leave is decided in place
 * (item 2.30); everything else opens where it is decided. HR also sees leave still with a manager, which it
 * may stop. Beside the list: my stand-ins, and what I decided here today.
 */
export function ToDoScreen({ me, onNavigate }: { me: Me; onNavigate: (to: string) => void }) {
  const frame = useFrame();
  const [items, setItems] = useState<WaitingItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [today, setToday] = useState<{ label: string; outcome: string }[]>([]);
  const decides = isOfficeUser(me);
  const leave = useLeaveToDecide(decides);
  const delegates = decides && me.employee_id !== null;

  useEffect(() => {
    get<WaitingItem[]>("/approvals/waiting/")
      .then(setItems)
      .catch((err) => setError(errorMessage(err, "Could not load what is waiting for you.")));
  }, []);

  function decided(request: LeaveRequest, outcome: string) {
    setToday((list) => [{ label: `${request.employee_name}, ${request.leave_type_name.toLowerCase()}`, outcome }, ...list]);
    frame.decided();
  }

  const byId = new Map((leave.toDecide ?? []).map((r) => [r.id, r]));
  const waiting = items?.length ?? 0;

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>To do</h1>
          {items !== null && (
            <p className="muted lead">
              {waiting === 0
                ? "Nothing is waiting for you."
                : `${waiting} ${waiting === 1 ? "decision waits" : "decisions wait"} for you, oldest first.`}
            </p>
          )}
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {items === null && !error && <p className="loading">Loading…</p>}
      <div className="home-columns">
        <div className="home-main">
          {items !== null && items.length === 0 && (
            <section className="panel-card padded">
              <h2>Nothing is waiting for you</h2>
              <p className="muted">When something needs your answer, such as a letter to sign, it appears here and on Home.</p>
            </section>
          )}
          {items !== null && items.length > 0 && (
            <section className="panel-card">
              <ul className="rows decisions" aria-label="Waiting for you">
                {items.map((item) => {
                  const meta = (
                    <>
                      <span className="todo-kind">{item.kind_name}</span>{" "}
                      <span className={item.overdue ? "todo-since late" : "todo-since"}>{waited(item)}</span>
                      {item.overdue && <span className="chip chip-career-blocked"> Past its time limit</span>}
                    </>
                  );
                  const request = byId.get(leaveId(item));
                  if (request)
                    return (
                      <DecisionRow
                        key={`${item.kind}:${item.link}`}
                        request={request}
                        mode="decide"
                        onDecided={decided}
                        meta={meta}
                      />
                    );
                  return (
                    <li key={`${item.kind}:${item.link}:${item.title}`} className={item.overdue ? "todo-item overdue" : "todo-item"}>
                      <div className="decision-meta">{meta}</div>
                      <div className="todo-body">
                        <span className="initials" aria-hidden="true">
                          {initials(item.title.split(":")[0])}
                        </span>
                        <span className="strong grow">{item.title}</span>
                        <button onClick={() => onNavigate(item.link)} aria-label={`Open: ${item.title}`}>
                          Open it
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
          {leave.elsewhere.length > 0 && (
            <section className="panel-card" aria-labelledby="elsewhere-heading">
              <div className="panel-card-head stacked">
                <h2 id="elsewhere-heading">Still with a manager</h2>
                <span className="muted small">Not yours to approve yet, but Human Resources can still stop it.</span>
              </div>
              <ul className="rows decisions">
                {leave.elsewhere.map((r) => (
                  <DecisionRow key={r.id} request={r} mode="stop" onDecided={decided} />
                ))}
              </ul>
            </section>
          )}
        </div>
        {(delegates || today.length > 0) && (
          <div className="home-side">
            {delegates && <StandIns me={me} />}
            {today.length > 0 && (
              <section className="panel-card" aria-labelledby="decided-heading">
                <div className="panel-card-head">
                  <h2 id="decided-heading">Decided today</h2>
                </div>
                <ul className="rows">
                  {today.map((d, at) => (
                    <li key={at} className="stacked">
                      <span className="strong">{d.label}</span>
                      <span className="muted small">{d.outcome}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
      </div>
    </>
  );
}
