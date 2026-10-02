import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import { HR_ROLES, hasAnyRole, type CareerEvent, type CareerKind, type Employee, type Me, type Position } from "../../api/types";
import { dmy } from "../../app/format";
import { WriteLetter, type LetterPreset } from "../letters/WriteLetter";

const KINDS: [CareerKind, string][] = [
  ["transfer", "Transfer"],
  ["promotion", "Promotion"],
  ["increment", "Increment"],
  ["acting", "Acting appointment"],
  ["confirmation", "Confirmation in the post"],
];
const TO_A_POST: CareerKind[] = ["transfer", "promotion", "acting"];

/** What changed, in a line: from which post to which, or which step, and from when. */
function described(e: CareerEvent): string {
  const from = dmy(e.effective_date);
  switch (e.kind) {
    case "increment":
      return `From ${e.from_grade_name} to ${e.to_grade_name}, from ${from}`;
    case "acting":
      return `Acting in ${e.to_post} from ${from}${e.end_date ? ` to ${dmy(e.end_date)}` : ", until further notice"}`;
    case "confirmation":
      return `Confirmed in ${e.from_post} from ${from}`;
    default:
      return `From ${e.from_post} to ${e.to_post}, from ${from}`;
  }
}

function ChangeForm({ employee, onRecorded }: { employee: Employee; onRecorded: (event: CareerEvent) => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<CareerKind>("transfer");
  const [posts, setPosts] = useState<Position[]>([]);
  const [position, setPosition] = useState("");
  const [on, setOn] = useState("");
  const [until, setUntil] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toAPost = TO_A_POST.includes(kind);

  useEffect(() => {
    if (!open) return;
    getAll<Position>(`/org/positions/?campus=${employee.campus}&status=approved`)
      .then(setPosts)
      .catch(() => setPosts([]));
  }, [open, employee.campus]);

  async function record(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const event = await post<CareerEvent>("/career-events/", {
        employee: employee.id,
        kind,
        effective_date: on,
        reason,
        ...(toAPost ? { to_position: Number(position) } : {}),
        ...(kind === "acting" && until ? { end_date: until } : {}),
      });
      setOpen(false);
      setPosition("");
      setOn("");
      setUntil("");
      setReason("");
      onRecorded(event);
    } catch (err) {
      setError(errorMessage(err, "The change was not recorded."));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <div className="actions">
        <button className="secondary" onClick={() => setOpen(true)}>
          Record a change
        </button>
      </div>
    );

  return (
    <form className="stack sub-form" onSubmit={record} aria-label="Record a change">
      <h4>Record a change</h4>
      <div className="grid2">
        <label>
          Change
          <select value={kind} onChange={(e) => setKind(e.target.value as CareerKind)}>
            {KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {kind === "acting" ? "Acting from" : "Takes effect on"}
          <input type="date" value={on} onChange={(e) => setOn(e.target.value)} required />
        </label>
        {toAPost && (
          <label>
            {kind === "acting" ? "Post acted in" : "To the post"}
            <select value={position} onChange={(e) => setPosition(e.target.value)} required>
              <option value="">Choose</option>
              {posts.map((p) => (
                <option key={p.id} value={p.id} disabled={kind !== "acting" && !p.is_vacant}>
                  {p.number} {p.title} · {p.grade_name}
                  {p.is_vacant ? "" : ", filled"}
                </option>
              ))}
            </select>
          </label>
        )}
        {kind === "acting" && (
          <label>
            Acting until (leave empty for further notice)
            <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
          </label>
        )}
      </div>
      <label>
        Why
        <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
      </label>
      <p className="muted small">
        A change dated today or earlier takes effect now; a later one takes effect on its day. The appointment, the
        contract and the leave written into it move with it.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          Record the change
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function CancelForm({ event, onDone }: { event: CareerEvent; onDone: (cancelled: boolean) => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function cancel(e: FormEvent) {
    e.preventDefault();
    try {
      await post(`/career-events/${event.id}/cancel/`, { reason });
      onDone(true);
    } catch (err) {
      setError(errorMessage(err, "The change was not cancelled."));
    }
  }

  return (
    <form className="stack" onSubmit={cancel} aria-label={`Cancel the ${event.kind_name.toLowerCase()}`}>
      <label>
        Why cancel it
        <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="secondary">
          Cancel the change
        </button>
        <button type="button" className="link" onClick={() => onDone(false)}>
          Keep it
        </button>
      </div>
    </form>
  );
}

/** Transfers, promotions, increments, acting appointments and confirmations (item 1.11), each with its letter. */
export function CareerSection({ employee, me, onChanged }: { employee: Employee; me: Me; onChanged: () => void }) {
  const [events, setEvents] = useState<CareerEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [writing, setWriting] = useState<CareerEvent | null>(null);
  const [cancelling, setCancelling] = useState<number | null>(null);
  const isHr = hasAnyRole(me, HR_ROLES);
  const preset = useMemo<LetterPreset | undefined>(
    () =>
      writing
        ? {
            code: writing.letter_template,
            answers: writing.letter_answers ?? {},
            careerEvent: writing.id,
            title: `the ${writing.kind_name.toLowerCase()}`,
          }
        : undefined,
    [writing],
  );

  const load = useCallback(() => {
    getAll<CareerEvent>(`/career-events/?employee=${employee.id}`)
      .then(setEvents)
      .catch((err) => setError(errorMessage(err, "Could not load the career changes.")));
  }, [employee.id]);
  useEffect(load, [load]);

  function recorded(event: CareerEvent) {
    setNotice(
      event.state === "applied"
        ? `${event.kind_name} recorded, and in effect.`
        : `${event.kind_name} recorded: it takes effect on ${dmy(event.effective_date)}.`,
    );
    load();
    onChanged();
  }

  return (
    <section className="stack" aria-labelledby="career-heading">
      <h3 id="career-heading">Career changes</h3>
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
      {events !== null && events.length === 0 && <p className="muted">No changes recorded.</p>}
      {events !== null && events.length > 0 && (
        <ul className="plain accounts" aria-label="Career changes">
          {events.map((e) => (
            <li key={e.id} className={`career-${e.state}`}>
              <div>
                <strong>{e.kind_name}</strong> <span className={`chip chip-career-${e.state}`}>{e.state_name}</span>
                <br />
                <span className="small">{described(e)}</span>
                <br />
                <span className="muted small">
                  {e.reason}
                  {e.recorded_by ? ` · recorded by ${e.recorded_by}` : ""}
                </span>
              </div>
              {e.problem && <p className="error small">{e.problem}</p>}
              {e.letters.length > 0 && (
                <p className="small">
                  Letter:{" "}
                  {e.letters.map((l) => (
                    <a key={l.id} href={l.download_url}>
                      {l.reference}
                    </a>
                  ))}
                </p>
              )}
              {isHr && e.state !== "cancelled" && (
                <div className="actions">
                  <button className="link" onClick={() => setWriting(e)}>
                    Write the letter
                  </button>
                  {(e.state === "scheduled" || e.state === "blocked") && (
                    <button className="link" onClick={() => setCancelling(e.id)}>
                      Cancel this change
                    </button>
                  )}
                </div>
              )}
              {cancelling === e.id && (
                <CancelForm
                  event={e}
                  onDone={(cancelled) => {
                    setCancelling(null);
                    if (cancelled) {
                      setNotice(`${e.kind_name} cancelled.`);
                      load();
                    }
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {writing && preset && (
        <WriteLetter
          key={writing.id}
          employee={employee}
          preset={preset}
          onIssued={() => {
            load();
            onChanged();
          }}
          onClose={() => setWriting(null)}
        />
      )}
      {isHr && <ChangeForm employee={employee} onRecorded={recorded} />}
    </section>
  );
}
