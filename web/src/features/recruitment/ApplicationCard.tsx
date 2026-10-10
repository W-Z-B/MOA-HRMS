import { useState } from "react";
import type { Application } from "../../api/types";
import { dmy } from "../../app/format";
import { ScheduleInterviewForm } from "./ScheduleInterviewForm";

interface Props {
  application: Application;
  onAction: (application: Application, action: string, comment?: string) => Promise<void>;
  onScheduled: () => void;
}

const ACTION_LABEL: Record<string, string> = {
  shortlist: "Shortlist",
  mark_interviewed: "Mark interviewed",
  offer: "Make an offer",
  accept: "Candidate accepted",
  decline: "Candidate declined",
  reject: "Reject",
  withdraw: "Candidate withdrew",
};
const STATE_LABEL: Record<string, string> = {
  submitted: "Submitted",
  shortlisted: "Shortlisted",
  interview_scheduled: "Interview scheduled",
  interviewed: "Interviewed",
  offered: "Offered",
  accepted: "Accepted",
  declined: "Declined",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};
const STATE_CLASS: Record<string, string> = {
  submitted: "chip-draft",
  shortlisted: "chip-waiting",
  interview_scheduled: "chip-waiting",
  interviewed: "chip-waiting",
  offered: "chip-waiting",
  accepted: "chip-approved",
  declined: "chip-rejected",
  rejected: "chip-rejected",
  withdrawn: "chip-rejected",
};
// These close the application and are worth a word about why, same convention as leave.workflow's reject.
const ASKS_FOR_A_COMMENT = new Set(["reject", "withdraw"]);

/** One application: its candidate, its stage, and the actions open to HR from there (allowed_actions,
 * computed server-side by recruitment.workflow so this card never has to know the rules itself). */
export function ApplicationCard({ application, onAction, onScheduled }: Props) {
  const [busy, setBusy] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [commentFor, setCommentFor] = useState<string | null>(null);
  const [comment, setComment] = useState("");

  async function act(action: string, withComment?: string) {
    setBusy(true);
    try {
      await onAction(application, action, withComment);
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
    if (action === "schedule_interview") {
      setScheduling(true);
      return;
    }
    act(action);
  }

  const candidate = application.candidate;
  return (
    <article className="card-block stack" aria-label={candidate.full_name}>
      <header className="spread">
        <span className="stacked">
          <strong>{candidate.full_name}</strong>
          <span className="muted small">
            {candidate.email} {candidate.phone && `· ${candidate.phone}`}
          </span>
        </span>
        <span className={`chip ${STATE_CLASS[application.state] ?? ""}`}>
          {STATE_LABEL[application.state] ?? application.state}
        </span>
      </header>
      <p className="muted small">
        Reference {application.reference} · submitted {dmy(application.created_at)}
        {candidate.cv_filename && (
          <>
            {" · "}
            <span>CV: {candidate.cv_filename}</span>
          </>
        )}
      </p>
      {application.decision_comment && <p className="muted small">Note: {application.decision_comment}</p>}
      <div className="actions">
        {application.allowed_actions.map((action) => (
          <button
            key={action}
            className={action === "reject" || action === "decline" ? "secondary" : ""}
            disabled={busy}
            onClick={() => click(action)}
          >
            {action === "schedule_interview" ? "Schedule interview" : ACTION_LABEL[action] ?? action}
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
      {scheduling && (
        <ScheduleInterviewForm
          applicationId={application.id}
          onScheduled={() => {
            setScheduling(false);
            onScheduled();
          }}
          onCancel={() => setScheduling(false)}
        />
      )}
    </article>
  );
}
