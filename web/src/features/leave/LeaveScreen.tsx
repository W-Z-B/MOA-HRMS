import { useCallback, useEffect, useState } from "react";
import { get, plainMessage, post } from "../../api/client";
import {
  HR_ROLES,
  hasAnyRole,
  type LeaveBalance,
  type LeaveRequest,
  type LeaveType,
  type Me,
  type Paginated,
} from "../../api/types";
import { inDays, num } from "../../app/format";
import { flush, pendingCount, subscribe } from "../../app/offlineQueue";
import { Receipt } from "./Receipt";
import { RequestCard } from "./RequestCard";
import { RequestForm } from "./RequestForm";

interface Props {
  me: Me;
  focusId: number | null;
  /** Opened from Home's "Leave requests" or "All leave requests": the requests to decide come first. */
  deciding?: boolean;
  onNavigate: (to: string) => void;
}

type Tab = "mine" | "decide";

/**
 * Wireframe 3, laid out for a phone first: what I have left, a request form that checks as I type,
 * my requests with their progress, and the requests waiting for my decision.
 */
export function LeaveScreen({ me, focusId, deciding = false, onNavigate }: Props) {
  const [tab, setTab] = useState<Tab>(deciding ? "decide" : "mine");
  const [mine, setMine] = useState<LeaveRequest[]>([]);
  const [queue, setQueue] = useState<LeaveRequest[]>([]);
  const [elsewhere, setElsewhere] = useState<LeaveRequest[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [focused, setFocused] = useState<LeaveRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<number>(pendingCount);
  const isHr = hasAnyRole(me, HR_ROLES);

  useEffect(() => subscribe(() => setWaiting(pendingCount())), []);

  const load = useCallback(() => {
    const own = me.employee_id ? get<Paginated<LeaveRequest>>(`/leave/requests/?employee=${me.employee_id}`) : null;
    Promise.all([
      own,
      get<Paginated<LeaveRequest>>("/leave/requests/?state=submitted"),
      get<Paginated<LeaveRequest>>("/leave/requests/?state=supervisor_approved"),
      me.employee_id ? get<{ balances: LeaveBalance[] }>("/leave/ledger/balances/") : null,
      get<Paginated<LeaveType>>("/leave/types/"),
    ])
      .then(([ownRes, submitted, withHr, bal, typesRes]) => {
        setMine(ownRes?.results ?? []);
        const open = [...submitted.results, ...withHr.results].filter((r) => !r.is_mine);
        setQueue(open.filter((r) => r.allowed_actions.includes("approve")));
        // Not this person's turn, but theirs to stop: HR sees what is still with a manager.
        setElsewhere(
          open.filter((r) => !r.allowed_actions.includes("approve") && r.allowed_actions.includes("reject")),
        );
        setBalances(bal?.balances ?? []);
        setTypes(typesRes.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load leave data.")));
  }, [me.employee_id]);

  useEffect(load, [load]);

  // A link from a notification names one request: open its receipt, or the list it belongs in.
  useEffect(() => {
    if (!focusId) return; // a request opened earlier is ignored below once the link no longer names it
    let current = true;
    get<LeaveRequest>(`/leave/requests/${focusId}/`)
      .then((r) => {
        if (!current) return;
        setFocused(r);
        setTab(r.is_mine ? "mine" : "decide");
      })
      .catch(() => current && setFocused(null));
    return () => {
      current = false;
    };
  }, [focusId]);

  async function act(request: LeaveRequest, action: string, comment: string) {
    setNotice(null);
    try {
      const moved = await post<LeaveRequest>(`/leave/requests/${request.id}/transition/`, { action, comment });
      setError(null);
      if (action === "submit") setNotice(`Sent to ${moved.manager_name ?? "your campus supervisors"} for approval.`);
      if (action === "approve" && moved.state === "approved")
        setNotice(`Approved. ${moved.employee_name} has been sent a receipt.`);
      if (action === "approve" && moved.state !== "approved") setNotice("Approved. It is now with Human Resources.");
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    }
  }

  async function attach(request: LeaveRequest, file: File) {
    const body = new FormData();
    body.set("file", file);
    try {
      await post(`/leave/requests/${request.id}/evidence/`, body);
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "The file could not be attached."));
    }
  }

  if (focused?.receipt && focusId === focused.id)
    return <Receipt receipt={focused.receipt} onBack={() => onNavigate("/leave")} />;

  const canDecide = queue.length > 0 || hasAnyRole(me, ["supervisor", ...HR_ROLES]);
  const card = (r: LeaveRequest, view: Tab) => (
    <RequestCard
      key={r.id}
      request={r}
      view={view}
      canOpenNote={r.is_mine || isHr}
      highlighted={r.id === focusId}
      onAction={act}
      onAttach={attach}
      onReceipt={(request) => onNavigate(`/leave/requests/${request.id}`)}
    />
  );

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Leave</h1>
          <p className="muted lead">
            {canDecide
              ? "Your own leave, and requests from the people you approve."
              : "Days left, your requests and how far each one has gone."}
          </p>
        </div>
      </div>

      {canDecide && (
        <div className="tabs" role="tablist" aria-label="Leave">
          <button role="tab" aria-selected={tab === "mine"} className={tab === "mine" ? "tab active" : "tab"} onClick={() => setTab("mine")}>
            My leave
          </button>
          <button role="tab" aria-selected={tab === "decide"} className={tab === "decide" ? "tab active" : "tab"} onClick={() => setTab("decide")}>
            To decide ({queue.length})
          </button>
        </div>
      )}
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

      {(tab === "mine" || !canDecide) && (
        <>
          {waiting > 0 && (
            <p role="status" className="notice">
              {waiting} request{waiting === 1 ? "" : "s"} saved on this phone, waiting for a connection.{" "}
              <button
                className="link accent"
                onClick={() =>
                  flush().then((sent) => {
                    if (sent.drafts > 0) setNotice("Saved as a draft: attach the note it needs, then send it.");
                    load();
                  })
                }
              >
                Try sending now
              </button>
            </p>
          )}
          {balances.some((b) => b.limited) && (
            <section className="figures" aria-label="Days you have left">
              {balances
                .filter((b) => b.limited)
                .map((b) => (
                  <div className="figure" key={b.leave_type}>
                    <span className="figure-label">{b.name} left</span>
                    <span className="figure-value">{inDays(Math.max(num(b.available), 0))}</span>
                    <span className="figure-note">
                      {num(b.pending) > 0
                        ? `${inDays(b.pending)} awaiting a decision`
                        : `${inDays(b.entitlement)} a year · nothing awaiting a decision`}
                    </span>
                  </div>
                ))}
            </section>
          )}
          <div className="leave-columns">
            <div className="leave-form">
              {me.employee_id ? (
                <RequestForm
                  employeeId={me.employee_id}
                  types={types}
                  onSaved={(message) => {
                    setNotice(message);
                    load();
                  }}
                />
              ) : (
                <p className="panel-card padded muted">
                  Your account is not linked to an employee record, so you cannot ask for leave here.
                </p>
              )}
            </div>
            <section className="leave-mine" aria-labelledby="mine-heading">
              <h2 id="mine-heading">Your requests</h2>
              {mine.length === 0 ? (
                <p className="empty-note">You have not asked for leave this year.</p>
              ) : (
                mine.map((r) => card(r, "mine"))
              )}
            </section>
          </div>
        </>
      )}
      {tab === "decide" && canDecide && (
        <>
          {queue.length === 0 ? (
            <p className="panel-card padded">Nothing is waiting for your decision.</p>
          ) : (
            queue.map((r) => card(r, "decide"))
          )}
          {elsewhere.length > 0 && (
            <>
              <h2>Still with a manager</h2>
              {elsewhere.map((r) => card(r, "decide"))}
            </>
          )}
        </>
      )}
    </>
  );
}
