import type { LeaveReceipt } from "../../api/types";
import { dmy, dmyTime, inDays, num } from "../../app/format";

interface Props {
  receipt: LeaveReceipt;
  onBack: () => void;
}

/**
 * The receipt issued on final approval. It shows the balances as they stood that day, so it reads
 * the same whenever it is opened. Printing it, or saving it as a PDF, prints the receipt alone.
 */
export function Receipt({ receipt, onBack }: Props) {
  return (
    <>
      <p className="no-print">
        <button className="link accent" onClick={onBack}>
          Back to leave
        </button>
      </p>
      <article className="receipt">
        <header>
          <p className="eyebrow">Guyana School of Agriculture</p>
          <h1>Leave approved</h1>
          <p className="muted">
            Receipt {receipt.number} · issued {dmyTime(receipt.issued_at)}
          </p>
        </header>

        <dl>
          <dt>Employee</dt>
          <dd>
            {receipt.employee_name} ({receipt.employee_no})
          </dd>
          <dt>Position</dt>
          <dd>
            {receipt.position || "Not recorded"}, {receipt.campus}
          </dd>
          <dt>Leave</dt>
          <dd>
            {receipt.leave_type}, {receipt.paid ? "paid" : "without pay"}
          </dd>
          <dt>Dates</dt>
          <dd>
            {dmy(receipt.from_date)} to {dmy(receipt.to_date)} · <strong>{inDays(receipt.days)}</strong>
          </dd>
          <dt>Back at work</dt>
          <dd>{dmy(receipt.return_date)}</dd>
          {num(receipt.days_beyond) > 0 && (
            <>
              <dt>Beyond the entitlement</dt>
              <dd>
                {inDays(receipt.days_beyond)}, supported by a {receipt.evidence.toLowerCase()}
              </dd>
            </>
          )}
        </dl>

        <h2>Days you have left</h2>
        <div className="tiles">
          {receipt.balances.map((b) => (
            <div className="tile" key={b.code}>
              <span className="num">{parseFloat(num(b.remaining).toFixed(2))}</span>
              <span>{b.name}</span>
              {num(b.pending) > 0 && <span className="muted small">{inDays(b.pending)} more awaiting a decision</span>}
            </div>
          ))}
        </div>

        <h2>Approved by</h2>
        <ul className="plain">
          {receipt.approvals.map((a) => (
            <li key={a.step}>
              <strong>{a.name}</strong>, {a.step}
              <br />
              <span className="muted small">{dmyTime(a.decided_at)}</span>
            </li>
          ))}
        </ul>
      </article>
      <p className="no-print actions">
        <button onClick={() => window.print()}>Print or save as PDF</button>
      </p>
    </>
  );
}
