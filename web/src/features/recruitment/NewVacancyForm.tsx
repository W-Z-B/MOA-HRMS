import { useEffect, useState, type FormEvent } from "react";
import { getAll } from "../../api/client";
import type { Position } from "../../api/types";

interface Props {
  campusId: number | null;
  onCreate: (fields: { position: number; title: string; opens_on: string; closes_on: string }) => Promise<void>;
}

/** Posts a vacancy against an approved, existing post (org.Position): item H-W01 does not let a vacancy
 * invent a post of its own, so the establishment stays the one source of headcount. */
export function NewVacancyForm({ campusId, onCreate }: Props) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [position, setPosition] = useState("");
  const [title, setTitle] = useState("");
  const [opensOn, setOpensOn] = useState("");
  const [closesOn, setClosesOn] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const query = campusId ? `?campus=${campusId}` : "";
    getAll<Position>(`/org/positions/${query}`)
      .then(setPositions)
      .catch(() => setPositions([]));
  }, [campusId]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!position || !opensOn || !closesOn) return;
    setBusy(true);
    try {
      await onCreate({ position: Number(position), title, opens_on: opensOn, closes_on: closesOn });
      setPosition("");
      setTitle("");
      setOpensOn("");
      setClosesOn("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card-block stack" onSubmit={submit} aria-label="Post a vacancy">
      <h2>Post a vacancy</h2>
      <label>
        Post
        <select value={position} onChange={(e) => setPosition(e.target.value)} required>
          <option value="">Choose the post being filled…</option>
          {positions.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.is_vacant}>
              {p.number} {p.title} ({p.org_unit_name}){!p.is_vacant ? " — filled" : ""}
            </option>
          ))}
        </select>
      </label>
      <label>
        Advertised title (optional; defaults to the post's own title)
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160} />
      </label>
      <div className="grid2">
        <label>
          Opens
          <input type="date" value={opensOn} onChange={(e) => setOpensOn(e.target.value)} required />
        </label>
        <label>
          Closes
          <input type="date" value={closesOn} onChange={(e) => setClosesOn(e.target.value)} required />
        </label>
      </div>
      <div className="actions">
        <button type="submit" disabled={busy || !position}>
          Post vacancy
        </button>
      </div>
    </form>
  );
}
