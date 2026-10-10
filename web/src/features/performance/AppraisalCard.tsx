import { useState, type FormEvent } from "react";
import type { Appraisal } from "../../api/types";

interface Props {
  appraisal: Appraisal;
  canSign: boolean;
  canSetGoals: boolean;
  onWriteSelfAssessment: (appraisal: Appraisal, text: string) => Promise<void>;
  onWriteManagerAssessment: (appraisal: Appraisal, text: string, rating: number, outcome: string) => Promise<void>;
  onAction: (appraisal: Appraisal, action: string, comment?: string) => Promise<void>;
  onAddGoal: (appraisal: Appraisal, title: string) => Promise<void>;
}

const STATE_LABEL: Record<string, string> = {
  draft: "Draft",
  self_assessed: "Self-assessment done",
  rated: "Rated",
  signed: "Signed off",
};
const STATE_CLASS: Record<string, string> = {
  draft: "chip-draft",
  self_assessed: "chip-waiting",
  rated: "chip-waiting",
  signed: "chip-approved",
};
const ACTION_LABEL: Record<string, string> = {
  rate: "Rate",
  sign_off: "Sign off",
  reopen: "Reopen",
};
const ASKS_FOR_A_COMMENT = new Set(["reopen"]);

/** One appraisal (item H-M03): its goals, its state, and the form open to whoever may act on it from
 * there (allowed_actions, computed server-side by performance.workflow). */
export function AppraisalCard({
  appraisal,
  canSign,
  canSetGoals,
  onWriteSelfAssessment,
  onWriteManagerAssessment,
  onAction,
  onAddGoal,
}: Props) {
  const [selfText, setSelfText] = useState(appraisal.self_assessment);
  const [managerText, setManagerText] = useState(appraisal.manager_assessment);
  const [rating, setRating] = useState(appraisal.overall_rating ?? 3);
  const [outcome, setOutcome] = useState(appraisal.outcome);
  const [commentFor, setCommentFor] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [newGoal, setNewGoal] = useState("");
  const [busy, setBusy] = useState(false);

  async function addGoal(e: FormEvent) {
    e.preventDefault();
    if (!newGoal.trim()) return;
    setBusy(true);
    try {
      await onAddGoal(appraisal, newGoal.trim());
      setNewGoal("");
    } finally {
      setBusy(false);
    }
  }

  async function saveSelf(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await onWriteSelfAssessment(appraisal, selfText);
    } finally {
      setBusy(false);
    }
  }

  async function saveManager(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await onWriteManagerAssessment(appraisal, managerText, rating, outcome);
    } finally {
      setBusy(false);
    }
  }

  async function act(action: string, withComment?: string) {
    setBusy(true);
    try {
      await onAction(appraisal, action, withComment);
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

  const canWriteSelf = appraisal.is_mine && appraisal.state === "draft";
  const canSubmitSelf = appraisal.is_mine && appraisal.allowed_actions.includes("submit_self_assessment");
  const canWriteManager = (appraisal.is_rated_by_me || canSign) && appraisal.state === "self_assessed";
  const canRate = (appraisal.is_rated_by_me || canSign) && appraisal.allowed_actions.includes("rate");
  const signActions = appraisal.allowed_actions.filter((a) => a === "sign_off" || a === "reopen");

  return (
    <article className="card-block stack" aria-label={appraisal.employee_name}>
      <header className="spread">
        <span className="stacked">
          <strong>{appraisal.employee_name}</strong>
          <span className="muted small">
            {appraisal.cycle_name} · {appraisal.kind_name}
            {appraisal.manager_name && ` · rated by ${appraisal.manager_name}`}
          </span>
        </span>
        <span className={`chip ${STATE_CLASS[appraisal.state] ?? ""}`}>{STATE_LABEL[appraisal.state] ?? appraisal.state}</span>
      </header>

      {appraisal.goals.length > 0 && (
        <ul className="rows" aria-label="Goals">
          {appraisal.goals.map((goal) => (
            <li key={goal.id} className="item-row">
              <span className="stacked grow">
                <span>{goal.title}</span>
                {goal.description && <span className="muted small">{goal.description}</span>}
              </span>
              {goal.weight !== null && <span className="muted small">{goal.weight}%</span>}
              <span className="chip">{goal.status_name}</span>
            </li>
          ))}
        </ul>
      )}
      {canSetGoals && (
        <form className="actions" onSubmit={addGoal} aria-label="Add a goal">
          <label className="grow">
            Add a goal
            <input value={newGoal} onChange={(e) => setNewGoal(e.target.value)} placeholder="e.g. Finish the farm survey" />
          </label>
          <button type="submit" disabled={busy || !newGoal.trim()}>
            Add
          </button>
        </form>
      )}

      {canWriteSelf && (
        <form className="stack sub-form" onSubmit={saveSelf} aria-label="Write a self-assessment">
          <label>
            Self-assessment
            <textarea value={selfText} onChange={(e) => setSelfText(e.target.value)} rows={5} />
          </label>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Save
            </button>
          </div>
        </form>
      )}
      {canSubmitSelf && (
        <div className="actions">
          <button type="button" disabled={busy || !selfText.trim()} onClick={() => act("submit_self_assessment")}>
            Submit self-assessment
          </button>
        </div>
      )}

      {!appraisal.is_mine && appraisal.state !== "draft" && appraisal.self_assessment && (
        <p className="panel-card padded">
          <strong>Self-assessment: </strong>
          {appraisal.self_assessment}
        </p>
      )}

      {canWriteManager && (
        <form className="stack sub-form" onSubmit={saveManager} aria-label="Write the manager's assessment">
          <label>
            Manager's assessment
            <textarea value={managerText} onChange={(e) => setManagerText(e.target.value)} rows={5} />
          </label>
          <div className="grid2">
            <label>
              Overall rating (1 to 5)
              <input type="number" min={1} max={5} value={rating} onChange={(e) => setRating(Number(e.target.value))} />
            </label>
            <label>
              Outcome
              <input value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="e.g. increment" />
            </label>
          </div>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Save
            </button>
          </div>
        </form>
      )}
      {canRate && (
        <div className="actions">
          <button type="button" disabled={busy || !managerText.trim()} onClick={() => act("rate")}>
            Rate
          </button>
        </div>
      )}

      {appraisal.state !== "draft" && appraisal.manager_assessment && (appraisal.is_mine || canSign) && (
        <p className="panel-card padded">
          <strong>Manager's assessment: </strong>
          {appraisal.manager_assessment}
          {appraisal.overall_rating !== null && ` (rated ${appraisal.overall_rating}/5)`}
        </p>
      )}

      {signActions.length > 0 && canSign && (
        <div className="actions">
          {signActions.map((action) => (
            <button key={action} className={action === "reopen" ? "secondary" : ""} disabled={busy} onClick={() => click(action)}>
              {ACTION_LABEL[action] ?? action}
            </button>
          ))}
        </div>
      )}
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
