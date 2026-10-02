import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import type { SignatureRequest } from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

function SignForm({ request, onDone }: { request: SignatureRequest; onDone: (message: string) => void }) {
  const [agree, setAgree] = useState(false);
  const [password, setPassword] = useState("");
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sign(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(`/signing/mine/${request.id}/sign/`, { password, agree });
      onDone(`Signed: ${request.document_title}.`);
    } catch (err) {
      setPassword("");
      setError(errorMessage(err, "It was not signed."));
    } finally {
      setBusy(false);
    }
  }

  async function decline(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post(`/signing/mine/${request.id}/decline/`, { reason });
      onDone(`Declined: ${request.document_title}. Human Resources is told why.`);
    } catch (err) {
      setError(errorMessage(err, "That was not recorded."));
    }
  }

  return (
    <div className="stack">
      {!declining ? (
        <form className="stack" onSubmit={sign} aria-label={`Sign ${request.document_title}`}>
          <label className="inline">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> {request.statement}
          </label>
          <label>
            Your password, to confirm it is you
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button type="submit" disabled={busy || !agree}>
              Sign
            </button>
            <button type="button" className="link" onClick={() => setDeclining(true)}>
              Decline
            </button>
          </div>
        </form>
      ) : (
        <form className="stack" onSubmit={decline} aria-label={`Decline ${request.document_title}`}>
          <label>
            Why you do not agree
            <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button type="submit" className="secondary">
              Decline to sign
            </button>
            <button type="button" className="link" onClick={() => setDeclining(false)}>
              Back
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

/** What I am asked to sign, and what I have signed (item 1.20). */
export function MySignatures() {
  const [requests, setRequests] = useState<SignatureRequest[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    getAll<SignatureRequest>("/signing/mine/")
      .then(setRequests)
      .catch(() => setRequests([]));
  }, []);
  useEffect(load, [load]);

  if (requests === null || (requests.length === 0 && !notice)) return null;
  const waiting = requests.filter((r) => r.state === "waiting");
  const done = requests.filter((r) => r.state !== "waiting");

  return (
    <section className="card-block" aria-labelledby="to-sign-heading">
      <h2 id="to-sign-heading">{waiting.length > 0 ? "Waiting for your signature" : "Signatures"}</h2>
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {waiting.length > 0 && (
        <ul className="plain" aria-label="Waiting for your signature">
          {waiting.map((r) => (
            <li key={r.id} className="stack">
              <div>
                <a href={r.download_url}>{r.document_title}</a> <span className="chip">{r.kind_name}</span>
                <br />
                <span className="muted small">
                  Asked {dmy(r.created_at)}
                  {r.requested_by ? ` by ${r.requested_by}` : ""}
                  {r.due_by ? `, by ${dmy(r.due_by)}` : ""}
                  {r.message ? `: ${r.message}` : ""}
                </span>
              </div>
              <p className="muted small">Read it first: open it with the link above.</p>
              <SignForm
                request={r}
                onDone={(message) => {
                  setNotice(message);
                  load();
                }}
              />
            </li>
          ))}
        </ul>
      )}
      {done.length > 0 && (
        <ul className="plain" aria-label="Signed or declined">
          {done.map((r) => (
            <li key={r.id}>
              <a href={r.download_url}>{r.document_title}</a>{" "}
              <span className="muted small">
                {r.state === "signed" && r.evidence ? `signed ${dmyTime(r.evidence.signed_at)}` : r.state_name.toLowerCase()}
                {r.decline_reason ? `: ${r.decline_reason}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
