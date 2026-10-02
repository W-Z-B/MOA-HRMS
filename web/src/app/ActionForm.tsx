import { useState, type FormEvent, type ReactNode } from "react";
import { errorMessage, patch, post } from "../api/client";

/** A small form that sends one change to a record and hands back the record as it now stands. Any refusal is
 * shown in words inside the form, next to what was refused. */
export function ActionForm<T>({
  label,
  path,
  fields,
  onDone,
  method = "POST",
  submit,
  children,
}: {
  label: string;
  path: string;
  fields: () => Record<string, unknown>;
  onDone: (fresh: T) => void;
  method?: "POST" | "PATCH";
  /** The button's words, when they differ from the form's name. */
  submit?: string;
  children: ReactNode;
}) {
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onDone(await (method === "PATCH" ? patch<T>(path, fields()) : post<T>(path, fields())));
    } catch (err) {
      setError(errorMessage(err, "That was not recorded."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={send} aria-label={label}>
      <h4>{label}</h4>
      {children}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">{submit ?? label}</button>
      </div>
    </form>
  );
}
