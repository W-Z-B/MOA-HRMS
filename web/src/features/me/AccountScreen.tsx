import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, get, plainMessage, post, remove } from "../../api/client";
import type { SignedInSession } from "../../api/types";
import { dmyTime } from "../../app/format";
import { PASSWORD_RULES } from "../auth/SetPasswordScreen";
import { EmailSection } from "./EmailSection";

/** Where the person is signed in, with a way to end any session they do not recognise, and their password. */
export function AccountScreen() {
  const [sessions, setSessions] = useState<SignedInSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get<SignedInSession[]>("/auth/sessions/")
      .then((rows) => {
        setSessions(rows);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load where you are signed in.")));
  }, []);

  useEffect(load, [load]);

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setNotice(null);
    try {
      setNotice(await work());
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    } finally {
      setBusy(false);
    }
  }

  const endOne = (session: SignedInSession) =>
    run(async () => {
      await remove(`/auth/sessions/${session.id}/`);
      return `Signed out of ${session.device}.`;
    });

  const endOthers = () =>
    run(async () => {
      const { ended } = await post<{ ended: number }>("/auth/sessions/end-others/");
      return ended === 1 ? "Signed out of 1 other device." : `Signed out of ${ended} other devices.`;
    });

  const others = sessions?.filter((s) => !s.current) ?? [];

  return (
    <>
      <h1>My account</h1>
      <section className="card-block stack" aria-labelledby="sessions-heading">
        <h2 id="sessions-heading">Where you are signed in</h2>
        <p className="muted">
          For your security you are signed out after 30 minutes without activity, and after 8 hours in any case. If
          you see a device you do not recognise, sign it out and tell Human Resources.
        </p>
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
        {sessions === null && !error && <p className="loading">Loading…</p>}
        {sessions && (
          <ul className="plain sessions">
            {sessions.map((s) => (
              <li key={s.id}>
                <div>
                  <strong>{s.device}</strong>
                  {s.current && <span className="chip chip-approved">This device</span>}
                  <br />
                  <span className="muted small">
                    Signed in {dmyTime(s.created_at)} · last active {dmyTime(s.last_seen_at)}
                    {s.ip ? ` · ${s.ip}` : ""}
                  </span>
                </div>
                {!s.current && (
                  <button
                    className="secondary"
                    aria-label={`Sign out of ${s.device}`}
                    disabled={busy}
                    onClick={() => endOne(s)}
                  >
                    Sign out
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {others.length > 0 && (
          <div className="actions">
            <button disabled={busy} onClick={endOthers}>
              Sign out everywhere else
            </button>
          </div>
        )}
      </section>
      <PasswordSection onChanged={load} />
      <EmailSection />
    </>
  );
}

/** Change the password, knowing the current one. The other devices are signed out; this one stays. */
function PasswordSection({ onChanged }: { onChanged: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setNotice(null);
    if (next !== repeat) {
      setProblems(["The two new passwords are not the same."]);
      return;
    }
    setBusy(true);
    setProblems([]);
    try {
      const { ended } = await post<{ ended: number }>("/auth/password/change/", {
        current_password: current,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setRepeat("");
      setNotice(
        ended === 0
          ? "Your password is changed."
          : `Your password is changed. You were signed out on ${ended === 1 ? "1 other device" : `${ended} other devices`}.`,
      );
      onChanged();
    } catch (err) {
      setProblems(
        err instanceof ApiError && err.fields
          ? Object.values(err.fields).flat()
          : [plainMessage(err, "Your password was not changed. Try again.")],
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card-block" aria-labelledby="password-heading">
      <h2 id="password-heading">Your password</h2>
      <form className="stack" onSubmit={submit}>
        <p className="muted small" id="change-rules">
          {PASSWORD_RULES} Changing it signs you out on your other devices.
        </p>
        <label>
          Current password
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </label>
        <label>
          New password
          <input
            type="password"
            autoComplete="new-password"
            aria-describedby="change-rules"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            minLength={12}
            required
          />
        </label>
        <label>
          New password again
          <input
            type="password"
            autoComplete="new-password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            required
          />
        </label>
        {problems.length > 0 && (
          <div role="alert" className="error">
            {problems.map((problem) => (
              <p key={problem}>{problem}</p>
            ))}
          </div>
        )}
        {notice && (
          <p role="status" className="notice good">
            {notice}
          </p>
        )}
        <div className="actions">
          <button type="submit" disabled={busy}>
            Change password
          </button>
        </div>
      </form>
    </section>
  );
}
