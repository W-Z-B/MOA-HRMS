import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import type { Classification, Employee, Letter, LetterPreview, LetterTemplate } from "../../api/types";
import { Paper } from "./Paper";

const FILED_AS: Record<Classification, string> = {
  internal: "Internal",
  confidential: "Confidential",
  medical: "Medical",
};

/** A letter written for something on file: its template, its answers, and the career change it is for, if any. */
export interface LetterPreset {
  code: string;
  answers: Record<string, string>;
  careerEvent?: number;
  title: string;
}

interface Props {
  employee: Employee;
  onIssued: () => void;
  preset?: LetterPreset;
  onClose?: () => void;
  /** Opened from the file's own "Write a letter" (item 2.30): the form is open from the start. */
  startOpen?: boolean;
}

/** Write a letter to one member of staff from a template: read it, see what it lacks, then issue it (item 1.19). */
export function WriteLetter({ employee, onIssued, preset, onClose, startOpen = false }: Props) {
  const [open, setOpen] = useState(preset !== undefined || startOpen);
  const [templates, setTemplates] = useState<LetterTemplate[] | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<LetterPreview | null>(null);
  const [issued, setIssued] = useState<Letter | null>(null);
  const [ask, setAsk] = useState<"" | "acknowledge" | "accept">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || templates !== null) return;
    getAll<LetterTemplate>("/letters/templates/")
      .then((all) => {
        const active = all.filter((t) => t.is_active);
        setTemplates(active);
        if (!preset) return;
        // A change's letter opens on its template, with the change's answers filled in.
        const chosen = active.find((t) => t.code === preset.code);
        if (!chosen) {
          setError(`No letter template is in use for ${preset.title}.`);
          return;
        }
        setTemplateId(String(chosen.id));
        setAnswers(Object.fromEntries(chosen.asks.map((ask) => [ask.key, preset.answers[ask.key] ?? ""])));
      })
      .catch((err) => setError(errorMessage(err, "Could not load the letter templates.")));
  }, [open, templates, preset]);

  const template = templates?.find((t) => String(t.id) === templateId) ?? null;
  const letter = () => ({
    employee: employee.id,
    template: Number(templateId),
    answers,
    ...(preset?.careerEvent ? { career_event: preset.careerEvent } : {}),
    ...(ask ? { ask } : {}),
  });
  const close = () => (onClose ? onClose() : setOpen(false));

  // Any change means reading the letter again: what is issued is always what was read.
  function choose(id: string) {
    setTemplateId(id);
    setAnswers({});
    setPreview(null);
    setError(null);
  }
  function answer(key: string, value: string) {
    setAnswers({ ...answers, [key]: value });
    setPreview(null);
  }

  async function read(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setIssued(null);
    try {
      setPreview(await post<LetterPreview>("/letters/preview/", letter()));
    } catch (err) {
      setError(errorMessage(err, "Could not set out the letter."));
    } finally {
      setBusy(false);
    }
  }

  async function issue() {
    setBusy(true);
    setError(null);
    try {
      setIssued(await post<Letter>("/letters/", letter()));
      if (!preset) choose("");
      else setPreview(null);
      onIssued();
    } catch (err) {
      setError(errorMessage(err, "The letter was not issued."));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <div className="actions">
        <button className="secondary" onClick={() => setOpen(true)}>
          Write a letter
        </button>
      </div>
    );

  return (
    <section className="sub-form stack" aria-labelledby="write-letter-heading">
      <h3 id="write-letter-heading">{preset ? `Write the letter for ${preset.title}` : "Write a letter"}</h3>
      {issued && (
        <p role="status" className="notice good">
          {issued.template_name} {issued.reference} is issued and filed with the documents.{" "}
          <a href={issued.download_url}>Download it</a>
        </p>
      )}
      <form className="stack" onSubmit={read} aria-label="Write a letter">
        <label>
          Letter
          <select value={templateId} onChange={(e) => choose(e.target.value)} required>
            <option value="">{templates === null ? "Loading…" : "Choose"}</option>
            {(templates ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {template?.asks.map((ask) => (
          <label key={ask.key}>
            {ask.label}
            <input
              type={ask.type === "date" ? "date" : "text"}
              value={answers[ask.key] ?? ""}
              onChange={(e) => answer(ask.key, e.target.value)}
            />
          </label>
        ))}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="submit" className="secondary" disabled={busy || template === null}>
            Read the letter
          </button>
          <button type="button" className="link" onClick={close}>
            Close
          </button>
        </div>
      </form>
      {preview && (
        <>
          {preview.missing.length > 0 ? (
            <div className="missing">
              <p>
                <strong>Before it can be issued</strong>
              </p>
              <ul>
                {preview.missing.map((m) => (
                  <li key={m.key}>{m.asked ? `Answer: ${m.label}` : `The staff record has no ${m.label.toLowerCase()}`}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="muted small">
              It is filed as {FILED_AS[preview.classification]} with the documents, and {employee.first_name} can read it
              under My contract.
            </p>
          )}
          <Paper letter={preview} />
          <label>
            Once it is issued, ask {employee.first_name} to
            <select value={ask} onChange={(e) => setAsk(e.target.value as typeof ask)}>
              <option value="">Nothing more</option>
              <option value="acknowledge">Acknowledge receiving it</option>
              <option value="accept">Accept it</option>
            </select>
          </label>
          <div className="actions">
            <button onClick={issue} disabled={busy || preview.missing.length > 0}>
              Issue the letter
            </button>
          </div>
        </>
      )}
    </section>
  );
}
