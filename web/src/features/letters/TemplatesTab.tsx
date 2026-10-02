import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage, get, getAll, post } from "../../api/client";
import {
  TEMPLATE_WRITE_ROLES,
  hasAnyRole,
  type Classification,
  type LetterAsk,
  type LetterFields,
  type LetterTemplate,
  type Me,
} from "../../api/types";

const KINDS: [string, string][] = [
  ["appointment", "Appointment"],
  ["confirmation", "Confirmation of appointment"],
  ["job_letter", "Job letter"],
  ["transfer", "Transfer"],
  ["promotion", "Promotion"],
  ["acting", "Acting appointment"],
  ["increment", "Increment"],
  ["exit", "Leaving"],
  ["other", "Other"],
];

interface Draft {
  code: string;
  kind: string;
  name: string;
  subject: string;
  body: string;
  asks: LetterAsk[];
  addressed: boolean;
  classification: Classification;
  signatory_name: string;
  signatory_title: string;
}

const EMPTY: Draft = {
  code: "",
  kind: "other",
  name: "",
  subject: "",
  body: "",
  asks: [],
  addressed: true,
  classification: "confidential",
  signatory_name: "",
  signatory_title: "Human Resources Manager",
};

const draftOf = (t: LetterTemplate): Draft => ({
  code: t.code,
  kind: t.kind,
  name: t.name,
  subject: t.subject,
  body: t.body,
  asks: t.asks.map((a) => ({ ...a })),
  addressed: t.addressed,
  classification: t.classification,
  signatory_name: t.signatory_name,
  signatory_title: t.signatory_title,
});

/** Every problem the server found with a template, not only the first: there are often several. */
function allProblems(err: unknown): string {
  if (err instanceof ApiError && err.fields) {
    return Object.entries(err.fields)
      .map(([field, messages]) => `${field.replace(/_/g, " ")}: ${[messages].flat().join(" ")}`)
      .join(" ");
  }
  return errorMessage(err, "The template was not saved.");
}

