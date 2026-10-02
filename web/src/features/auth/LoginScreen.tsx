import { useState, type FormEvent } from "react";
import { ApiError, post } from "../../api/client";
import type { Me } from "../../api/types";

interface Props {
  onSignedIn: (me: Me) => void;
  /** Why the person is seeing this page again, for example after an idle time-out. */
  notice?: string | null;
  /** Filled in for them, for example after choosing a password from an emailed link. */
  username?: string;
  onForgotPassword?: () => void;
  /** For someone shown a letter from the School, who has no account. */
  onCheckLetter?: () => void;
}

/** Login, then TOTP verification for privileged roles (with first-time enrolment). */
export function LoginScreen({ onSignedIn, notice, username: knownUsername = "", onForgotPassword, onCheckLetter }: Props) {
  const [username, setUsername] = useState(knownUsername);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"credentials" | "mfa">("credentials");
  const [provisioning, setProvisioning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitCredentials(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await post<Me>("/auth/login/", { username, password });
      if (me.mfa_required && !me.mfa_verified) {
        setStage("mfa");
        try {
          const enrol = await post<{ provisioning_uri: string }>("/auth/mfa/enrol/");
          setProvisioning(enrol.provisioning_uri);
        } catch (err) {
          if (!(err instanceof ApiError && err.code === "already_enrolled")) throw err;
        }
      } else {
        onSignedIn(me);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await post<Me>("/auth/mfa/verify/", { code }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="card" onSubmit={stage === "credentials" ? submitCredentials : submitCode}>
        <h1>GSA HRMS</h1>
        <p className="muted">Guyana School of Agriculture, Human Resource Management System</p>
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        {stage === "credentials" ? (
          <>
            <label>
              Username
              <input
                id="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                required
              />
            </label>
            <label>
              Password
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
          </>
        ) : (
          <>
            {provisioning && (
              <p className="notice">
                First sign-in with a privileged role: add this account to your authenticator app, then enter the
                six-digit code. <code className="wrap">{provisioning}</code>
              </p>
            )}
            <label>
              Authenticator code
              <input
                id="mfa-code"
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]*"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoFocus
                required
              />
            </label>
          </>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {stage === "credentials" ? "Sign in" : "Verify"}
        </button>
        {stage === "credentials" && onForgotPassword && (
          <button type="button" className="link" onClick={onForgotPassword}>
            Forgot your password?
          </button>
        )}
        {stage === "credentials" && onCheckLetter && (
          <button type="button" className="link" onClick={onCheckLetter}>
            Shown a letter from the School? Check it is genuine
          </button>
        )}
      </form>
    </div>
  );
}
