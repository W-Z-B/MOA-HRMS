import { useCallback, useEffect, useState } from "react";
import { errorMessage, get, patch, plainMessage, post } from "../../api/client";
import {
  RETENTION_WRITE_ROLES,
  hasAnyRole,
  type DisposalRun,
  type Me,
  type Paginated,
  type RetentionRule,
} from "../../api/types";
import { dmy, dmyTime } from "../../app/format";

const kept = (rule: RetentionRule) =>
  rule.keep_months === null ? "Until the date on each record" : `${rule.keep_months} months`;

/**
 * The retention schedule (item 1.32): how long each kind of record is kept, whether GSA has agreed the
 * period, and the disposal runs that one person proposes and a second approves.
 */
export function RetentionTab({ me }: { me: Me }) {
  const [rules, setRules] = useState<RetentionRule[] | null>(null);
  const [runs, setRuns] = useState<DisposalRun[]>([]);
  const [months, setMonths] = useState<Record<number, string>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, RETENTION_WRITE_ROLES);

  const load = useCallback(() => {
    get<RetentionRule[]>("/privacy/retention-rules/")
      .then(setRules)
      .catch((err) => setError(errorMessage(err, "Could not load the retention schedule.")));
    get<Paginated<DisposalRun>>("/privacy/disposal-runs/")
      .then((page) => setRuns(page.results))
      .catch(() => setRuns([]));
  }, []);

  useEffect(load, [load]);

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    } finally {
      setBusy(false);
    }
  }

  const savePeriod = (rule: RetentionRule) =>
    run(async () => {
      await patch(`/privacy/retention-rules/${rule.id}/`, { keep_months: Number(months[rule.id]) });
      setMonths((all) => ({ ...all, [rule.id]: "" }));
      return `${rule.name}: now kept for ${months[rule.id]} months. Confirm it once GSA has agreed.`;
    });
  const confirm = (rule: RetentionRule) =>
    run(async () => {
      await post(`/privacy/retention-rules/${rule.id}/confirm/`);
      return `${rule.name}: recorded as agreed by GSA.`;
    });
  const find = (rule: RetentionRule) =>
    run(async () => (await post<{ detail: string }>(`/privacy/retention-rules/${rule.id}/find/`)).detail);
  const keep = (disposal: DisposalRun, itemId: number) =>
    run(async () => {
      await post(`/privacy/disposal-runs/${disposal.id}/keep/`, { item: itemId, reason: reasons[itemId] ?? "" });
      return "Kept, with the reason recorded.";
    });
  const approve = (disposal: DisposalRun) =>
    run(async () => {
      const done = await post<DisposalRun>(`/privacy/disposal-runs/${disposal.id}/approve/`);
      const destroyed = done.items.filter((i) => i.disposed_at).length;
      return `${destroyed} ${destroyed === 1 ? "record" : "records"} destroyed; each is recorded in the audit log.`;
    });
  const cancel = (disposal: DisposalRun) =>
    run(async () => {
      await post(`/privacy/disposal-runs/${disposal.id}/cancel/`);
      return "Cancelled. Nothing was destroyed.";
    });

  return (
    <section aria-labelledby="retention-heading">
      <h2 id="retention-heading" className="sr-only">
        Retention schedule
      </h2>
      <p className="muted">
        Records are kept only as long as the schedule says. Logs go every night by themselves; records go only when one
        person lists them and a second approves.
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
      {rules === null && !error && <p className="loading">Loading…</p>}
      {rules !== null && (
        <table className="cards">
          <caption className="sr-only">The retention schedule</caption>
          <thead>
            <tr>
              <th scope="col">Records</th>
              <th scope="col">Kept for</th>
              <th scope="col">Counted from</th>
              <th scope="col">How</th>
              <th scope="col">Agreed by GSA</th>
              {mayWrite && <th scope="col">Change</th>}
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td data-label="Records">{rule.name}</td>
                <td data-label="Kept for">{kept(rule)}</td>
                <td data-label="Counted from">{rule.counted_from}</td>
                <td data-label="How">{rule.automatic ? "Every night, by itself" : "Listed, then approved by a second person"}</td>
                <td data-label="Agreed by GSA">
                  {rule.confirmed
                    ? `Yes: ${rule.confirmed_by_name ?? "recorded"}, ${rule.confirmed_at ? dmy(rule.confirmed_at) : ""}`
                    : `Not yet. ${rule.note}`}
                </td>
                {mayWrite && (
                  <td data-label="Change" className="actions">
                    {rule.keep_months !== null && (
                      <>
                        <label>
                          <span className="sr-only">Months to keep {rule.name}</span>
                          <input
                            type="number"
                            min={1}
                            inputMode="numeric"
                            placeholder={String(rule.keep_months)}
                            value={months[rule.id] ?? ""}
                            onChange={(e) => setMonths({ ...months, [rule.id]: e.target.value })}
                          />
                        </label>
                        <button
                          className="secondary"
                          disabled={busy || !months[rule.id]}
                          onClick={() => savePeriod(rule)}
                          aria-label={`Save the period for ${rule.name}`}
                        >
                          Save
                        </button>
                      </>
                    )}
                    {!rule.confirmed && (
                      <button className="secondary" disabled={busy} onClick={() => confirm(rule)} aria-label={`Confirm the period for ${rule.name}`}>
                        Confirm
                      </button>
                    )}
                    {!rule.automatic && rule.open_run === null && (
                      <button disabled={busy} onClick={() => find(rule)} aria-label={`Find what is due: ${rule.name}`}>
                        Find what is due
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {runs.length > 0 && (
        <>
          <h3>Disposal runs</h3>
          <ul className="plain accounts" aria-label="Disposal runs">
            {runs.map((disposal) => (
              <li key={disposal.id} className={disposal.state === "proposed" ? "state-invited" : undefined}>
                <div>
                  <strong>{disposal.rule_name}</strong> <span className="chip">{disposal.state_name}</span>
                  <br />
                  <span className="muted small">
                    Listed by {disposal.proposed_by ?? "someone no longer here"}, {dmyTime(disposal.created_at)}
                    {disposal.approved_at
                      ? ` · approved by ${disposal.approved_by_name ?? "someone no longer here"}, ${dmyTime(disposal.approved_at)}`
                      : ""}
                  </span>
                </div>
                <ul className="plain grants" aria-label={`Records in ${disposal.rule_name}`}>
                  {disposal.items.map((item) => (
                    <li key={item.id}>
                      <span>
                        {item.description}, due since {dmy(item.due_since)}
                        {item.disposed_at ? ` · destroyed ${dmyTime(item.disposed_at)}` : ""}
                        {item.keep_reason ? ` · kept: ${item.keep_reason}` : ""}
                      </span>
                      {mayWrite && disposal.state === "proposed" && !item.keep_reason && (
                        <span className="actions">
                          <label>
                            <span className="sr-only">Why keep {item.description}</span>
                            <input
                              placeholder="Why keep it"
                              value={reasons[item.id] ?? ""}
                              onChange={(e) => setReasons({ ...reasons, [item.id]: e.target.value })}
                              maxLength={300}
                            />
                          </label>
                          <button
                            className="secondary"
                            disabled={busy || !(reasons[item.id] ?? "").trim()}
                            onClick={() => keep(disposal, item.id)}
                            aria-label={`Keep ${item.description}`}
                          >
                            Keep
                          </button>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
                {mayWrite && disposal.state === "proposed" && (
                  <div className="actions">
                    {disposal.proposed_by_me ? (
                      <span className="muted small">You listed these, so someone else approves.</span>
                    ) : (
                      <button disabled={busy} onClick={() => approve(disposal)}>
                        Approve and destroy
                      </button>
                    )}
                    <button className="secondary" disabled={busy} onClick={() => cancel(disposal)}>
                      Cancel the run
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
