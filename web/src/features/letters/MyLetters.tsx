import { useEffect, useState } from "react";
import { getAll } from "../../api/client";
import type { Letter } from "../../api/types";
import { dmy } from "../../app/format";

/** The letters the School has issued to me (item 1.19), to read or keep. */
export function MyLetters() {
  const [letters, setLetters] = useState<Letter[] | null>(null);

  useEffect(() => {
    getAll<Letter>("/letters/mine/")
      .then(setLetters)
      .catch(() => setLetters([]));
  }, []);

  return (
    <section className="card-block" aria-labelledby="my-letters-heading">
      <h2 id="my-letters-heading">Letters</h2>
      {letters === null && <p className="loading">Loading…</p>}
      {letters !== null && letters.length === 0 && <p className="muted">No letters have been issued to you yet.</p>}
      {letters !== null && letters.length > 0 && (
        <ul className="plain" aria-label="My letters">
          {letters.map((l) => (
            <li key={l.id}>
              <a href={l.download_url}>{l.template_name}</a>{" "}
              <span className="muted small">
                {l.reference} · {dmy(l.issued_on)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
