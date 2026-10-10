import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, plainMessage, post } from "../../api/client";
import type { Onboarding, Paginated } from "../../api/types";

const STATE_LABEL: Record<string, string> = {
  in_progress: "In progress",
  documents_submitted: "Submitted, waiting for Human Resources",
  completed: "Completed",
  cancelled: "Cancelled",
};

/** A new hire's own document upload, while the "documents" step is still open: ``onboarding/{id}/
 * documents/``, not the general ``/documents/`` endpoint (HR write only) — the same reason leave's own
 * evidence action exists apart from it. A trimmed version of people.DocumentUpload: a new hire chooses
 * neither classification nor the wider range of document types HR files, only what they were asked to send. */
function MyDocumentUpload({ onboardingId, onSaved }: { onboardingId: number; onSaved: () => void }) {
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("contract");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.set("title", title || file.name);
    body.set("doc_type", docType);
    body.set("file", file);
    try {
      await post(`/onboarding/${onboardingId}/documents/`, body);
      setTitle("");
      setFile(null);
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Upload failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={submit} aria-label="Upload a document">
      <label>
        What is it?
        <select value={docType} onChange={(e) => setDocType(e.target.value)}>
          <option value="contract">Signed contract</option>
          <option value="id_copy">Identification</option>
          <option value="certificate">Certificate</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Passport copy" />
      </label>
      <label>
        File
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy || !file}>
          Upload
        </button>
      </div>
    </form>
  );
}

/** A new hire's own onboarding (item H-W02): their checklist, read-only, and the one step that is
 * naturally theirs — uploading the documents Human Resources asked for and submitting them for review. */
export function MyOnboardingScreen() {
  const [record, setRecord] = useState<Onboarding | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Onboarding>>("/onboarding/")
      .then((r) => setRecord(r.results[0] ?? null))
      .catch((err) => {
        setError(plainMessage(err, "Could not load your onboarding."));
        setRecord(null);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function submitDocuments() {
    if (!record) return;
    try {
      await post<Onboarding>(`/onboarding/${record.id}/transition/`, { action: "submit_documents" });
      setNotice("Submitted. Human Resources will confirm them.");
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "Upload at least one document first."));
    }
  }

  if (record === undefined) return <p className="loading">Loading…</p>;

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>My onboarding</h1>
          <p className="muted lead">Joining the Guyana School of Agriculture.</p>
        </div>
      </div>

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

      {record === null ? (
        <p className="panel-card padded">You have no onboarding in progress.</p>
      ) : (
        <>
          <p className={`chip ${record.state === "completed" ? "chip-approved" : record.state === "cancelled" ? "chip-rejected" : "chip-waiting"}`}>
            {STATE_LABEL[record.state] ?? record.state}
          </p>
          <ul className="rows" aria-label="Your checklist">
            {record.steps.map((step) => (
              <li key={step.id} className="item-row">
                <span className="stacked grow">
                  <span>{step.label}</span>
                  <span className="muted small">{step.who}</span>
                </span>
                <span className={`chip ${step.state === "done" ? "chip-approved" : step.state === "not_needed" ? "chip-rejected" : "chip-waiting"}`}>
                  {step.state_name}
                </span>
              </li>
            ))}
          </ul>
          {record.state === "in_progress" && record.steps.some((s) => s.code === "documents" && s.state === "open") && (
            <>
              <MyDocumentUpload onboardingId={record.id} onSaved={load} />
              <div className="actions">
                <button type="button" onClick={submitDocuments}>
                  I have uploaded everything asked for
                </button>
              </div>
            </>
          )}
          {record.state === "completed" && <p className="notice good">Your staff record is now active. Welcome!</p>}
        </>
      )}
    </>
  );
}
