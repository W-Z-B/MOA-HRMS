import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, get, post } from "../../api/client";
import type { LeaveBalance, LeaveRequest, LeaveType, Me, Paginated } from "../../api/types";
import { enqueueLeave, flush, isNetworkError, pendingCount, subscribe } from "../../app/offlineQueue";

interface Props {
  me: Me;
  focusId: number | null;
}

type Tab = "mine" | "approvals" | "balances";

const STATE_LABEL: Record<string, string> = {
  draft: "Draft",
  submitted: "Submitted",
  supervisor_approved: "Supervisor approved",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

/** Wireframe 3: my requests with a new-request form, an approvals inbox, and ledger balances. */
export function LeaveScreen({ me, focusId }: Props) {
  const [tab, setTab] = useState<Tab>(focusId ? "approvals" : "mine");
  const [mine, setMine] = useState<LeaveRequest[]>([]);
  const [queue, setQueue] = useState<LeaveRequest[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});
  const [pending, setPending] = useState<number>(pendingCount);

  useEffect(() => subscribe(() => setPending(pendingCount())), []);

  const load = useCallback(() => {
    const own = me.employee_id ? get<Paginated<LeaveRequest>>(`/leave/requests/?employee=${me.employee_id}`) : null;
    Promise.all([
      own,
      get<Paginated<LeaveRequest>>("/leave/requests/?state=submitted"),
      get<Paginated<LeaveRequest>>("/leave/requests/?state=supervisor_approved"),
      me.employee_id ? get<{ balances: LeaveBalance[] }>("/leave/ledger/balances/") : null,
      get<Paginated<LeaveType>>("/leave/types/"),
    ])
      .then(([ownRes, submitted, supApproved, bal, typesRes]) => {
        setMine(ownRes?.results ?? []);
        const pending = [...submitted.results, ...supApproved.results].filter(
          (r) => r.allowed_actions.includes("approve") || r.allowed_actions.includes("reject"),
        );
        setQueue(pending);
        setBalances(bal?.balances ?? []);
        setTypes(typesRes.results);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Could not load leave data."));
  }, [me.employee_id]);

  useEffect(load, [load]);

  async function transition(id: number, action: string) {
    try {
      await post(`/leave/requests/${id}/transition/`, { action, comment: comments[id] ?? "" });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Action failed.");
    }
  }

  return (
    <>
      <h1>Leave</h1>
      <div className="tabs" role="tablist">
        {(["mine", "approvals", "balances"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>
            {t === "mine" ? "My requests" : t === "approvals" ? `Approvals (${queue.length})` : "Balances"}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {tab === "mine" && (
        <>
          {pending > 0 && (
            <p role="status" className="notice">
              {pending} request{pending === 1 ? "" : "s"} saved on this device, waiting for a connection.{" "}
              <button className="link" onClick={() => flush().then(load)}>
                Try sending now
              </button>
            </p>
          )}
          {me.employee_id ? (
            <NewRequestForm employeeId={me.employee_id} types={types} onCreated={load} />
          ) : (
            <p className="muted">Your account is not linked to an employee record, so you cannot request leave here.</p>
          )}
          <RequestTable rows={mine} onAction={transition} comments={comments} setComments={setComments} focusId={focusId} />
        </>
      )}
      {tab === "approvals" && (
        <RequestTable rows={queue} onAction={transition} comments={comments} setComments={setComments} focusId={focusId} showEmployee />
      )}
      {tab === "balances" && (
        <table>
          <thead>
            <tr>
              <th>Leave type</th>
              <th className="num">Balance (days)</th>
            </tr>
          </thead>
          <tbody>
            {balances.length === 0 ? (
              <tr>
                <td colSpan={2} className="muted">
                  No ledger entries yet.
                </td>
              </tr>
            ) : (
              balances.map((b) => (
                <tr key={b.leave_type}>
                  <td>{b.name}</td>
                  <td className="num">{b.balance}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}
    </>
  );
}

function NewRequestForm({ employeeId, types, onCreated }: { employeeId: number; types: LeaveType[]; onCreated: () => void }) {
  const [leaveType, setLeaveType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent, andSubmit: boolean) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const payload = { employee: employeeId, leave_type: Number(leaveType), from_date: from, to_date: to, reason };
    try {
      const created = await post<LeaveRequest>("/leave/requests/", payload);
      if (andSubmit) await post(`/leave/requests/${created.id}/transition/`, { action: "submit" });
      setFrom("");
      setTo("");
      setReason("");
      onCreated();
    } catch (err) {
      if (err instanceof ApiError) {
        const fieldMsg = err.fields ? Object.values(err.fields).flat()[0] : undefined;
        setError(fieldMsg ?? err.detail);
      } else if (isNetworkError(err)) {
        enqueueLeave(payload, andSubmit);
        setFrom("");
        setTo("");
        setReason("");
        setNotice("No connection. The request is saved on this device and will be sent when the network returns.");
      } else setError("Could not save the request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form-row" onSubmit={(e) => submit(e, true)}>
      <label>
        Leave type
        <select id="leave-type" value={leaveType} onChange={(e) => setLeaveType(e.target.value)} required>
          <option value="">Choose</option>
          {types.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        From
        <input id="leave-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} required />
      </label>
      <label>
        To
        <input id="leave-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} required />
      </label>
      <label className="grow">
        Reason
        <input id="leave-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" disabled={busy} onClick={(e) => submit(e, false)}>
          Save draft
        </button>
        <button type="submit" disabled={busy}>
          Submit request
        </button>
      </div>
    </form>
  );
}

function RequestTable({
  rows,
  onAction,
  comments,
  setComments,
  focusId,
  showEmployee = false,
}: {
  rows: LeaveRequest[];
  onAction: (id: number, action: string) => void;
  comments: Record<number, string>;
  setComments: (c: Record<number, string>) => void;
  focusId: number | null;
  showEmployee?: boolean;
}) {
  if (rows.length === 0) return <p className="muted">No requests.</p>;
  return (
    <table>
      <thead>
        <tr>
          {showEmployee && <th>Employee</th>}
          <th>Type</th>
          <th>From</th>
          <th>To</th>
          <th className="num">Days</th>
          <th>Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className={r.id === focusId ? "selected" : ""}>
            {showEmployee && <td>{r.employee_name}</td>}
            <td>{r.leave_type_code}</td>
            <td>{r.from_date}</td>
            <td>{r.to_date}</td>
            <td className="num">{r.days}</td>
            <td>
              {STATE_LABEL[r.state] ?? r.state}
              {r.decision_comment && <span className="muted small"> {r.decision_comment}</span>}
            </td>
            <td className="actions">
              {r.allowed_actions.includes("reject") && (
                <input
                  aria-label="Rejection comment"
                  placeholder="Comment (required to reject)"
                  value={comments[r.id] ?? ""}
                  onChange={(e) => setComments({ ...comments, [r.id]: e.target.value })}
                />
              )}
              {r.allowed_actions.map((a) => (
                <button key={a} className={a === "reject" || a === "cancel" ? "secondary" : ""} onClick={() => onAction(r.id, a)}>
                  {a}
                </button>
              ))}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
