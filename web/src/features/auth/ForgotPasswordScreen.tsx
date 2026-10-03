import { useState, type FormEvent } from "react";
import { ApiError, post } from "../../api/client";
import { AuthFrame } from "./AuthFrame";

interface Props {
  onBack: () => void;
}

/**
 * Ask for a link to choose a new password. The answer is the same whether or not the account exists, so
 * the page never tells anyone who has an account.
 */
export function ForgotPasswordScreen({ onBack }: Props) {
  const [login, setLogin] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const answer = await post<{ detail: string }>("/auth/password/forgot/", { login });
      setSent(answer.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <form className="card" onSubmit={submit} aria-labelledby="forgot-heading">
        <h1>GSA HRMS</h1>
        <h2 id="forgot-heading">Forgot your password?</h2>
        {sent ? (
          <p role="status" className="notice good">
            {sent}
          </p>
        ) : (
          <>
            <p className="muted">
              Give your username or the email address Human Resources has for you, and we will email you a link to
              choose a new password. If you have no email address on file, ask Human Resources.
            </p>
            <label>
              Username or email address
              <input
                id="forgot-login"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                autoFocus
                required
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button type="submit" disabled={busy}>
              Email me a link
            </button>
          </>
        )}
        <button type="button" className="link" onClick={onBack}>
          Back to sign in
        </button>
      </form>
    </AuthFrame>
  );
}
