import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import { hasAnyRole, type BankAccount, type Me, type Paginated } from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

const PROPOSE = ["hr_officer", "hr_manager", "administrator", "finance"];
const DECIDE = ["hr_manager", "finance", "administrator"];

interface Props {
  employeeId: number;
  me: Me;
}

/**
 * Where pay goes. A change is a proposal until a second person approves it; nothing is edited in place,
 * and the employee is told when it changes.
 */
export function BankTab({ employeeId, me }: Props) {
  const [accounts, setAccounts] = useState<BankAccount[] | null>(null);
  const [revealed, setRevealed] = useState<Record<number, string>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canPropose = hasAnyRole(me, PROPOSE);
  const canDecide = hasAnyRole(me, DECIDE);

  const load = useCallback(() => {
    get<Paginated<BankAccount>>(`/bank-accounts/?employee=${employeeId}`)
      .then((page) => setAccounts(page.results))
      .catch((err) => setError(errorMessage(err, "Could not load bank details.")));
  }, [employeeId]);

  useEffect(load, [load]);

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
      load();
    } catch (err) {
      setError(errorMessage(err, "That did not go through."));
    } finally {
      setBusy(false);
    }
  }

  const pending = accounts?.find((a) => a.state === "pending");

  return (
    <section className="records" aria-labelledby="bank-heading">
      <h3 id="bank-heading">Bank details</h3>
      <p className="muted small">
        A change is used only after a second person approves it, and the employee is told each time it changes.
      </p>
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
      {accounts !== null && accounts.length === 0 && <p className="muted">No bank details on file.</p>}
      {accounts !== null && accounts.length > 0 && (
        <ul className="plain">
          {accounts.map((a) => {
            const mayDecide = a.state === "pending" && canDecide && a.requested_by !== me.id;
            return (
              <li key={a.id}>
                <div>
                  <strong>{a.bank_name}</strong>
                  {a.branch ? `, ${a.branch}` : ""}{" "}
                  <span className={`chip chip-bank-${a.state}`}>{a.state_name}</span>
                  <br />
                  <span className="num">{revealed[a.id] ?? a.account_number_masked}</span> · {a.account_name}
                  <br />
                  <span className="muted small">
                    Proposed by {a.requested_by_name ?? "someone no longer here"} on {dmyTime(a.created_at)}
                    {a.decided_by_name && ` · ${a.state === "rejected" ? "not approved" : "approved"} by ${a.decided_by_name}`}
                    {a.effective_from && ` · in use from ${dmy(a.effective_from)}`}
                    {a.decision_note && ` · ${a.decision_note}`}
                  </span>
                </div>
                <div className="actions">
                  {canDecide && revealed[a.id] === undefined && (
                    <button
                      className="link"
                      aria-label={`Show the full account number for ${a.bank_name} (recorded)`}
                      onClick={() =>
                        run(async () => {
                          const shown = await post<{ account_number: string }>(`/bank-accounts/${a.id}/reveal/`);
                          setRevealed((r) => ({ ...r, [a.id]: shown.account_number }));
                          return "The full number is shown. Looking at it was recorded.";
                        })
                      }
                    >
                      Show number
                    </button>
                  )}
                  {mayDecide && (
                    <>
                      <label className="grow">
                        <span className="sr-only">Note for {a.bank_name}</span>
                        <input
                          placeholder="Note (needed to reject)"
                          value={notes[a.id] ?? ""}
                          onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })}
                          maxLength={200}
                        />
                      </label>
                      <button
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            await post(`/bank-accounts/${a.id}/approve/`, { note: notes[a.id] ?? "" });
                            return "Approved. Pay now goes to this account, and the employee has been told.";
                          })
                        }
                      >
                        Approve
                      </button>
                      <button
                        className="secondary"
                        disabled={busy || !(notes[a.id] ?? "").trim()}
                        onClick={() =>
                          run(async () => {
                            await post(`/bank-accounts/${a.id}/reject/`, { note: notes[a.id] });
                            return "Not approved. The account in use is unchanged.";
                          })
                        }
                      >
                        Reject
                      </button>
                    </>
                  )}
                  {a.state === "pending" && canDecide && a.requested_by === me.id && (
                    <span className="muted small">You proposed this change, so someone else must decide it.</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {canPropose && !pending && <ProposeForm employeeId={employeeId} busy={busy} onRun={run} />}
    </section>
  );
}

function ProposeForm({
  employeeId,
  busy,
  onRun,
}: {
  employeeId: number;
  busy: boolean;
  onRun: (work: () => Promise<string>) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ bank_name: "", branch: "", account_name: "", account_number: "" });

  if (!open)
    return (
      <button className="secondary" onClick={() => setOpen(true)}>
        Propose new bank details
      </button>
    );

  function submit(e: FormEvent) {
    e.preventDefault();
    void onRun(async () => {
      await post("/bank-accounts/", { employee: employeeId, ...form });
      setOpen(false);
      setForm({ bank_name: "", branch: "", account_name: "", account_number: "" });
      return "Proposed. It is used once a second person approves it.";
    });
  }

  const field = (name: keyof typeof form, label: string, extra: Record<string, unknown> = {}) => (
    <label htmlFor={`bank-${name}`}>
      {label}
      <input
        id={`bank-${name}`}
        value={form[name]}
        onChange={(e) => setForm({ ...form, [name]: e.target.value })}
        autoComplete="off"
        {...extra}
      />
    </label>
  );

  return (
    <form className="stack sub-form" onSubmit={submit} aria-label="Propose new bank details">
      <div className="grid2">
        {field("bank_name", "Bank", { required: true })}
        {field("branch", "Branch")}
        {field("account_name", "Name on the account", { required: true })}
        {field("account_number", "Account number", { required: true, inputMode: "numeric" })}
      </div>
      <div className="actions">
        <button type="button" className="secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
        <button type="submit" disabled={busy}>
          Propose
        </button>
      </div>
    </form>
  );
}
