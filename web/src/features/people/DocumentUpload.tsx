import { useState, type FormEvent } from "react";
import { errorMessage, post } from "../../api/client";
import type { Employee } from "../../api/types";

// Classifications from the widest readership to the narrowest, and what each type needs at the least, as
// the server checks: a contract shows pay, an identity document the national ID, a medical paper health.
const RESTRICTION = ["internal", "confidential", "medical"];
const LEAST: Record<string, string> = { contract: "confidential", id_copy: "confidential", medical: "medical" };
const below = (classification: string, docType: string) =>
  RESTRICTION.indexOf(classification) < RESTRICTION.indexOf(LEAST[docType] ?? "internal");

/** Files a scanned or received document in the employee's record. */
export function DocumentUpload({ employee, onSaved }: { employee: Employee; onSaved: () => void }) {
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("letter");
  const [classification, setClassification] = useState("internal");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function chooseType(next: string) {
    setDocType(next);
    if (below(classification, next)) setClassification(LEAST[next]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.set("employee", String(employee.id));
    body.set("title", title);
    body.set("doc_type", docType);
    body.set("classification", classification);
    body.set("file", file);
    try {
      await post("/documents/", body);
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
    <form className="stack sub-form" onSubmit={submit} aria-label="File a document">
      <h3>File a document</h3>
      <label>
        Title
        <input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <div className="grid2">
        <label>
          Type
          <select id="doc-type" value={docType} onChange={(e) => chooseType(e.target.value)}>
            <option value="contract">Contract</option>
            <option value="certificate">Certificate</option>
            <option value="letter">Letter</option>
            <option value="id_copy">ID copy</option>
            <option value="medical">Medical</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          Classification
          <select id="doc-class" value={classification} onChange={(e) => setClassification(e.target.value)}>
            <option value="internal" disabled={below("internal", docType)}>
              Internal: anyone who reads staff files
            </option>
            <option value="confidential" disabled={below("confidential", docType)}>
              Confidential: HR, the Principal and the auditor
            </option>
            <option value="medical">Medical: the HR Manager and administrators</option>
          </select>
        </label>
      </div>
      <label>
        File
        <input id="doc-file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
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
