import { useState, type FormEvent } from "react";
import { errorMessage, patch, post } from "../../api/client";
import type { Application } from "../../api/types";

interface Props {
  vacancyId: number;
  onCreated: (application: Application) => void;
}

/** Records an application HR received by email, by phone or on paper (the build plan's own conservative
 * default: no public online form in this release). A CV, if there is one, is attached in a second request
 * once the candidate record exists, so the file upload never has to travel inside the nested JSON body. */
export function NewApplicationForm({ vacancyId, onCreated }: Props) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [source, setSource] = useState("");
  const [cv, setCv] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const application = await post<Application>("/recruitment/applications/", {
        vacancy: vacancyId,
        source,
        candidate: { first_name: firstName, last_name: lastName, email, phone },
      });
      if (cv) {
        const form = new FormData();
        form.append("cv", cv);
        await patch(`/recruitment/candidates/${application.candidate.id}/`, form).catch(() => undefined);
        // A failed attachment never loses the application itself; HR can add the file again from the file.
      }
      onCreated(application);
      setFirstName("");
      setLastName("");
      setEmail("");
      setPhone("");
      setSource("");
      setCv(null);
    } catch (err) {
      setError(errorMessage(err, "The application could not be recorded."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card-block stack" onSubmit={submit} aria-label="Record an application">
      <h2>Record an application</h2>
      <div className="grid2">
        <label>
          First name
          <input value={firstName} onChange={(e) => setFirstName(e.target.value)} maxLength={80} required />
        </label>
        <label>
          Last name
          <input value={lastName} onChange={(e) => setLastName(e.target.value)} maxLength={80} required />
        </label>
      </div>
      <div className="grid2">
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Phone
          <input value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} />
        </label>
      </div>
      <label>
        How it reached HR
        <input
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="Email, paper, referral…"
          maxLength={40}
        />
      </label>
      <label>
        CV or covering letter (optional; PDF, Word or a photograph)
        <input type="file" accept=".pdf,.docx,.jpg,.jpeg,.png,.heic,.webp" onChange={(e) => setCv(e.target.files?.[0] ?? null)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          Record application
        </button>
      </div>
    </form>
  );
}
