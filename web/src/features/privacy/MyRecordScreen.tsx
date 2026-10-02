import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, plainMessage, post } from "../../api/client";
import type { CorrectionRequest, CurrentNotice, Objection, OwnRecord, Paginated, RecordRestriction } from "../../api/types";
import { dmy, dmyTime } from "../../app/format";
import { NoticeText } from "./PrivacyNoticeScreen";

/** The parts of a staff record, in reading order, with their headings. */
const SECTIONS: [string, string][] = [
  ["personal", "Personal details"],
  ["appointments", "Appointments"],
  ["contract_and_terms", "Contract and terms"],
  ["leave_balances", "Leave balances"],
  ["leave_requests", "Leave requests"],
  ["qualifications", "Qualifications"],
  ["work_before_gsa", "Work before GSA"],
  ["dependants", "Dependants"],
  ["emergency_contacts", "Emergency contacts"],
  ["bank_accounts", "Bank accounts"],
  ["work_accidents", "Accidents at work"],
  ["documents", "Documents on file"],
  ["history_of_changes", "Changes made to your record"],
];
const LABELS: Record<string, string> = {
  employee_no: "Employee number",
  national_id: "National ID",
  nis_no: "NIS number",
  tin: "TIN",
  action_name: "What",
  actor: "Who",
  at: "When",
  account_ending: "Account ending",
  waiting_for_a_decision: "Waiting for a decision",
  last_sign_in: "Last signed in",
  signed_in_on: "Signed in on",
  privacy_notices_read: "Privacy notices read",
  nis_notice_of_accident_given_on: "NIS notice of accident given on",
};
const SUBJECTS: [string, string][] = [
  ["personal", "Personal details"],
  ["contact", "Contact details"],
  ["emergency", "Emergency contacts"],
  ["dependants", "Dependants"],
  ["qualifications", "Qualifications"],
  ["previous", "Work before GSA"],
  ["bank", "Bank details"],
  ["appointment", "Appointment or contract"],
  ["leave", "Leave records"],
  ["other", "Something else"],
];

const label = (key: string) => LABELS[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** A stored value in words: dates as dd/mm/yyyy, yes or no, lists and nested details on one line. */
function said(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return dmy(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) return dmyTime(value);
  if (Array.isArray(value)) return value.length === 0 ? "—" : value.map(said).join("; ");
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("field" in record && "before" in record && "after" in record)
      return `${record.field}: ${said(record.before)} → ${said(record.after)}`;
    return Object.entries(record)
      .filter(([key]) => key !== "id" && key !== "employee")
      .map(([key, inner]) => `${label(key)}: ${said(inner)}`)
      .join(", ");
  }
  return String(value);
}

function Details({ value }: { value: Record<string, unknown> }) {
  return (
    <dl className="terms">
      {Object.entries(value)
        .filter(([key]) => key !== "employee")
        .map(([key, inner]) => (
          <div key={key}>
            <dt>{label(key)}</dt>
            <dd>{said(inner)}</dd>
          </div>
        ))}
    </dl>
  );
}

