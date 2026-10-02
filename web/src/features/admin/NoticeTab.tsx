import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, plainMessage, post } from "../../api/client";
import { NOTICE_WRITE_ROLES, hasAnyRole, type Me, type Paginated, type PrivacyNotice } from "../../api/types";
import { dmyTime } from "../../app/format";
import { NoticeText } from "../privacy/PrivacyNoticeScreen";

/**
 * Versions of the privacy notice (item 1.31). A draft is written and checked, then published; everyone
 * reads the new version at their next sign-in. A published version never changes.
 */
export function NoticeTab({ me }: { me: Me }) {
  const [notices, setNotices] = useState<PrivacyNotice[] | null>(null);
  const [editing, setEditing] = useState<PrivacyNotice | "new" | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, NOTICE_WRITE_ROLES);

  const load = useCallback(() => {
    get<Paginated<PrivacyNotice>>("/privacy/notices/")
      .then((page) => setNotices(page.results))
      .catch((err) => setError(errorMessage(err, "Could not load the notices.")));
  }, []);

  useEffect(load, [load]);

  function open(draft: PrivacyNotice | "new") {
    setEditing(draft);
    setTitle(draft === "new" ? "" : draft.title);
    setBody(draft === "new" ? "" : draft.body);
    setNotice(null);
  }

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    } finally {
      setBusy(false);
    }
  }

  function save(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      if (editing === "new") await post("/privacy/notices/", { title, body });
      else if (editing) await patch(`/privacy/notices/${editing.id}/`, { title, body });
      setEditing(null);
      return "Draft saved. Publish it when it is ready.";
    });
  }

  const publish = (draft: PrivacyNotice) =>
    run(async () => {
      await post(`/privacy/notices/${draft.id}/publish/`);
      return `Version ${draft.version} is in force. Everyone reads it at their next sign-in.`;
    });

  const inForce = notices?.find((n) => n.published_at !== null) ?? null;

  return (
    <section aria-labelledby="notice-tab-heading">
      <h2 id="notice-tab-heading" className="sr-only">
        Privacy notice
      </h2>
      <p className="muted">
        The notice tells staff what the system holds about them, why, who sees it, how long it is kept and their
        rights. A starting draft for GSA to complete is in the project documents (docs/privacy).
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
      {mayWrite && editing === null && (
        <div className="actions">
          <button onClick={() => open("new")}>Write a new version</button>
        </div>
      )}
      {editing !== null && (
        <form className="card-block stack" onSubmit={save} aria-label="Privacy notice draft">
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
          </label>
          <label>
            Text (a blank line starts a new paragraph)
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={12} required />
          </label>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Save the draft
            </button>
          </div>
        </form>
      )}
      {notices !== null && notices.length === 0 && (
        <p className="notice">No notice yet. Until one is published, nobody is asked to read one.</p>
      )}
      {notices !== null &&
        notices.map((n) => (
          <section key={n.id} className="card-block" aria-label={`Version ${n.version}`}>
            <h3>
              {n.title}{" "}
              <span className={n === inForce ? "chip chip-approved" : "chip"}>
                {n === inForce ? "In force" : n.published_at ? "Replaced" : "Draft"}
              </span>
            </h3>
            <NoticeText notice={n} />
            <p className="muted small">
              {n.published_at
                ? `Published ${dmyTime(n.published_at)} by ${n.published_by ?? "someone no longer here"}.`
                : `Written ${dmyTime(n.created_at)}.`}
            </p>
            {mayWrite && n.published_at === null && editing === null && (
              <div className="actions">
                <button className="secondary" onClick={() => open(n)}>
                  Edit the draft
                </button>
                <button disabled={busy} onClick={() => publish(n)}>
                  Publish version {n.version}
                </button>
              </div>
            )}
          </section>
        ))}
    </section>
  );
}
