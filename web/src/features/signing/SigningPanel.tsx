import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import {
  HR_ROLES,
  LETTER_ROLES,
  hasAnyRole,
  type Employee,
  type EmployeeDocument,
  type Me,
  type SignatureKind,
  type SignatureRequest,
} from "../../api/types";
import { dmy } from "../../app/format";
import { Evidence } from "./Evidence";

function AskForm({ employee, documents, onAsked }: { employee: Employee; documents: EmployeeDocument[]; onAsked: () => void }) {
  const [open, setOpen] = useState(false);
  const [document, setDocument] = useState("");
  const [kind, setKind] = useState<SignatureKind>("acknowledge");
  const [message, setMessage] = useState("");
  const [due, setDue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const signable = documents.filter((d) => d.classification !== "medical");

  async function ask(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post("/signing/requests/", { document: Number(document), kind, message, due_by: due || null });
      setOpen(false);
      setDocument("");
      setMessage("");
      setDue("");
      onAsked();
    } catch (err) {
      setError(errorMessage(err, "The request was not sent."));
    }
  }

  if (!open)
    return (
      <div className="actions">
        <button className="secondary" onClick={() => setOpen(true)} disabled={signable.length === 0}>
          Ask {employee.first_name} to sign a document
        </button>
      </div>
    );

  return (
    <form className="stack sub-form" onSubmit={ask} aria-label="Ask to sign">
      <div className="grid2">
        <label>
          Document
          <select value={document} onChange={(e) => setDocument(e.target.value)} required>
            <option value="">Choose</option>
            {signable.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ask them to
          <select value={kind} onChange={(e) => setKind(e.target.value as SignatureKind)}>
            <option value="acknowledge">Acknowledge receiving it</option>
            <option value="accept">Accept it</option>
          </select>
        </label>
        <label>
          By (optional)
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </label>
        <label>
          Note to them (optional)
          <input value={message} onChange={(e) => setMessage(e.target.value)} maxLength={300} />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Send the request</button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** Who was asked to sign what in this file, and the evidence of each signature (item 1.20). */
export function SigningPanel({
  employee,
  documents,
  me,
  version,
}: {
  employee: Employee;
  documents: EmployeeDocument[];
  me: Me;
  version: number;
}) {
  const [requests, setRequests] = useState<SignatureRequest[] | null>(null);
  const [withdrawing, setWithdrawing] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reads = hasAnyRole(me, LETTER_ROLES);
  const isHr = hasAnyRole(me, HR_ROLES);

  const load = useCallback(() => {
    if (!reads) return;
    getAll<SignatureRequest>(`/signing/requests/?employee=${employee.id}`)
      .then(setRequests)
      .catch((err) => setError(errorMessage(err, "Could not load the signatures.")));
  }, [employee.id, reads]);
  useEffect(load, [load, version]);

  async function withdraw(e: FormEvent, request: SignatureRequest) {
    e.preventDefault();
    try {
      await post(`/signing/requests/${request.id}/withdraw/`, { reason });
      setWithdrawing(null);
      setReason("");
      setNotice(`The request for ${request.document_title} is withdrawn.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "The request was not withdrawn."));
    }
  }

  if (!reads) return null;

  return (
    <section className="stack" aria-labelledby="signatures-heading">
      <h3 id="signatures-heading">Signatures</h3>
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
      {requests !== null && requests.length === 0 && <p className="muted">Nobody has been asked to sign anything here.</p>}
      {requests !== null && requests.length > 0 && (
        <ul className="plain accounts" aria-label="Signature requests">
          {requests.map((r) => (
            <li key={r.id} className={`signature-${r.state}`}>
              <div>
                <strong>{r.document_title}</strong> <span className="chip">{r.kind_name}</span>{" "}
                <span className={`chip chip-signature-${r.state}`}>{r.state_name}</span>
                <br />
                <span className="muted small">
                  Asked {dmy(r.created_at)}
                  {r.requested_by ? ` by ${r.requested_by}` : ""}
                  {r.due_by ? `, by ${dmy(r.due_by)}` : ""}
                  {r.decline_reason ? ` · declined: ${r.decline_reason}` : ""}
                </span>
              </div>
              {r.evidence && <Evidence evidence={r.evidence} />}
              {isHr && r.state === "waiting" && withdrawing !== r.id && (
                <div className="actions">
                  <button className="link" onClick={() => setWithdrawing(r.id)}>
                    Withdraw the request
                  </button>
                </div>
              )}
              {withdrawing === r.id && (
                <form className="stack" onSubmit={(e) => withdraw(e, r)} aria-label={`Withdraw the request for ${r.document_title}`}>
                  <label>
                    Why
                    <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
                  </label>
                  <div className="actions">
                    <button type="submit" className="secondary">
                      Withdraw it
                    </button>
                    <button type="button" className="link" onClick={() => setWithdrawing(null)}>
                      Keep it
                    </button>
                  </div>
                </form>
              )}
            </li>
          ))}
        </ul>
      )}
      {isHr && employee.status !== "separated" && (
        <AskForm
          employee={employee}
          documents={documents}
          onAsked={() => {
            setNotice(`${employee.first_name} is asked to sign, and is told.`);
            load();
          }}
        />
      )}
    </section>
  );
}
