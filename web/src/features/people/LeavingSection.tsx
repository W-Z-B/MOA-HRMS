import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import {
  HR_ROLES,
  LETTER_ROLES,
  hasAnyRole,
  type Employee,
  type LeavingNotice,
  type LeavingReason,
  type Me,
  type Separation,
  type Settlement,
} from "../../api/types";
import { dmy, gyd } from "../../app/format";
import { WriteLetter, type LetterPreset } from "../letters/WriteLetter";

const REASONS: [LeavingReason, string][] = [
  ["resignation", "Resignation"],
  ["retirement", "Retirement"],
  ["contract_end", "End of a fixed-term contract"],
  ["notice", "Ended by the School with notice"],
  ["redundancy", "Redundancy"],
  ["dismissal", "Dismissal for good and sufficient cause"],
  ["mutual", "Mutual consent"],
  ["probation", "Ended during probation"],
  ["death", "Death in service"],
];
const WITH_NOTICE: LeavingReason[] = ["resignation", "notice", "redundancy"];

/** The notice check in a sentence or two. */
function noticeInWords(n: LeavingNotice): string {
  if (!n.needed) return n.why ?? "No notice is needed.";
  const by = n.given_by === "employee" ? "the employee" : "the School";
  const asked = `Notice given by ${by} on ${dmy(n.given_on)}; ${n.rule} is asked for.`;
  if (!n.short_by_days) return `${asked} The last day leaves full notice.`;
  const short = `The last day leaves it ${n.short_by_days} ${n.short_by_days === 1 ? "day" : "days"} short`;
  return `${asked} ${short}${n.given_by === "school" ? ": the days short are paid in lieu." : "."}`;
}

