import { useCallback, useEffect, useState } from "react";
import { get, plainMessage, post } from "../../api/client";
import { ATTENDANCE_CORRECT_ROLES, hasAnyRole, type AttendanceRecord, type Me, type Paginated } from "../../api/types";
import { dmy, hm } from "../../app/format";
import { CheckInCard } from "./CheckInCard";
import { ExceptionRow } from "./ExceptionRow";

interface Props {
  me: Me;
  /** The hash path, which may carry ?tab=exceptions (from the nightly sweep's notification link). */
  path: string;
  onNavigate: (to: string) => void;
}

type Tab = "mine" | "exceptions";

const STATUS_CLASS: Record<string, string> = {
  present: "chip-approved",
  late: "chip-waiting",
  absent: "chip-rejected",
  missing_checkout: "chip-waiting",
  on_leave: "chip-draft",
  holiday: "chip-draft",
  not_scheduled: "chip-draft",
  corrected: "chip-approved",
};

export function StatusChip({ record }: { record: AttendanceRecord }) {
  return <span className={`chip ${STATUS_CLASS[record.status] ?? ""}`}>{record.status_display}</span>;
}

/**
 * Attendance (item H-M02), phone first: check in and out for yourself, see your own recent days, and, for
 * Human Resources and supervisors, the exceptions the nightly sweep found, each corrected with a reason.
 */
export function AttendanceScreen({ me, path, onNavigate }: Props) {
  const query = path.includes("?") ? new URLSearchParams(path.split("?")[1]) : null;
  const canCorrect = hasAnyRole(me, ATTENDANCE_CORRECT_ROLES);
  const [tab, setTab] = useState<Tab>(query?.get("tab") === "exceptions" && canCorrect ? "exceptions" : "mine");
  const [today, setToday] = useState<AttendanceRecord | null>(null);
  const [recent, setRecent] = useState<AttendanceRecord[]>([]);
  const [exceptions, setExceptions] = useState<AttendanceRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadMine = useCallback(() => {
    if (me.employee_id === null) return;
    Promise.all([
      get<AttendanceRecord | null>("/attendance/records/mine/"),
      get<Paginated<AttendanceRecord>>(`/attendance/records/?employee=${me.employee_id}`),
    ])
      .then(([mine, history]) => {
        setToday(mine ?? null);
        setRecent(history.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load your attendance.")));
  }, [me.employee_id]);

  const loadExceptions = useCallback(() => {
    if (!canCorrect) return;
    get<Paginated<AttendanceRecord>>("/attendance/records/?exceptions=1")
      .then((r) => {
        setExceptions(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load attendance exceptions.")));
  }, [canCorrect]);

  useEffect(() => {
    if (tab === "mine") loadMine();
    else loadExceptions();
  }, [tab, loadMine, loadExceptions]);

  async function checkIn() {
    setBusy(true);
    setNotice(null);
    try {
      const record = await post<AttendanceRecord>("/attendance/records/check_in/");
      setToday(record);
      setNotice(`Checked in at ${hm(record.time_in)}.`);
      setError(null);
    } catch (err) {
      setError(plainMessage(err, "Could not check you in."));
    } finally {
      setBusy(false);
    }
  }

  async function checkOut() {
    setBusy(true);
    setNotice(null);
    try {
      const record = await post<AttendanceRecord>("/attendance/records/check_out/");
      setToday(record);
      setNotice(`Checked out at ${hm(record.time_out)}.`);
      setError(null);
    } catch (err) {
      setError(plainMessage(err, "Could not check you out."));
    } finally {
      setBusy(false);
    }
  }

  async function correct(recordId: number, body: { time_in?: string; time_out?: string; note: string; clear?: boolean }) {
    try {
      await post(`/attendance/records/${recordId}/correct/`, body);
      setNotice("Saved.");
      setError(null);
      loadExceptions();
    } catch (err) {
      setError(plainMessage(err, "Could not save that correction."));
    }
  }

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Attendance</h1>
          <p className="muted lead">
            {canCorrect
              ? "Check in and out, and the exceptions the nightly check found."
              : "Check in when you arrive, and out when you leave."}
          </p>
        </div>
      </div>

      {canCorrect && (
        <div className="tabs" role="tablist" aria-label="Attendance">
          <button
            role="tab"
            aria-selected={tab === "mine"}
            className={tab === "mine" ? "tab active" : "tab"}
            onClick={() => setTab("mine")}
          >
            My attendance
          </button>
          <button
            role="tab"
            aria-selected={tab === "exceptions"}
            className={tab === "exceptions" ? "tab active" : "tab"}
            onClick={() => setTab("exceptions")}
          >
            Exceptions ({exceptions.length})
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

      {tab === "mine" &&
        (me.employee_id === null ? (
          <p className="panel-card padded muted">Your account is not linked to an employee record.</p>
        ) : (
          <>
            <CheckInCard today={today} busy={busy} onCheckIn={checkIn} onCheckOut={checkOut} />
            <section className="panel-card" aria-labelledby="recent-heading">
              <h2 id="recent-heading">Recent days</h2>
              {recent.length === 0 ? (
                <p className="panel-empty">Nothing recorded yet.</p>
              ) : (
                <ul className="rows">
                  {recent.map((r) => (
                    <li key={r.id} className="item-row">
                      <span className="stacked grow">
                        <span className="strong">{dmy(r.date)}</span>
                        <span className="muted small">
                          {r.time_in ? hm(r.time_in) : "—"} to {r.time_out ? hm(r.time_out) : "—"}
                          {r.note && ` · ${r.note}`}
                        </span>
                      </span>
                      <StatusChip record={r} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ))}

      {tab === "exceptions" && canCorrect && (
        <section aria-label="Attendance exceptions">
          {exceptions.length === 0 ? (
            <p className="panel-card padded">Nothing is waiting for a correction.</p>
          ) : (
            exceptions.map((r) => (
              <ExceptionRow key={r.id} record={r} onCorrect={correct} onOpenFile={(id) => onNavigate(`/people/${id}`)} />
            ))
          )}
        </section>
      )}
    </>
  );
}