function Rows({ rows, caption }: { rows: Record<string, unknown>[]; caption: string }) {
  if (rows.length === 0) return <p className="muted">None on file.</p>;
  const columns = Object.keys(rows[0]);
  return (
    <table className="cards">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {columns.map((key) => (
            <th key={key} scope="col">
              {label(key)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {columns.map((key) => (
              <td key={key} data-label={label(key)}>
                {said(row[key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Section({ title, value }: { title: string; value: unknown }) {
  const id = `record-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section className="card-block record-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {Array.isArray(value) ? (
        <Rows rows={value as Record<string, unknown>[]} caption={title} />
      ) : value && typeof value === "object" ? (
        <Details value={value as Record<string, unknown>} />
      ) : (
        <p className="muted">None on file.</p>
      )}
    </section>
  );
}

function download(record: OwnRecord) {
  const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `my-gsa-hrms-record-${record.produced_at.slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Everything the system holds about the signed-in person (item 1.31): to read, print or keep as a file,
 * with a way to ask for anything wrong to be corrected, and the answers.
 */
export function MyRecordScreen() {
  const [record, setRecord] = useState<OwnRecord | null>(null);
  const [requests, setRequests] = useState<CorrectionRequest[]>([]);
  const [notice, setNotice] = useState<CurrentNotice | null>(null);
  const [showNotice, setShowNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRequests = useCallback(() => {
    get<Paginated<CorrectionRequest>>("/privacy/corrections/")
      .then((page) => setRequests(page.results.filter((r) => r.is_mine)))
      .catch(() => setRequests([]));
  }, []);

  useEffect(() => {
    get<OwnRecord>("/privacy/my-record/")
      .then(setRecord)
      .catch((err) => setError(errorMessage(err, "Could not load your record.")));
    get<CurrentNotice>("/privacy/notice/").then(setNotice).catch(() => setNotice(null));
    loadRequests();
  }, [loadRequests]);

  const staff = record?.staff_record ?? null;
  const account = record?.account ?? null;

  return (
    <>
      <div className="panel-head">
        <div>
          <h1>My record</h1>
          <p className="muted">
            {record ? `Everything the GSA HRMS holds about you, as at ${dmyTime(record.produced_at)}.` : "Loading…"}
          </p>
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {record && (
        <div className="actions no-print record-actions">
          <button className="secondary" onClick={() => download(record)}>
            Download as a file
          </button>
          <button className="secondary" onClick={() => window.print()}>
            Print or save as PDF
          </button>
          {notice?.notice && (
            <button className="secondary" aria-expanded={showNotice} onClick={() => setShowNotice((v) => !v)}>
              {showNotice ? "Hide the privacy notice" : "Read the privacy notice"}
            </button>
          )}
        </div>
      )}
      {showNotice && notice?.notice && (
        <section className="card-block" aria-label="Privacy notice">
          <h2>{notice.notice.title}</h2>
          <NoticeText notice={notice.notice} />
        </section>
      )}
      {staff && SECTIONS.map(([key, title]) => <Section key={key} title={title} value={staff[key]} />)}
      {record && !staff && (
        <p className="notice">Your account is not linked to a staff record, so it holds only your account.</p>
      )}
      {account && (
        <Section
          title="Your account"
          value={Object.fromEntries(Object.entries(account).filter(([key]) => key !== "name"))}
        />
      )}
      {staff && <CorrectionsPart requests={requests} onSent={loadRequests} />}
      {staff && <ObjectionsPart />}
    </>
  );
}

function CorrectionsPart({ requests, onSent }: { requests: CorrectionRequest[]; onSent: () => void }) {
  const [subject, setSubject] = useState("contact");
  const [wrong, setWrong] = useState("");
  const [shouldBe, setShouldBe] = useState("");
  const [restrict, setRestrict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSent(null);
    try {
      const made = await post<CorrectionRequest>("/privacy/corrections/", { subject, wrong, should_be: shouldBe, restrict });
      setSent(
        `Sent to Human Resources. They answer by ${dmy(made.due_by)}, and you will be told.` +
          (made.restricted ? " Until then that part of your record is held back from use." : ""),
      );
      setWrong("");
      setShouldBe("");
      setRestrict(false);
      onSent();
    } catch (err) {
      setError(plainMessage(err, "Your request was not sent. Try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card-block no-print" aria-labelledby="corrections-heading">
      <h2 id="corrections-heading">Something wrong?</h2>
      <p className="muted small">
        Tell Human Resources what is wrong and what it should say. They correct it, or tell you why not.
      </p>
      <form className="stack" onSubmit={submit} aria-label="Ask for a correction">
        <label>
          What is it about
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            {SUBJECTS.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          What is wrong
          <textarea value={wrong} onChange={(e) => setWrong(e.target.value)} rows={2} maxLength={1000} required />
        </label>
        <label>
          What it should say
          <textarea value={shouldBe} onChange={(e) => setShouldBe(e.target.value)} rows={2} maxLength={1000} required />
        </label>
        <label className="inline">
          <input type="checkbox" checked={restrict} onChange={(e) => setRestrict(e.target.checked)} /> Hold that part of my
          record back from use until Human Resources answers
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {sent && (
          <p role="status" className="notice good">
            {sent}
          </p>
        )}
        <div className="actions">
          <button type="submit" disabled={busy}>
            Send to Human Resources
          </button>
        </div>
      </form>
      {requests.length > 0 && (
        <>
          <h3>Your requests</h3>
          <ul className="plain history" aria-label="Your correction requests">
            {requests.map((r) => (
              <li key={r.id}>
                <p>
                  <strong>{r.subject_name}</strong>{" "}
                  <span className={`chip chip-correction-${r.state}`}>{r.state_name}</span>
                </p>
                <p className="small">
                  Wrong: {r.wrong} · Should say: {r.should_be}
                </p>
                <p className="muted small">
                  Asked {dmyTime(r.created_at)}
                  {r.state === "open"
                    ? ` · answer due by ${dmy(r.due_by)}`
                    : ` · answered by ${r.decided_by_name ?? "Human Resources"}${r.decision_note ? `: ${r.decision_note}` : ""}`}
                  {r.restricted ? " · held back from use until answered" : ""}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/**
 * Objecting in writing to how part of the record is used, and what is held back (item 1.46). The part objected
 * to is held back at once, until the data protection officer decides.
 */
function ObjectionsPart() {
  const [objections, setObjections] = useState<Objection[]>([]);
  const [held, setHeld] = useState<RecordRestriction[]>([]);
  const [part, setPart] = useState("contact");
  const [grounds, setGrounds] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Objection>>("/privacy/objections/")
      .then((page) => setObjections(page.results))
      .catch(() => setObjections([]));
    get<Paginated<RecordRestriction>>("/privacy/restrictions/?in_force=1")
      .then((page) => setHeld(page.results))
      .catch(() => setHeld([]));
  }, []);
  useEffect(load, [load]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSent(null);
    try {
      const made = await post<Objection>("/privacy/objections/", { part, grounds });
      setSent(`Sent to the data protection officer, who decides by ${dmy(made.due_by)}. Until then that part is held back from use.`);
      setGrounds("");
      load();
    } catch (err) {
      setError(plainMessage(err, "Your objection was not sent. Try again."));
    }
  }

  return (
    <section className="card-block no-print" aria-labelledby="objections-heading">
      <h2 id="objections-heading">Object to how your record is used</h2>
      <p className="muted small">
        You may object, at any time, to part of your record being used. That part is held back until the data
        protection officer decides; your objection stands unless GSA has compelling legitimate grounds, or needs it
        for a legal claim.
      </p>
      <form className="stack" onSubmit={submit} aria-label="Object to how your record is used">
        <label>
          Which part
          <select value={part} onChange={(e) => setPart(e.target.value)}>
            {SUBJECTS.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Why you object
          <textarea value={grounds} onChange={(e) => setGrounds(e.target.value)} rows={2} maxLength={2000} required />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {sent && (
          <p role="status" className="notice good">
            {sent}
          </p>
        )}
        <div className="actions">
          <button type="submit">Send my objection</button>
        </div>
      </form>
      {objections.length > 0 && (
        <>
          <h3>Your objections</h3>
          <ul className="plain history" aria-label="Your objections">
            {objections.map((o) => (
              <li key={o.id}>
                <p>
                  <strong>{o.part_name}</strong> <span className="chip">{o.state_name}</span>
                </p>
                <p className="small">{o.grounds}</p>
                <p className="muted small">
                  Made {dmyTime(o.created_at)}
                  {o.state === "open" ? ` · decision due by ${dmy(o.due_by)}` : ` · ${o.reasons}`}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
      {held.length > 0 && (
        <>
          <h3>Held back from use</h3>
          <ul className="plain" aria-label="Parts of your record held back">
            {held.map((r) => (
              <li key={r.id}>
                {r.part_name}: {r.ground_name.toLowerCase()} <span className="muted small">since {dmy(r.created_at)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
