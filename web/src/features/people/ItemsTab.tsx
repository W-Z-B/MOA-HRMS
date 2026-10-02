import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, getAll, post } from "../../api/client";
import { hasAnyRole, type Employee, type IssuedItem, type ItemCondition, type Me } from "../../api/types";
import { dmy } from "../../app/format";

const KINDS: [string, string][] = [
  ["key", "Key"],
  ["tool", "Tool or equipment"],
  ["device", "Computer, phone or other device"],
  ["uniform", "Uniform"],
  ["protective", "Protective clothing or gear"],
  ["card", "Identity or access card"],
  ["vehicle", "Vehicle"],
  ["book", "Book or manual"],
  ["other", "Other"],
];
const CONDITIONS: [ItemCondition, string][] = [
  ["good", "In good order"],
  ["worn", "Worn with use"],
  ["damaged", "Damaged"],
  ["lost", "Lost"],
];
// Supervisors hand out the tools, keys and gear of their unit, as HR does.
const ITEM_WRITE_ROLES = ["hr_officer", "hr_manager", "administrator", "supervisor"];

function IssueForm({ employee, onIssued }: { employee: Employee; onIssued: (item: IssuedItem) => void }) {
  const [kind, setKind] = useState("tool");
  const [description, setDescription] = useState("");
  const [tag, setTag] = useState("");
  const [on, setOn] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function issue(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const item = await post<IssuedItem>("/issued-items/", { employee: employee.id, kind, description, tag, issued_on: on });
      setDescription("");
      setTag("");
      onIssued(item);
    } catch (err) {
      setError(errorMessage(err, "The item was not recorded."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={issue} aria-label="Issue an item">
      <h3>Issue an item</h3>
      <div className="grid2">
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          What it is
          <input value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={160} />
        </label>
        <label>
          Serial number or tag (if any)
          <input value={tag} onChange={(e) => setTag(e.target.value)} maxLength={60} />
        </label>
        <label>
          Issued on
          <input type="date" value={on} onChange={(e) => setOn(e.target.value)} required />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Issue the item</button>
      </div>
    </form>
  );
}

function GiveBackForm({ item, onDone }: { item: IssuedItem; onDone: (back: IssuedItem | null) => void }) {
  const [on, setOn] = useState("");
  const [condition, setCondition] = useState<ItemCondition>("good");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function giveBack(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onDone(await post<IssuedItem>(`/issued-items/${item.id}/return/`, { returned_on: on, condition, note }));
    } catch (err) {
      setError(errorMessage(err, "That was not recorded."));
    }
  }

  return (
    <form className="stack" onSubmit={giveBack} aria-label={`Given back: ${item.description}`}>
      <div className="grid2">
        <label>
          Given back on
          <input type="date" value={on} onChange={(e) => setOn(e.target.value)} required />
        </label>
        <label>
          In what condition
          <select value={condition} onChange={(e) => setCondition(e.target.value as ItemCondition)}>
            {CONDITIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Note (optional)
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="secondary">
          Record it
        </button>
        <button type="button" className="link" onClick={() => onDone(null)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** The register of what the School has handed to this person (item 1.17), still out first. */
export function ItemsTab({ employee, me }: { employee: Employee; me: Me }) {
  const [items, setItems] = useState<IssuedItem[] | null>(null);
  const [returning, setReturning] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, ITEM_WRITE_ROLES) && employee.status !== "separated";

  const load = useCallback(() => {
    getAll<IssuedItem>(`/issued-items/?employee=${employee.id}`)
      .then(setItems)
      .catch((err) => setError(errorMessage(err, "Could not load the items issued.")));
  }, [employee.id]);
  useEffect(load, [load]);

  return (
    <section className="stack" aria-labelledby="items-heading">
      <h3 id="items-heading" className="sr-only">
        Items issued
      </h3>
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
      {items !== null && items.length === 0 && <p className="muted">Nothing has been issued.</p>}
      {items !== null && items.length > 0 && (
        <ul className="plain accounts" aria-label="Items issued">
          {items.map((item) => (
            <li key={item.id} className={item.returned_on ? "state-switched_off" : undefined}>
              <div>
                <strong>{item.description}</strong> <span className="chip">{item.kind_name}</span>
                {!item.returned_on && <span className="chip chip-career-scheduled">Still out</span>}
                <br />
                <span className="muted small">
                  {item.tag ? `${item.tag} · ` : ""}issued {dmy(item.issued_on)}
                  {item.issued_by ? ` by ${item.issued_by}` : ""}
                  {item.returned_on ? ` · given back ${dmy(item.returned_on)}, ${item.condition_name.toLowerCase()}` : ""}
                  {item.note ? ` · ${item.note}` : ""}
                </span>
              </div>
              {mayWrite && !item.returned_on && returning !== item.id && (
                <div className="actions">
                  <button className="link" onClick={() => setReturning(item.id)} aria-label={`Record ${item.description} as given back`}>
                    Given back
                  </button>
                </div>
              )}
              {returning === item.id && (
                <GiveBackForm
                  item={item}
                  onDone={(back) => {
                    setReturning(null);
                    if (back) {
                      setNotice(`${back.description}: ${back.condition_name.toLowerCase()}, recorded.`);
                      load();
                    }
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {mayWrite && (
        <IssueForm
          employee={employee}
          onIssued={(item) => {
            setNotice(`${item.description} issued.`);
            load();
          }}
        />
      )}
    </section>
  );
}
