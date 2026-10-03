import { useEffect, useRef, useState, type FormEvent } from "react";
import { plainMessage, post } from "../../api/client";
import type { LeaveCheck, LeaveRequest, LeaveType } from "../../api/types";
import { inDays, num } from "../../app/format";
import { usePhone } from "../../app/frame";
import { enqueueLeave, isNetworkError } from "../../app/offlineQueue";

interface Props {
  employeeId: number;
  types: LeaveType[];
  onSaved: (notice: string | null) => void;
}

/**
 * New request. As soon as the type and dates are chosen the server is asked what would happen,
 * so the employee sees the days, what is left and whether a note is needed before sending.
 */
export function RequestForm({ employeeId, types, onSaved }: Props) {
  const [leaveType, setLeaveType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const phone = usePhone();
  const [answer, setAnswer] = useState<{ key: string; check: LeaveCheck } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const type = types.find((t) => String(t.id) === leaveType);
  const key = leaveType && from && to && to >= from ? `${leaveType}|${from}|${to}` : "";
  const check = answer && answer.key === key ? answer.check : null;
  const blocked = (check?.problems.length ?? 0) > 0;
  const needsNote = check?.evidence_required ?? false;
  const noteName = (check?.evidence_name ?? type?.evidence_name ?? "supporting document").toLowerCase();

  useEffect(() => {
    if (!key) return;
    let current = true;
    const handle = setTimeout(() => {
      post<LeaveCheck>("/leave/requests/check/", { leave_type: Number(leaveType), from_date: from, to_date: to })
        .then((result) => current && setAnswer({ key, check: result }))
        .catch(() => undefined); // offline or refused: the server checks again when the request is saved
    }, 300);
    return () => {
      current = false;
      clearTimeout(handle);
    };
  }, [key, leaveType, from, to]);

  function changeFrom(value: string) {
    setFrom(value);
    if (!to || to < value) setTo(value);
  }

  function reset() {
    setFrom("");
    setTo("");
    setReason("");
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  async function save(e: FormEvent, send: boolean) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (send && needsNote && !file) {
      setError(`Attach your ${noteName} before sending.`);
      return;
    }
    setBusy(true);
    const payload = { employee: employeeId, leave_type: Number(leaveType), from_date: from, to_date: to, reason };
    let created: LeaveRequest | null = null;
    try {
      created = await post<LeaveRequest>("/leave/requests/", payload);
      if (file) {
        const body = new FormData();
        body.set("file", file);
        await post(`/leave/requests/${created.id}/evidence/`, body);
      }
      if (!send) {
        reset();
        onSaved("Saved as a draft. Send it when you are ready.");
        return;
      }
      const sent = await post<LeaveRequest>(`/leave/requests/${created.id}/transition/`, { action: "submit" });
      reset();
      onSaved(`Sent to ${sent.manager_name ?? "your campus supervisors"} for approval.`);
    } catch (err) {
      if (created) {
        reset();
        onSaved(null);
        setError(`Saved as a draft but not sent. ${plainMessage(err, "The connection was lost.")}`);
      } else if (isNetworkError(err)) {
        enqueueLeave(payload, send);
        reset();
        setNotice(
          "No connection. The request is saved on this phone and will be sent when the network returns." +
            (file ? " The file was not saved: attach it again then." : ""),
        );
      } else setError(plainMessage(err, "Could not save the request."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card-block stack leave-request" onSubmit={(e) => save(e, true)} aria-label="Ask for leave">
      <h2>Ask for leave</h2>
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
      <div className="grid2">
        <label>
          First day
          <input id="leave-from" type="date" value={from} onChange={(e) => changeFrom(e.target.value)} required />
        </label>
        <label>
          Last day
          <input id="leave-to" type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} required />
        </label>
      </div>
      <label>
        Reason (optional)
        <input id="leave-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
      </label>

      {!check && (
        <div className="check tone-neutral" role="status">
          <p>{key ? "Checking those days…" : "Choose the type of leave, then the first and last day."}</p>
        </div>
      )}
      {check && (
        <div className={`check ${blocked ? "bad tone-bad" : needsNote && !file ? "tone-warn" : "tone-good"}`} role="status">
          {blocked ? (
            check.problems.map((p) => <p key={p.code}>{p.detail}</p>)
          ) : (
            <>
              <p>
                <strong>{inDays(check.days)}</strong> of leave. Weekends and public holidays are not counted.
              </p>
              {type?.over_balance !== "allow" && (
                <p>
                  {num(check.beyond) > 0
                    ? `You have ${inDays(Math.max(num(check.available), 0))} left; ${inDays(check.beyond)} are beyond your balance.`
                    : `You will have ${inDays(check.remaining)} of ${type?.name.toLowerCase()} left.`}
                </p>
              )}
              {needsNote && (
                <p>
                  <strong>A {noteName} is needed.</strong> Take a photo of it or choose a PDF. Only you and Human
                  Resources can open it.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {needsNote && !blocked && (
        <label>
          {check?.evidence_name} (photo or PDF)
          <input
            id="leave-note"
            ref={fileInput}
            type="file"
            accept="image/*,application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
      )}
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
        <button type="submit" disabled={busy || blocked || !key}>
          Send request
        </button>
        <button type="button" className="secondary" disabled={busy || blocked || !key} onClick={(e) => save(e, false)}>
          Save draft
        </button>
      </div>
      {phone && (
        <p className="muted small">No signal? The request waits on this phone and is sent when you are back online.</p>
      )}
    </form>
  );
}
