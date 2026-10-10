import { useState, type FormEvent } from "react";
import { ApiError, post } from "../../api/client";
import type { CheckedApplication } from "../../api/types";
import { AuthFrame } from "../auth/AuthFrame";

/**
 * A candidate holds no account in this system (the build plan's own default, repeated in the pull
 * request): they check their application the way anyone checks a letter is genuine (item 1.47) — a
 * reference and a code, both given at submission, typed in here without signing in.
 */
export function ApplicationStatusScreen({ onBack }: { onBack: () => void }) {
  const [reference, setReference] = useState("");
  const [code, setCode] = useState("");
  const [answer, setAnswer] = useState<CheckedApplication | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function check(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await post<CheckedApplication>("/recruitment/check/", { reference, code }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the School's server. Try again later.");
    } finally {
      setBusy(false);
    }
  }

  const found = answer?.found ? answer : null;
  return (
    <AuthFrame>
      <section className="card wide" aria-labelledby="status-heading">
        <h1>GSA HRMS</h1>
        <h2 id="status-heading">Check your application</h2>
        <p className="muted">
          Enter the reference and the code from the email the Guyana School of Agriculture sent when you
          applied.
        </p>
        <form className="stack" onSubmit={check} aria-label="Check an application">
          <div className="grid2">
            <label>
              Reference
              <input
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                placeholder="GSA-APP-XXXX-XXXX"
                autoCapitalize="characters"
                spellCheck={false}
                maxLength={40}
                required
              />
            </label>
            <label>
              Code
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="XXXX-XXXX-XXXX"
                autoCapitalize="characters"
                autoComplete="off"
                spellCheck={false}
                maxLength={40}
                required
              />
            </label>
          </div>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Check my application
            </button>
          </div>
        </form>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {answer && !answer.found && (
          <p role="alert" className="notice bad">
            {answer.detail}
          </p>
        )}
        {found && (
          <p role="status" className="notice good">
            {found.vacancy}: <strong>{found.state_label}</strong>. Reference {found.reference}.
          </p>
        )}
        <button type="button" className="link" onClick={onBack}>
          Go to the sign-in page
        </button>
      </section>
    </AuthFrame>
  );
}
