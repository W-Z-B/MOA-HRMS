import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import type { Campus, IncidentKind, Me, MyIncident, OrgUnit } from "../../api/types";
import { localNow } from "../../app/format";

const KINDS: [IncidentKind, string, string][] = [
  ["accident", "An accident", "Someone was hurt."],
  ["near_miss", "A near miss", "Nobody was hurt, but someone could have been."],
  ["dangerous", "A dangerous occurrence", "An explosion, a fire, a flood, a machine or equipment failing, a cave-in."],
  ["disease", "An illness caused by work", "Such as a skin or breathing complaint from chemicals, dust or animals."],
];

/** Anyone may report what happened (item 1.16). HR is told at once and keeps the register. */
export function ReportForm({ me, onReported, onCancel }: { me: Me; onReported: (made: MyIncident) => void; onCancel: () => void }) {
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [kind, setKind] = useState<IncidentKind>("accident");
  const [when, setWhen] = useState("");
  const [campus, setCampus] = useState("");
  const [unit, setUnit] = useState("");
  const [place, setPlace] = useState("");
  const [industrial, setIndustrial] = useState(false);
  const [description, setDescription] = useState("");
  const [immediate, setImmediate] = useState("");
  const [hurt, setHurt] = useState(false);
  const [injury, setInjury] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAll<Campus>("/org/campuses/")
      .then(setCampuses)
      .catch(() => setCampuses([]));
  }, []);
  useEffect(() => {
    if (!campus) return;
    getAll<OrgUnit>(`/org/units/?campus=${campus}`)
      .then(setUnits)
      .catch(() => setUnits([]));
  }, [campus]);
  const unitsHere = units.filter((u) => String(u.campus) === campus);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const made = await post<MyIncident>("/incidents/", {
        kind,
        occurred_at: when,
        campus: Number(campus),
        org_unit: unit ? Number(unit) : null,
        place,
        industrial,
        description,
        immediate_action: immediate,
        hurt,
        injury: hurt ? injury : "",
      });
      onReported(made);
    } catch (err) {
      setError(errorMessage(err, "The report was not sent."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={send} aria-label="Report an incident">
      <fieldset className="stack">
        <legend>What was it?</legend>
        {KINDS.map(([value, label, hint]) => (
          <label key={value} className="inline">
            <input type="radio" name="kind" value={value} checked={kind === value} onChange={() => setKind(value)} />{" "}
            <strong>{label}</strong> <span className="muted small">{hint}</span>
          </label>
        ))}
      </fieldset>
      <div className="grid2">
        <label>
          When
          <input type="datetime-local" value={when} max={localNow()} onChange={(e) => setWhen(e.target.value)} required />
        </label>
        <label>
          Campus
          <select
            value={campus}
            onChange={(e) => {
              setCampus(e.target.value);
              setUnit("");
            }}
            required
          >
            <option value="">Choose</option>
            {campuses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Farm, workshop or unit
          <select value={unit} onChange={(e) => setUnit(e.target.value)} disabled={!campus}>
            <option value="">Not in one, or not sure</option>
            {unitsHere.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Exactly where
          <input value={place} onChange={(e) => setPlace(e.target.value)} required maxLength={120} placeholder="By the feed mixer" />
        </label>
      </div>
      <label className="inline">
        <input type="checkbox" checked={industrial} onChange={(e) => setIndustrial(e.target.checked)} /> At the processing unit, a
        workshop or another industrial place
      </label>
      <label>
        What happened
        <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} required />
      </label>
      <label>
        What was done at once <span className="muted small">(optional)</span>
        <textarea rows={2} value={immediate} onChange={(e) => setImmediate(e.target.value)} placeholder="First aid given; the area fenced off" />
      </label>
      {me.employee_id !== null && (
        <label className="inline">
          <input type="checkbox" checked={hurt} onChange={(e) => setHurt(e.target.checked)} /> I was hurt
        </label>
      )}
      {hurt && (
        <label>
          Your injury <span className="muted small">(only Human Resources reads this)</span>
          <textarea rows={2} value={injury} onChange={(e) => setInjury(e.target.value)} />
        </label>
      )}
      <p className="muted small">Say in what happened if someone else was hurt. Human Resources records them.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Send the report</button>
        <button type="button" className="link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
