import { useState, type FormEvent, type ReactNode } from "react";
import { plainMessage, post } from "../../api/client";
import type { LeaveRequest } from "../../api/types";
import { initials, inDays } from "../../app/format";
import { after, dates } from "./leave";

interface RowProps {
  request: LeaveRequest;
  /** "decide": approve or reject now. "stop": still with a manager, but HR may reject it. "watch": only shown. */
  mode: "decide" | "stop" | "watch";
  onDecided: (request: LeaveRequest, outcome: string) => void;
  /** A line above the request, such as how long it has waited. */
  meta?: ReactNode;
}

/**
 * One leave request with its decision in place (item 2.30): Approve at once, or Reject with the reason the
 * employee will see. The server checks every decision; this only offers what it would accept.
 */
export function DecisionRow({ request: r, mode, onDecided, meta }: RowProps) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ text: string; rejected: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const first = r.employee_name.split(" ")[0];
  const what = `${r.leave_type_name.toLowerCase()} for ${r.employee_name}`;
  const left = after(r);

  async function decide(action: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      const moved = await post<LeaveRequest>(`/leave/requests/${r.id}/transition/`, {
        action,
        comment: action === "reject" ? reason.trim() : "",
      });
      const text =
        action === "reject"
          ? `Rejected. ${first} has been told why.`
          : moved.state === "approved"
            ? `Approved. ${first} has been sent a receipt.`
            : "Approved. It is now with Human Resources.";
      setDone({ text, rejected: action === "reject" });
      onDecided(r, text);
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    } finally {
      setBusy(false);
    }
  }

  function reject(e: FormEvent) {
    e.preventDefault();
    if (reason.trim()) decide("reject");
  }

  return (
    <li className="decision">
      {meta && <div className="decision-meta">{meta}</div>}
      <div className="decision-who">
        <span className="initials" aria-hidden="true">
          {initials(r.employee_name)}
        </span>
        <span className="stacked">
          <span className="strong">{r.employee_name}</span>
          <span className="muted small">
            {r.leave_type_name}
            {r.reason ? ` · ${r.reason}` : ""}
          </span>
        </span>
      </div>
      <div className="decision-when stacked">
        <span className="num">{dates(r)}</span>
        <span className="muted small">
          <strong className="ink">{inDays(r.days)}</strong>
          {left ? ` · ${left}` : ""}
        </span>
      </div>
      <div className="decision-actions">
        {done ? (
          <span role="status" className={done.rejected ? "chip chip-rejected" : "chip chip-approved"}>
            {done.text}
          </span>
        ) : (
          <>
            {mode !== "decide" && <span className="chip chip-waiting">With {r.manager_name ?? "the campus supervisors"}</span>}
            {mode === "decide" && !rejecting && (
              <>
                <button className="secondary" disabled={busy} onClick={() => setRejecting(true)} aria-label={`Reject ${what}`}>
                  Reject
                </button>
                <button disabled={busy} onClick={() => decide("approve")} aria-label={`Approve ${what}`}>
                  Approve
                </button>
              </>
            )}
            {mode === "stop" && !rejecting && (
              <button className="secondary danger-text" disabled={busy} onClick={() => setRejecting(true)} aria-label={`Stop ${what}`}>
                Stop it
              </button>
            )}
          </>
        )}
      </div>
      {rejecting && !done && (
        <form className="reject-form" onSubmit={reject} aria-label={`Reject ${what}`}>
          <label>
            Reason for {mode === "stop" ? "stopping it" : "rejecting"}. {first} will see it.
            <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} autoFocus />
          </label>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setRejecting(false)}>
              Back
            </button>
            <button type="submit" className="danger" disabled={busy || !reason.trim()}>
              Reject request
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="error decision-error">
          {error}
        </p>
      )}
    </li>
  );
}