function TemplateForm({ editing, onDone }: { editing: LetterTemplate | null; onDone: (saved: LetterTemplate | null) => void }) {
  const [draft, setDraft] = useState<Draft>(editing ? draftOf(editing) : EMPTY);
  const [fields, setFields] = useState<LetterFields | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<LetterFields>("/letters/templates/fields/")
      .then(setFields)
      .catch(() => setFields(null));
  }, []);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft({ ...draft, [key]: value });
  const setAsk = (i: number, change: Partial<LetterAsk>) =>
    set(
      "asks",
      draft.asks.map((a, j) => (j === i ? { ...a, ...change } : a)),
    );

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = editing
        ? await post<LetterTemplate>(`/letters/templates/${editing.id}/revise/`, draft)
        : await post<LetterTemplate>("/letters/templates/", draft);
      onDone(saved);
    } catch (err) {
      setError(allProblems(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card-block stack" onSubmit={save} aria-label={editing ? `Change ${editing.name}` : "New letter template"}>
      <h3>{editing ? `Change ${editing.name}: it becomes version ${editing.version + 1}` : "New letter template"}</h3>
      <div className="grid2">
        <label>
          Name
          <input value={draft.name} onChange={(e) => set("name", e.target.value)} required />
        </label>
        <label>
          Kind
          <select value={draft.kind} onChange={(e) => set("kind", e.target.value)}>
            {KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {!editing && (
          <label>
            Code
            <input value={draft.code} onChange={(e) => set("code", e.target.value)} required placeholder="for example study_leave" />
          </label>
        )}
        <label>
          Filed as
          <select value={draft.classification} onChange={(e) => set("classification", e.target.value as Classification)}>
            <option value="internal">Internal: anyone who reads staff files</option>
            <option value="confidential">Confidential: HR, the Principal and the auditor</option>
            <option value="medical">Medical: the HR Manager and administrators</option>
          </select>
        </label>
      </div>
      <label>
        Subject
        <input value={draft.subject} onChange={(e) => set("subject", e.target.value)} required />
      </label>
      <label>
        Wording
        <textarea rows={12} value={draft.body} onChange={(e) => set("body", e.target.value)} required />
      </label>
      <p className="muted small">
        A blank line starts a new paragraph; lines that begin with a dash and a space make a list; **two stars** make
        words bold. A field is written with two braces each side, such as {"{{full_name}}"}.
      </p>
      {fields && (
        <details>
          <summary>Fields from the staff record</summary>
          <ul className="plain field-list">
            {fields.record.map((f) => (
              <li key={f.key}>
                <code>{`{{${f.key}}}`}</code> {f.label}
                {f.pay && <span className="muted small"> (pay: file the letter as Confidential)</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
      <fieldset className="stack">
        <legend>Asked when a letter is written</legend>
        {draft.asks.length === 0 && <p className="muted small">Nothing beyond the staff record.</p>}
        {draft.asks.map((ask, i) => (
          <div key={i} className="grid2 ask-row">
            <label>
              Field
              <input value={ask.key} onChange={(e) => setAsk(i, { key: e.target.value })} required placeholder="effective_date" />
            </label>
            <label>
              Question
              <input value={ask.label} onChange={(e) => setAsk(i, { label: e.target.value })} required />
            </label>
            <label>
              Answer
              <select value={ask.type} onChange={(e) => setAsk(i, { type: e.target.value as LetterAsk["type"] })}>
                <option value="text">Words</option>
                <option value="date">A date</option>
              </select>
            </label>
            <div className="actions">
              <button
                type="button"
                className="link"
                onClick={() =>
                  set(
                    "asks",
                    draft.asks.filter((_, j) => j !== i),
                  )
                }
              >
                Remove this question
              </button>
            </div>
          </div>
        ))}
        <div className="actions">
          <button type="button" className="secondary" onClick={() => set("asks", [...draft.asks, { key: "", label: "", type: "text" }])}>
            Add a question
          </button>
        </div>
      </fieldset>
      <label className="inline">
        <input type="checkbox" checked={draft.addressed} onChange={(e) => set("addressed", e.target.checked)} /> Addressed to
        the person, under the date (not for letters to whom it may concern)
      </label>
      <div className="grid2">
        <label>
          Signed by (name, if any)
          <input value={draft.signatory_name} onChange={(e) => set("signatory_name", e.target.value)} />
        </label>
        <label>
          Their title
          <input value={draft.signatory_title} onChange={(e) => set("signatory_title", e.target.value)} required />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          Save the template
        </button>
        <button type="button" className="link" onClick={() => onDone(null)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** The letter templates in use and out of use, each at its newest version (item 1.19). */
export function TemplatesTab({ me }: { me: Me }) {
  const [templates, setTemplates] = useState<LetterTemplate[] | null>(null);
  const [editing, setEditing] = useState<LetterTemplate | "new" | null>(null);
  const [reading, setReading] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, TEMPLATE_WRITE_ROLES);

  const load = useCallback(() => {
    getAll<LetterTemplate>("/letters/templates/")
      .then(setTemplates)
      .catch((err) => setError(errorMessage(err, "Could not load the templates.")));
  }, []);
  useEffect(load, [load]);

  async function setInUse(t: LetterTemplate, active: boolean) {
    setError(null);
    try {
      await post(`/letters/templates/${t.id}/in-use/`, { is_active: active });
      setNotice(active ? `${t.name} is back in use.` : `${t.name} is out of use: no new letter is written from it.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "That did not work."));
    }
  }

  function done(saved: LetterTemplate | null) {
    setEditing(null);
    if (saved) {
      setNotice(`${saved.name} saved as version ${saved.version}.`);
      load();
    }
  }

  return (
    <section aria-labelledby="templates-heading">
      <h2 id="templates-heading" className="sr-only">
        Letter templates
      </h2>
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
      {templates === null && !error && <p className="loading">Loading…</p>}
      {templates !== null && (
        <ul className="plain accounts" aria-label="Letter templates">
          {templates.map((t) => (
            <li key={t.id} className={t.is_active ? undefined : "state-switched_off"}>
              <div>
                <strong>{t.name}</strong> <span className="chip">{t.kind_name}</span>{" "}
                <span className="chip">version {t.version}</span>{" "}
                <span className="chip">{t.classification_name}</span>
                {!t.is_active && <span className="chip"> Out of use</span>}
                <br />
                <span className="muted small">{t.subject}</span>
              </div>
              {reading === t.id && (
                <div className="stack">
                  <pre className="template-body">{t.body}</pre>
                  {t.asks.length > 0 && (
                    <p className="muted small">Asks for: {t.asks.map((a) => a.label).join(", ")}.</p>
                  )}
                  <p className="muted small">
                    Signed: {[t.signatory_name, t.signatory_title].filter(Boolean).join(", ")}.
                  </p>
                </div>
              )}
              <div className="actions">
                <button
                  className="link"
                  aria-expanded={reading === t.id}
                  aria-label={`${reading === t.id ? "Hide" : "Read"} the wording of ${t.name}`}
                  onClick={() => setReading(reading === t.id ? null : t.id)}
                >
                  {reading === t.id ? "Hide the wording" : "Read the wording"}
                </button>
                {mayWrite && (
                  <>
                    <button className="link" aria-label={`Change ${t.name}`} onClick={() => setEditing(t)}>
                      Change
                    </button>
                    <button className="link" onClick={() => setInUse(t, !t.is_active)}>
                      {t.is_active ? `Take ${t.name} out of use` : `Put ${t.name} back in use`}
                    </button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {mayWrite && editing === null && (
        <div className="actions">
          <button className="secondary" onClick={() => setEditing("new")}>
            Add a template
          </button>
        </div>
      )}
      {editing !== null && <TemplateForm key={editing === "new" ? "new" : editing.id} editing={editing === "new" ? null : editing} onDone={done} />}
    </section>
  );
}
