import { useState } from "react";
import type { LeaveRequest } from "../../api/types";
import { dmy, dmyTime, inDays, num } from "../../app/format";

interface Props {
  request: LeaveRequest;
  /** "mine": the employee's own request. "decide": in the approver's list. */
  view: "mine" | "decide";
  canOpenNote: boolean;
  highlighted: boolean;
  onAction: (request: LeaveRequest, action: string, comment: string) => Promise<void>;
  onAttach: (request: LeaveRequest, file: File) => Promise<void>;
  onReceipt: (request: LeaveRequest) => void;
}

const STATUS: Record<string, string> = {
  draft: "Draft, not sent",
  submitted: "With the manager",
  supervisor_approved: "With Human Resources",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

const ACTION: Record<string, string> = {
  submit: "Send request",
  approve: "Approve",
  reject: "Reject",
  cancel: "Cancel request",
};

type Mark = "done" | "current" | "stopped" | "todo";

/** Sent, manager, Human Resources: where the request is and who has decided. */
function steps(r: LeaveRequest): { label: string; mark: Mark; detail: string }[] {
  const decided = (step: "manager" | "hr") => r.decisions.find((d) => d.step === step);
  const mark = (step: "manager" | "hr", waitingIn: string): Mark => {
    const decision = decided(step);
    if (decision) return decision.outcome === "approved" ? "done" : "stopped";
    return r.state === waitingIn ? "current" : "todo";
  };
  const detail = (step: "manager" | "hr", fallback: string) => {
    const decision = decided(step);
    return decision ? `${decision.actor_name}, ${dmyTime(decision.decided_at)}` : fallback;
  };
  return [
    { label: "Sent", mark: r.state === "draft" ? "todo" : "done", detail: "" },
    {
      label: "Manager",
      mark: mark("manager", "submitted"),
      detail: detail("manager", r.state === "draft" ? "" : (r.manager_name ?? "Campus supervisors")),
    },
    { label: "Human Resources", mark: mark("hr", "supervisor_approved"), detail: detail("hr", "") },
  ];
}

/** One request as a card: readable on a phone, with the actions this person may take on it. */
export function RequestCard({ request: r, view, canOpenNote, highlighted, onAction, onAttach, onReceipt }: Props) {
  const [comment, setComment] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const open = ["draft", "submitted", "supervisor_approved"].includes(r.state);
  const noteName = r.evidence_name.toLowerCase();
  const missingNote = r.evidence_required && !r.has_evidence;

  async function run(work: () => Promise<void>) {
    setBusy(true);
    try {
      await work();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`request state-${r.state}${highlighted ? " highlighted" : ""}`} id={`request-${r.id}`}>
      <header>
        <div>
          {view === "decide" && <p className="who">{r.employee_name}</p>}
          <h3>{r.leave_type_name}</h3>
        </div>
        <span className={`chip chip-${r.state}`}>{STATUS[r.state] ?? r.state}</span>
      </header>
      <p className="when">
        {dmy(r.from_date)}
        {r.to_date !== r.from_date && ` to ${dmy(r.to_date)}`} · <strong>{inDays(r.days)}</strong>
      </p>
      {r.reason && <p className="muted">{r.reason}</p>}

      {r.state !== "cancelled" && (
        <ol className="steps">
          {steps(r).map((s) => (
            <li key={s.label} className={s.mark}>
              <span className="label">{s.label}</span>
              {s.detail && <span className="muted small">{s.detail}</span>}
            </li>
          ))}
        </ol>
      )}

      {r.state === "rejected" && r.decision_comment && (
        <p className="notice">
          <strong>Reason given:</strong> {r.decision_comment}
        </p>
      )}
      {open && r.balance_after !== null && view === "decide" && num(r.days_beyond) === 0 && (
        <p>
          Leaves {inDays(r.balance_after)} of {r.leave_type_name.toLowerCase()}.
        </p>
      )}
      {num(r.days_beyond) > 0 && (
        <p>
          {inDays(num(r.days) - num(r.days_beyond))} from the balance and{" "}
          <strong>{inDays(r.days_beyond)} beyond the entitlement</strong>
          {r.has_evidence ? `, supported by a ${noteName}.` : "."}
        </p>
      )}

      {r.has_evidence && (
        <p>
          <span className="tick" aria-hidden="true" /> {r.evidence_name} attached.{" "}
          {canOpenNote && <a href={`/api/v1/leave/requests/${r.id}/evidence/`}>Open</a>}
        </p>
      )}
      {view === "mine" && open && missingNote && (
        <div className="check">
          <p>
            <strong>A {noteName} is needed</strong> before this can be sent.
          </p>
          <label>
            {r.evidence_name} (photo or PDF)
            <input type="file" accept="image/*,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <div className="actions">
            <button disabled={busy || !file} onClick={() => file && run(() => onAttach(r, file))}>
              Attach
            </button>
          </div>
        </div>
      )}

      {rejecting && (
        <form
          className="reject-form"
          aria-label={`Reject ${r.leave_type_name.toLowerCase()} for ${r.employee_name}`}
          onSubmit={(e) => {
            e.preventDefault();
            if (comment.trim()) run(() => onAction(r, "reject", comment.trim()));
          }}
        >
          <label>
            Reason for rejecting. {r.employee_name.split(" ")[0]} will see it.
            <input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={300} autoFocus />
          </label>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setRejecting(false)}>
              Back
            </button>
            <button type="submit" className="danger" disabled={busy || !comment.trim()}>
              Reject request
            </button>
          </div>
        </form>
      )}
      <div className="actions">
        {r.allowed_actions
          .filter((action) => !(rejecting && action === "reject"))
          .map((action) => (
            <button
              key={action}
              className={action === "reject" || action === "cancel" ? "secondary" : ""}
              disabled={busy || (action === "submit" && missingNote)}
              onClick={() => (action === "reject" ? setRejecting(true) : run(() => onAction(r, action, comment)))}
            >
              {ACTION[action] ?? action}
            </button>
          ))}
        {r.receipt && (
          <button className="secondary" onClick={() => onReceipt(r)}>
            View receipt
          </button>
        )}
      </div>
    </article>
  );
}