function Figures({ settlement }: { settlement: Settlement }) {
  return (
    <div className="stack">
      {settlement.monthly && (
        <p className="muted small">
          On {gyd(settlement.monthly)} a month ({settlement.grade}), {settlement.completed_years} completed{" "}
          {settlement.completed_years === 1 ? "year" : "years"} of service from {dmy(settlement.service_from)}.
        </p>
      )}
      {settlement.lines.length === 0 ? (
        <p className="muted">Nothing is owed beyond the last pay.</p>
      ) : (
        <table className="figures" aria-label="Owed on leaving">
          <tbody>
            {settlement.lines.map((line) => (
              <tr key={line.key}>
                <td>{line.label}</td>
                <td className="num">{gyd(line.amount)}</td>
              </tr>
            ))}
            <tr className="total">
              <td>Total</td>
              <td className="num">{gyd(settlement.total)}</td>
            </tr>
          </tbody>
        </table>
      )}
      <ul className="muted small notes">
        {settlement.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}

function LeavingForm({ employee, onRecorded }: { employee: Employee; onRecorded: (s: Separation) => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<LeavingReason>("resignation");
  const [notice, setNotice] = useState("");
  const [last, setLast] = useState("");
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<{ notice: LeavingNotice; settlement: Settlement | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const withNotice = WITH_NOTICE.includes(reason);
  const body = () => ({
    employee: employee.id,
    reason,
    last_day: last,
    note,
    notice_given_on: withNotice && notice ? notice : null,
  });
  // Any change means checking again: what is recorded is what was checked.
  const changed =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v);
      setPreview(null);
    };

  async function check(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setPreview(await post<{ notice: LeavingNotice; settlement: Settlement | null }>("/separations/preview/", body()));
    } catch (err) {
      setError(errorMessage(err, "Could not check the leaving."));
    } finally {
      setBusy(false);
    }
  }

  async function record() {
    setBusy(true);
    setError(null);
    try {
      const recorded = await post<Separation>("/separations/", body());
      setOpen(false);
      setPreview(null);
      onRecorded(recorded);
    } catch (err) {
      setError(errorMessage(err, "The leaving was not recorded."));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <div className="actions">
        <button className="secondary" onClick={() => setOpen(true)}>
          Record leaving
        </button>
      </div>
    );

  return (
    <form className="stack sub-form" onSubmit={check} aria-label="Record leaving">
      <h4>Record leaving</h4>
      <div className="grid2">
        <label>
          Why they are leaving
          <select value={reason} onChange={(e) => changed(setReason)(e.target.value as LeavingReason)}>
            {REASONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {withNotice && (
          <label>
            Notice given on
            <input type="date" value={notice} onChange={(e) => changed(setNotice)(e.target.value)} required />
          </label>
        )}
        <label>
          Last day
          <input type="date" value={last} onChange={(e) => changed(setLast)(e.target.value)} required />
        </label>
      </div>
      <label>
        In words
        <input value={note} onChange={(e) => changed(setNote)(e.target.value)} required maxLength={300} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="secondary" disabled={busy}>
          Check the notice and the figures
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {preview && (
        <div className="stack" aria-label="The check">
          <p>{noticeInWords(preview.notice)}</p>
          {preview.settlement && <Figures settlement={preview.settlement} />}
          <p className="muted small">
            The night after the last day {employee.first_name} has left: the appointment ends and the account is switched
            off.
          </p>
          <div className="actions">
            <button type="button" onClick={record} disabled={busy}>
              Record leaving
            </button>
          </div>
        </div>
      )}
    </form>
  );
}

function WithdrawForm({ separation, onDone }: { separation: Separation; onDone: (done: boolean) => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function withdraw(e: FormEvent) {
    e.preventDefault();
    try {
      await post(`/separations/${separation.id}/withdraw/`, { reason });
      onDone(true);
    } catch (err) {
      setError(errorMessage(err, "The leaving was not withdrawn."));
    }
  }

  return (
    <form className="stack" onSubmit={withdraw} aria-label="Withdraw the leaving">
      <label>
        Why withdraw it
        <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="secondary">
          Withdraw the leaving
        </button>
        <button type="button" className="link" onClick={() => onDone(false)}>
          Keep it
        </button>
      </div>
    </form>
  );
}

/** Leaving the School (items 1.12 to 1.14): for HR, the Principal and the auditor; HR records and withdraws. */
export function LeavingSection({ employee, me, onChanged }: { employee: Employee; me: Me; onChanged: () => void }) {
  const [separations, setSeparations] = useState<Separation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);
  const [writing, setWriting] = useState<Separation | null>(null);
  const reads = hasAnyRole(me, LETTER_ROLES);
  const isHr = hasAnyRole(me, HR_ROLES);
  const preset = useMemo<LetterPreset | undefined>(
    () =>
      writing
        ? {
            code: writing.letter_template,
            answers: writing.letter_answers ?? {},
            title: "the certificate of service",
          }
        : undefined,
    [writing],
  );

  const load = useCallback(() => {
    if (!reads) return;
    getAll<Separation>(`/separations/?employee=${employee.id}`)
      .then(setSeparations)
      .catch((err) => setError(errorMessage(err, "Could not load the leaving.")));
  }, [employee.id, reads]);
  useEffect(load, [load]);

  if (!reads) return null;
  const current = separations?.find((s) => s.state !== "withdrawn") ?? null;
  const withdrawn = separations?.filter((s) => s.state === "withdrawn") ?? [];

  return (
    <section className="stack" aria-labelledby="leaving-heading">
      <h3 id="leaving-heading">Leaving</h3>
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
      {current && (
        <div className={`card-block leaving leaving-${current.state}`}>
          <p>
            <strong>
              {current.state === "left" ? `Left on ${dmy(current.last_day)}` : `Leaving on ${dmy(current.last_day)}`}
            </strong>{" "}
            <span className="chip">{current.reason_name}</span>
          </p>
          <p className="muted small">
            {current.note}
            {current.recorded_by ? ` · recorded by ${current.recorded_by}` : ""}
          </p>
          <p>{noticeInWords(current.notice)}</p>
          {current.settlement && <Figures settlement={current.settlement} />}
          {isHr && (
            <div className="actions">
              {current.state === "leaving" && (
                <button className="link" onClick={() => setWithdrawing(true)}>
                  Withdraw the leaving
                </button>
              )}
              <button className="link" onClick={() => setWriting(current)}>
                Write the certificate of service
              </button>
            </div>
          )}
          {withdrawing && (
            <WithdrawForm
              separation={current}
              onDone={(done) => {
                setWithdrawing(false);
                if (done) {
                  setNotice("The leaving is withdrawn.");
                  load();
                  onChanged();
                }
              }}
            />
          )}
        </div>
      )}
      {writing && preset && (
        <WriteLetter
          key={writing.id}
          employee={employee}
          preset={preset}
          onIssued={onChanged}
          onClose={() => setWriting(null)}
        />
      )}
      {separations !== null && current === null && <p className="muted">No leaving is recorded.</p>}
      {withdrawn.length > 0 && (
        <p className="muted small">
          Withdrawn before:{" "}
          {withdrawn.map((s) => `${s.reason_name.toLowerCase()} for ${dmy(s.last_day)} (${s.withdrawn_reason})`).join("; ")}.
        </p>
      )}
      {isHr && separations !== null && current === null && employee.status !== "separated" && (
        <LeavingForm
          employee={employee}
          onRecorded={(s) => {
            setNotice(s.state === "left" ? "Recorded: they have left." : `Recorded: leaving on ${dmy(s.last_day)}.`);
            load();
            onChanged();
          }}
        />
      )}
    </section>
  );
}
