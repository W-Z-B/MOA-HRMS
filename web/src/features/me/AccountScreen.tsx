import { useCallback, useEffect, useState } from "react";
import { get, plainMessage, post, remove } from "../../api/client";
import type { SignedInSession } from "../../api/types";
import { dmyTime } from "../../app/format";

/** Where the person is signed in, with a way to end any session they do not recognise. */
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
    </>
  );
}
