import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { getAll, plainMessage, post } from "../../api/client";
import type { Classification, Employee, ScanBatch, ScanItem } from "../../api/types";
import { dmyTime } from "../../app/format";

const TYPES: [string, string][] = [
  ["contract", "Contract"],
  ["certificate", "Certificate"],
  ["letter", "Letter"],
  ["id_copy", "ID copy"],
  ["medical", "Medical"],
  ["other", "Other"],
];
/** The least each type is filed as: the server holds the same rule (a contract shows pay, and so on). */
const LEAST: Record<string, Classification> = { contract: "confidential", id_copy: "confidential", medical: "medical" };
const CLASSES: [Classification, string][] = [
  ["internal", "Internal"],
  ["confidential", "Confidential"],
  ["medical", "Medical (restricted)"],
];

/** One file as it went: filed, or waiting for HR to choose whose record it belongs in. */
interface Row {
  file: File;
  item: ScanItem | null;
  error: string | null;
}

function send(batch: number, file: File, employee?: string) {
  const body = new FormData();
  body.append("file", file);
  if (employee) body.append("employee", employee);
  return post<ScanItem>(`/scan-batches/${batch}/files/`, body);
}

function Unplaced({ batch, row, staff, onFiled }: { batch: number; row: Row; staff: Employee[]; onFiled: (item: ScanItem) => void }) {
  const [employee, setEmployee] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function place(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const item = await send(batch, row.file, employee);
      if (item.filed) onFiled(item);
      else setError(item.refused);
    } catch (err) {
      setError(plainMessage(err, "It was not filed."));
    }
  }

  return (
    <form className="inline-form" onSubmit={place} aria-label={`Choose whose file ${row.file.name} belongs in`}>
      <label>
        Whose file
        <select value={employee} onChange={(e) => setEmployee(e.target.value)} required>
          <option value="">Choose</option>
          {staff.map((s) => (
            <option key={s.id} value={s.id}>
              {s.full_name} ({s.employee_no})
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="secondary">
        File it there
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}

/**
 * Item 1.21: a pile of scanned personnel papers filed into staff records in one sitting. Each file goes into
 * the record of the employee number its name starts with; any that cannot be placed wait for HR to choose.
 */
export function ScanningScreen({ onNavigate }: { onNavigate: (to: string) => void }) {
  const [batches, setBatches] = useState<ScanBatch[]>([]);
  const [staff, setStaff] = useState<Employee[]>([]);
  const [docType, setDocType] = useState("contract");
  const [classification, setClassification] = useState<Classification>("confidential");
  const [note, setNote] = useState("");
  const [batch, setBatch] = useState<ScanBatch | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getAll<ScanBatch>("/scan-batches/")
      .then(setBatches)
      .catch(() => setBatches([]));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    getAll<Employee>("/employees/?status=active")
      .then(setStaff)
      .catch(() => setStaff([]));
  }, []);

  function chooseType(value: string) {
    setDocType(value);
    setClassification(LEAST[value] ?? "confidential");
  }

  async function begin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setBatch(await post<ScanBatch>("/scan-batches/", { doc_type: docType, classification, note }));
      setRows([]);
    } catch (err) {
      setError(plainMessage(err, "The batch was not begun."));
    }
  }

  async function sendAll(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!batch || files.length === 0) return;
    setBusy(true);
    for (const file of files) {
      // One at a time, so a large pile never makes one large request.
      let row: Row;
      try {
        row = { file, item: await send(batch.id, file), error: null };
      } catch (err) {
        row = { file, item: null, error: plainMessage(err, "It was not sent.") };
      }
      setRows((done) => [...done, row]);
    }
    setBusy(false);
    load();
  }

  const filed = rows.filter((r) => r.item?.filed).length;
  // Never below what the type needs: the classes from that one up.
  const allowed = CLASSES.slice(CLASSES.findIndex(([value]) => value === (LEAST[docType] ?? "internal")));
  return (
    <>
      <div className="panel-head">
        <h1>File scanned papers</h1>
        <button className="secondary" onClick={() => onNavigate("/people")}>
          Back to People
        </button>
      </div>
      <p className="muted">
        Name each file starting with the employee number, such as <code>E0001 Appointment 2014.pdf</code>. Each goes
        into that person&apos;s record, titled with the rest of its name. Any that cannot be placed wait for you to
        choose whose file they belong in.
      </p>
      {!batch ? (
        <form className="stack sub-form" onSubmit={begin} aria-label="Begin a batch">
          <div className="grid2">
            <label>
              The papers are
              <select value={docType} onChange={(e) => chooseType(e.target.value)}>
                {TYPES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Classification
              <select value={classification} onChange={(e) => setClassification(e.target.value as Classification)}>
                {allowed.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Note <span className="muted small">(optional)</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder="Personnel files, cabinet 2" />
            </label>
          </div>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button type="submit">Begin</button>
          </div>
        </form>
      ) : (
        <section className="card-block stack" aria-labelledby="batch-heading">
          <h2 id="batch-heading">
            {batch.doc_type_name}, {CLASSES.find(([v]) => v === batch.classification)?.[1].toLowerCase()}
            {batch.note ? `: ${batch.note}` : ""}
          </h2>
          <label>
            Choose the scanned files (PDF or photographs, up to 20 MB each)
            <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,.docx,.xlsx" onChange={sendAll} disabled={busy} />
          </label>
          {rows.length > 0 && (
            <p role="status" className="notice">
              {busy ? `Filing… ${rows.length} done so far.` : `${filed} of ${rows.length} filed.`}
            </p>
          )}
          <ul className="plain stack" aria-label="Files in this batch">
            {rows.map((row, index) => (
              <li key={index}>
                <strong>{row.file.name}</strong>{" "}
                {row.item?.filed ? (
                  <span className="small">
                    filed in the record of {row.item.employee_name} ({row.item.employee_no}) as “{row.item.document_title}”
                  </span>
                ) : (
                  <>
                    <span className="small error">{row.item?.refused ?? row.error}</span>
                    {row.item && (
                      <Unplaced
                        batch={batch.id}
                        row={row}
                        staff={staff}
                        onFiled={(item) => setRows((all) => all.map((r, i) => (i === index ? { ...r, item } : r)))}
                      />
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
          <div className="actions">
            <button className="secondary" onClick={() => setBatch(null)} disabled={busy}>
              Finish this batch
            </button>
          </div>
        </section>
      )}
      {batches.length > 0 && (
        <section className="stack" aria-labelledby="earlier-batches">
          <h2 id="earlier-batches">Batches filed</h2>
          <table className="cards" aria-label="Batches filed">
            <thead>
              <tr>
                <th>When</th>
                <th>Papers</th>
                <th>By</th>
                <th>Filed</th>
                <th>Not filed</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id}>
                  <td data-label="When">{dmyTime(b.created_at)}</td>
                  <td data-label="Papers">
                    {b.doc_type_name}
                    {b.note ? <span className="muted small"> {b.note}</span> : null}
                  </td>
                  <td data-label="By">{b.created_by_name}</td>
                  <td data-label="Filed">{b.filed}</td>
                  <td data-label="Not filed">{b.not_filed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
