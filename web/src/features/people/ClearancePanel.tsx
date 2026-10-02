import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage, get, post } from "../../api/client";
import { HR_ROLES, hasAnyRole, type Clearance, type ClearanceStep, type ExitInterview, type Me, type Separation } from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

// An exit interview holds someone's views of their managers: HR and the Principal read it.
const EXIT_ROLES = ["hr_officer", "hr_manager", "administrator", "principal"];
// Steps that close by themselves: the account the night after the last day, the interview when it is recorded.
const CLOSE_THEMSELVES = ["account", "interview"];
const REASONS: [string, string][] = [
  ["pay", "Pay and benefits"],
  ["growth", "Training and promotion"],
  ["workload", "Workload"],
  ["management", "Supervision and management"],
  ["conditions", "Working conditions"],
  ["moving", "Moving away"],
  ["family", "Personal or family reasons"],
  ["retirement", "Retirement"],
  ["other", "Something else"],
];
const RATINGS: [keyof ExitInterview, string][] = [
  ["rating_pay", "Pay and benefits"],
  ["rating_supervision", "Supervision"],
  ["rating_training", "Training and growth"],
  ["rating_workload", "Workload"],
  ["rating_conditions", "Working conditions"],
];

function StepCloser({ step, base, onClosed }: { step: ClearanceStep; base: string; onClosed: (c: Clearance | null) => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function close(done: boolean) {
    setError(null);
    try {
      onClosed(await post<Clearance>(`${base}/clearance/${step.code}/`, { done, note }));
    } catch (err) {
      setError(errorMessage(err, "The step was not closed."));
    }
  }

  return (
    <div className="stack">
      <label>
        Note (who confirmed it, or why it is not needed)
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button className="secondary" onClick={() => close(true)}>
          Done
        </button>
        <button className="secondary" onClick={() => close(false)}>
          Not needed
        </button>
        <button className="link" onClick={() => onClosed(null)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function InterviewForm({ base, onSaved }: { base: string; onSaved: (saved: ExitInterview) => void }) {
  const [heldOn, setHeldOn] = useState("");
  const [declined, setDeclined] = useState(false);
  const [reason, setReason] = useState("");
  const [recommend, setRecommend] = useState("");
  const [ratings, setRatings] = useState<Record<string, string>>({});
  const [keep, setKeep] = useState("");
  const [change, setChange] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const answers = declined
      ? { held_on: heldOn, declined: true }
      : {
          held_on: heldOn,
          declined: false,
          main_reason: reason,
          would_recommend: recommend,
          keep,
          change,
          ...Object.fromEntries(RATINGS.map(([key]) => [key, ratings[key] ? Number(ratings[key]) : null])),
        };
    try {
      onSaved(await post<ExitInterview>(`${base}/exit-interview/`, answers));
    } catch (err) {
      setError(errorMessage(err, "The exit interview was not saved."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save} aria-label="Exit interview">
      <h4>Exit interview</h4>
      <div className="grid2">
        <label>
          Held, or offered, on
          <input type="date" value={heldOn} onChange={(e) => setHeldOn(e.target.value)} required />
        </label>
        <label className="inline">
          <input type="checkbox" checked={declined} onChange={(e) => setDeclined(e.target.checked)} /> Offered, and declined
        </label>
      </div>
      {!declined && (
        <>
          <div className="grid2">
            <label>
              The main reason for leaving
              <select value={reason} onChange={(e) => setReason(e.target.value)}>
                <option value="">Not said</option>
                {REASONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Would they recommend the School as a place to work?
              <select value={recommend} onChange={(e) => setRecommend(e.target.value)}>
                <option value="">Not said</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
                <option value="unsure">Not sure</option>
              </select>
            </label>
            {RATINGS.map(([key, label]) => (
              <label key={key}>
                {label}, from 1 (poor) to 5 (very good)
                <select value={ratings[key] ?? ""} onChange={(e) => setRatings({ ...ratings, [key]: e.target.value })}>
                  <option value="">Not said</option>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <label>
            What the School should keep
            <textarea rows={2} value={keep} onChange={(e) => setKeep(e.target.value)} />
          </label>
          <label>
            What the School should change
            <textarea rows={2} value={change} onChange={(e) => setChange(e.target.value)} />
          </label>
        </>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Save the exit interview</button>
      </div>
    </form>
  );
}

function InterviewSummary({ interview }: { interview: ExitInterview }) {
  if (interview.declined) return <p>Exit interview offered on {dmy(interview.held_on)}, and declined.</p>;
  const rated = RATINGS.filter(([key]) => interview[key] !== null).map(([key, label]) => `${label} ${interview[key]}`);
  return (
    <dl className="terms">
      <dt>Held</dt>
      <dd>{dmy(interview.held_on)}</dd>
      <dt>Main reason</dt>
      <dd>{interview.main_reason_name || "Not said"}</dd>
      <dt>Would recommend the School</dt>
      <dd>{interview.would_recommend_name || "Not said"}</dd>
      <dt>Ratings out of 5</dt>
      <dd>{rated.length ? rated.join(", ") : "Not given"}</dd>
      {interview.keep && (
        <>
          <dt>Keep</dt>
          <dd>{interview.keep}</dd>
        </>
      )}
      {interview.change && (
        <>
          <dt>Change</dt>
          <dd>{interview.change}</dd>
        </>
      )}
    </dl>
  );
}

/** The clearance of someone leaving, step by step, and their exit interview (item 1.13). */
export function ClearancePanel({ separation, me, onChanged }: { separation: Separation; me: Me; onChanged: () => void }) {
  const [clearance, setClearance] = useState<Clearance | null>(null);
  const [interview, setInterview] = useState<ExitInterview | null | undefined>(undefined);
  const [closing, setClosing] = useState<string | null>(null);
  const [interviewing, setInterviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isHr = hasAnyRole(me, HR_ROLES) && separation.state !== "withdrawn";
  const readsInterview = hasAnyRole(me, EXIT_ROLES);
  const base = `/separations/${separation.id}`;

  const load = useCallback(() => {
    get<Clearance>(`${base}/clearance/`)
      .then(setClearance)
      .catch((err) => setError(errorMessage(err, "Could not load the clearance.")));
    if (!readsInterview) return;
    get<ExitInterview>(`${base}/exit-interview/`)
      .then(setInterview)
      .catch((err) => (err instanceof ApiError && err.status === 404 ? setInterview(null) : setInterview(undefined)));
  }, [base, readsInterview]);
  useEffect(load, [load]);

  if (clearance === null) return error ? <p role="alert" className="error">{error}</p> : null;
  const itemsOut = clearance.outstanding_items.length > 0;

  return (
    <section className="stack" aria-labelledby={`clearance-${separation.id}`}>
      <h4 id={`clearance-${separation.id}`}>
        Clearance: {clearance.steps.filter((s) => s.state !== "open").length} of {clearance.steps.length} steps closed
      </h4>
      <ul className="plain steps-list" aria-label="Clearance steps">
        {clearance.steps.map((step) => (
          <li key={step.code} className={`step step-${step.state}`}>
            <div>
              <span className={`chip chip-step-${step.state}`}>{step.state_name}</span> {step.label}
              <br />
              <span className="muted small">
                {step.state === "open"
                  ? `Confirmed by: ${step.who}`
                  : `${step.cleared_by_name ? `${step.cleared_by_name}, ` : ""}${step.cleared_at ? dmyTime(step.cleared_at) : ""}${step.note ? `: ${step.note}` : ""}`}
              </span>
            </div>
            {step.code === "items" && itemsOut && (
              <ul className="small" aria-label="Still out">
                {clearance.outstanding_items.map((item) => (
                  <li key={item.id}>
                    {item.description}
                    {item.tag ? ` (${item.tag})` : ""}, issued {dmy(item.issued_on)}
                  </li>
                ))}
              </ul>
            )}
            {isHr && step.state === "open" && !CLOSE_THEMSELVES.includes(step.code) && closing !== step.code && (
              <div className="actions">
                {step.code === "items" && itemsOut ? (
                  <span className="muted small">Record each item given back, or lost, under Items issued.</span>
                ) : (
                  <button className="link" onClick={() => setClosing(step.code)} aria-label={`Close the step: ${step.label}`}>
                    Close this step
                  </button>
                )}
              </div>
            )}
            {closing === step.code && (
              <StepCloser
                step={step}
                base={base}
                onClosed={(fresh) => {
                  setClosing(null);
                  if (fresh) {
                    setClearance(fresh);
                    onChanged();
                  }
                }}
              />
            )}
          </li>
        ))}
      </ul>
      {readsInterview && interview !== undefined && (
        <div className="stack">
          {interview && <InterviewSummary interview={interview} />}
          {!interview && isHr && !interviewing && (
            <div className="actions">
              <button className="secondary" onClick={() => setInterviewing(true)}>
                Record the exit interview
              </button>
            </div>
          )}
          {!interview && !isHr && <p className="muted">No exit interview is recorded.</p>}
          {interviewing && (
            <InterviewForm
              base={base}
              onSaved={(saved) => {
                setInterviewing(false);
                setInterview(saved);
                load();
                onChanged();
              }}
            />
          )}
        </div>
      )}
    </section>
  );
}
