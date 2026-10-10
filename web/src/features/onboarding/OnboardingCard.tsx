import { useState } from "react";
import type { Onboarding, OnboardingStepCode } from "../../api/types";
import { dmy } from "../../app/format";

interface Props {
  record: Onboarding;
  onAction: (record: Onboarding, action: string, comment?: string) => Promise<void>;
  onClearStep: (record: Onboarding, code: OnboardingStepCode, done: boolean) => Promise<void>;
  onOpenAccount: (record: Onboarding) => Promise<void>;
}

const ACTION_LABEL: Record<string, string> = {
  submit_documents: "Documents received: submit for review",
  confirm_documents: "Confirm documents",
  send_back: "Send back for more",
  complete: "Complete onboarding",
  cancel: "Cancel onboarding",
};
const STATE_LABEL: Record<string, string> = {
  in_progress: "In progress",
  documents_submitted: "Documents submitted, awaiting HR",
  completed: "Completed",
  cancelled: "Cancelled",
};
const STATE_CLASS: Record<string, string> = {
  in_progress: "chip-waiting",
  documents_submitted: "chip-waiting",
  completed: "chip-approved",
  cancelled: "chip-rejected",
};
// These close or send back the record and are worth a word about why (same convention as leave and
// recruitment's own reject/withdraw actions).
const ASKS_FOR_A_COMMENT = new Set(["send_back", "cancel"]);

/** One onboarding (item H-W02): its new hire, its stage, the checklist, and the actions open to HR from
 * there (allowed_actions, computed server-side by people.onboarding_workflow). */
export function OnboardingCard({ record, onAction, onClearStep, onOpenAccount }: Props) {
  const [busy, setBusy] = useState(false);
  const [commentFor, setCommentFor] = useState<string | null>(null);
  const [comment, setComment] = useState("");

  async function act(action: string, withComment?: string) {
    setBusy(true);
    try {
      await onAction(record, action, withComment);
      setCommentFor(null);
      setComment("");
    } finally {
      setBusy(false);
    }
  }

  function click(action: string) {
    if (ASKS_FOR_A_COMMENT.has(action)) {
      setCommentFor(action);
      return;
    }
    act(action);
  }

  async function clear(code: OnboardingStepCode, done: boolean) {
    setBusy(true);
    try {
      await onClearStep(record, code, done);
    } finally {
      setBusy(false);
    }
  }

  async function openAccount() {
    setBusy(true);
    try {
      await onOpenAccount(record);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card-block stack" aria-label={record.employee_name}>
      <header className="spread">
        <span className="stacked">
          <strong>{record.employee_name}</strong>
          <span className="muted small">Started {dmy(record.started_on)}</span>
        </span>
        <span className={`chip ${STATE_CLASS[record.state] ?? ""}`}>{STATE_LABEL[record.state] ?? record.state}</span>
      </header>
      {record.decision_comment && <p className="muted small">Note: {record.decision_comment}</p>}
      <ul className="rows" aria-label="Checklist">
        {record.steps.map((step) => (
          <li key={step.id} className="item-row">
            <span className="stacked grow">
              <span>{step.label}</span>
              <span className="muted small">
                {step.who}
                {step.note && ` · ${step.note}`}
              </span>
            </span>
            <span className={`chip ${step.state === "done" ? "chip-approved" : step.state === "not_needed" ? "chip-rejected" : "chip-waiting"}`}>
              {step.state_name}
            </span>
            {step.state === "open" && step.code === "account" && (
              <button type="button" className="secondary small-button" disabled={busy} onClick={openAccount}>
                Open account
              </button>
            )}
            {step.state === "open" && (step.code === "equipment" || step.code === "induction") && (
              <>
                <button type="button" className="secondary small-button" disabled={busy} onClick={() => clear(step.code, true)}>
                  Mark done
                </button>
                <button type="button" className="secondary small-button" disabled={busy} onClick={() => clear(step.code, false)}>
                  Not needed
                </button>
              </>
            )}
            {step.state === "open" && (step.code === "documents" || step.code === "account") && (
              <button type="button" className="secondary small-button" disabled={busy} onClick={() => clear(step.code, false)}>
                Not needed
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="actions">
        {record.allowed_actions.map((action) => (
          <button key={action} className={action === "cancel" ? "secondary" : ""} disabled={busy} onClick={() => click(action)}>
            {ACTION_LABEL[action] ?? action}
          </button>
        ))}
      </div>
      {commentFor && (
        <form
          className="stack sub-form"
          onSubmit={(e) => {
            e.preventDefault();
            act(commentFor, comment);
          }}
        >
          <label>
            Why
            <input value={comment} onChange={(e) => setComment(e.target.value)} required autoFocus />
          </label>
          <div className="actions">
            <button type="submit" disabled={busy || !comment.trim()}>
              Confirm
            </button>
            <button type="button" className="secondary" onClick={() => setCommentFor(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </article>
  );
}
