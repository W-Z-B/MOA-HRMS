import { useState, type ChangeEvent, type FormEvent } from "react";
import { ApiError, post } from "../../api/client";
import type { CheckedLetter } from "../../api/types";
import { dmy } from "../../app/format";
import { Paper } from "./Paper";
import { AuthFrame } from "../auth/AuthFrame";

/** The SHA-256 fingerprint of a file, worked out in the browser: the file never leaves the device. */
async function fingerprintOf(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

const FILE_VERDICTS = {
  same: { good: true, text: "This file is exactly the one the School issued." },
  different: { good: false, text: "This file is not the one the School issued: it may have been changed. Rely on the words above." },
  unreadable: { good: false, text: "That file could not be read here. Compare the words instead." },
} as const;

/**
 * Item 1.47: a bank, an embassy or an employer shown a letter checks it is genuine, by the reference and the
 * code at its foot, without signing in. The answer shows the letter as issued, to compare with the one in hand.
 */
export function CheckLetterScreen({ onBack }: { onBack: () => void }) {
  const [reference, setReference] = useState("");
  const [code, setCode] = useState("");
  const [answer, setAnswer] = useState<CheckedLetter | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [verdict, setVerdict] = useState<keyof typeof FILE_VERDICTS | null>(null);

  async function check(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setAnswer(null);
    setVerdict(null);
    try {
      setAnswer(await post<CheckedLetter>("/letters/check/", { reference, code }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the School's server. Try again later.");
    } finally {
      setBusy(false);
    }
  }

  async function compare(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !answer?.sha256) return;
    try {
      setVerdict((await fingerprintOf(file)) === answer.sha256 ? "same" : "different");
    } catch {
      setVerdict("unreadable");
    }
  }

  const genuine = answer?.genuine ? answer : null;
  return (
    <AuthFrame>
      <section className="card wide" aria-labelledby="check-heading">
        <h1>GSA HRMS</h1>
        <h2 id="check-heading">Check a letter from the School</h2>
        <p className="muted">
          Enter the reference and the code printed at the foot of the letter. If it is genuine you will see it as the
          Guyana School of Agriculture issued it, to compare with the one you were shown.
        </p>
        <form className="stack" onSubmit={check} aria-label="Check a letter">
          <div className="grid2">
            <label>
              Reference
              <input
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                placeholder="GSA/HR/2026/0001"
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
              Check the letter
            </button>
          </div>
        </form>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {answer && !answer.genuine && (
          <p role="alert" className="notice bad">
            {answer.detail}
          </p>
        )}
        {genuine && (
          <section className="stack" aria-label="The letter as issued">
            <p role="status" className="notice good">
              Genuine: {genuine.letter} {genuine.reference}, about {genuine.about}, issued on {dmy(genuine.issued_on)}.
              Compare its words with the letter you hold.
            </p>
            <Paper
              letter={{
                subject: genuine.subject ?? "",
                addressed: Boolean(genuine.addressed),
                blocks: genuine.blocks ?? [],
                values: genuine.values ?? {},
              }}
            />
            <label>
              Sent the letter as a PDF file? Choose it to check it is the very file issued
              <input type="file" accept="application/pdf,.pdf" onChange={compare} />
            </label>
            {verdict && (
              <p role="status" className={`notice ${FILE_VERDICTS[verdict].good ? "good" : "bad"}`}>
                {FILE_VERDICTS[verdict].text}
              </p>
            )}
          </section>
        )}
        <button type="button" className="link" onClick={onBack}>
          Go to the sign-in page
        </button>
      </section>
    </AuthFrame>
  );
}
