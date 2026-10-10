import { useState, type FormEvent } from "react";
import { ApiError, post } from "../../api/client";
import type { Me } from "../../api/types";
import { AuthFrame } from "./AuthFrame";

interface Props {
  onSignedIn: (me: Me) => void;
  /** Why the person is seeing this page again, for example after an idle time-out. */
  notice?: string | null;
  /** Filled in for them, for example after choosing a password from an emailed link. */
  username?: string;
  onForgotPassword?: () => void;
  /** For someone shown a letter from the School, who has no account. */
  onCheckLetter?: () => void;
  /** For a candidate checking their application, who holds no account either (item H-W01). */
  onCheckApplication?: () => void;
}

/** Password first, then the 6-digit code from an authenticator app for roles that need one (with first-time enrolment). */
export function LoginScreen({
  onSignedIn,
  notice,
  username: knownUsername = "",
  onForgotPassword,
  onCheckLetter,
  onCheckApplication,
}: Props) {
  const [username, setUsername] = useState(knownUsername);
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
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

  function startAgain() {
    post("/auth/logout/").catch(() => undefined); // the half-finished sign-in ends here
    setStage("credentials");
    setCode("");
    setPassword("");
    setProvisioning(null);
    setError(null);
  }

  return (
    <AuthFrame>
      <form className="card" onSubmit={stage === "credentials" ? submitCredentials : submitCode}>
        <h1 className="card-eyebrow">GSA HRMS</h1>
        {stage === "credentials" ? (
          <div className="stacked">
            <h2>Sign in</h2>
            <p className="muted">Use your GSA staff account.</p>
          </div>
        ) : (
          <div className="stacked">
            <h2>Enter your code</h2>
            <p className="muted">Open the authenticator app on your phone and type the 6-digit code it shows for GSA HRMS.</p>
          </div>
        )}
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
            {/* The Show button sits outside the label, so the field is named "Password" alone. */}
            <div className="field">
              <label htmlFor="password">Password</label>
              <span className="password-field">
                <input
                  id="password"
                  type={shown ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="reveal"
                  aria-pressed={shown}
                  aria-label={shown ? "Hide password" : "Show password"}
                  onClick={() => setShown(!shown)}
                >
                  {shown ? "Hide" : "Show"}
                </button>
              </span>
            </div>
          </>
        ) : (
          <>
            {provisioning && (
              <p className="notice">
                First sign-in with a role that needs a code: add this account to your authenticator app, then enter the
                6-digit code it shows. <code className="wrap">{provisioning}</code>
              </p>
            )}
            <label>
              6-digit code
              <input
                id="mfa-code"
                className="code-input"
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={8}
                placeholder="000000"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
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
        <button type="submit" className="wide" disabled={busy}>
          Sign in
        </button>
        {stage === "credentials" && onForgotPassword && (
          <button type="button" className="link accent" onClick={onForgotPassword}>
            Forgot your password?
          </button>
        )}
        {stage === "mfa" && (
          <button type="button" className="link accent" onClick={startAgain}>
            Use a different account
          </button>
        )}
        {stage === "credentials" && onCheckLetter && (
          <p className="card-foot">
            Shown a letter from the School?{" "}
            <button type="button" className="link accent" onClick={onCheckLetter}>
              Check that it is genuine
            </button>
          </p>
        )}
        {stage === "credentials" && onCheckApplication && (
          <p className="card-foot">
            Applied for a post here?{" "}
            <button type="button" className="link accent" onClick={onCheckApplication}>
              Check your application
            </button>
          </p>
        )}
      </form>
    </AuthFrame>
  );
}
