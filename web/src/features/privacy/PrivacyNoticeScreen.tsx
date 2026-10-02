import { useEffect, useState } from "react";
import { ApiError, post, get } from "../../api/client";
import type { CurrentNotice, PrivacyNotice } from "../../api/types";
import { dmy } from "../../app/format";

/** The notice as paragraphs: a blank line in the text starts a new one. */
export function NoticeText({ notice }: { notice: PrivacyNotice }) {
  return (
    <>
      {notice.body
        .split(/\n\s*\n/)
        .map((paragraph) => paragraph.trim())
        .filter(Boolean)
        .map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
      <p className="muted small">
        Version {notice.version}
        {notice.published_at ? `, in force from ${dmy(notice.published_at)}` : ", draft"}
      </p>
    </>
  );
}

interface Props {
  onAcknowledged: () => void;
  onSignOut: () => void;
}

/**
 * Shown after sign-in until the person has read the privacy notice in force (item 1.31). Their reading
 * is recorded, once for each version.
 */
export function PrivacyNoticeScreen({ onAcknowledged, onSignOut }: Props) {
  const [notice, setNotice] = useState<PrivacyNotice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<CurrentNotice>("/privacy/notice/")
      .then((current) => {
        if (current.notice === null || current.acknowledged) onAcknowledged();
        else setNotice(current.notice);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Could not reach the server."));
  }, [onAcknowledged]);

  async function acknowledge() {
    if (!notice) return;
    setBusy(true);
    setError(null);
    try {
      await post<CurrentNotice>("/privacy/notice/acknowledge/", { version: notice.version });
      onAcknowledged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <section className="card notice-card" aria-labelledby="notice-heading">
        <h1>GSA HRMS</h1>
        <h2 id="notice-heading">{notice?.title ?? "Privacy notice"}</h2>
        {notice === null && error === null && <p className="loading">Loading the notice…</p>}
        {notice !== null && <NoticeText notice={notice} />}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {notice !== null && (
          <button type="button" disabled={busy} onClick={acknowledge}>
            I have read this notice
          </button>
        )}
        <button type="button" className="link" onClick={onSignOut}>
          Sign out
        </button>
      </section>
    </div>
  );
}
