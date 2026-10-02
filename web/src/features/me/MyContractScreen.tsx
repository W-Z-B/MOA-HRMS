import { useEffect, useState } from "react";
import { get, plainMessage } from "../../api/client";
import type { MyTerms } from "../../api/types";
import { dmy, gyd, inDays } from "../../app/format";
import { MyLetters } from "../letters/MyLetters";

/** The employee's own appointment and contract: what the School holds about the terms they work on. */
export function MyContractScreen() {
  const [terms, setTerms] = useState<MyTerms | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<MyTerms>("/contracts/mine/")
      .then(setTerms)
      .catch((err) => setError(plainMessage(err, "Could not load your contract.")));
  }, []);

  if (error)
    return (
      <>
        <h1>My contract</h1>
        <p role="alert" className="error">
          {error}
        </p>
      </>
    );
  if (!terms) return <p className="loading">Loading your contract…</p>;
  const contract = terms.contract;

  return (
    <>
      <h1>My contract</h1>
      <section className="card-block">
        <h2>{terms.name}</h2>
        <p className="muted">
          {terms.employee_no} · {terms.campus}
        </p>
        <dl className="terms">
          <dt>Position</dt>
          <dd>{terms.position ?? "No current appointment"}</dd>
          <dt>Unit</dt>
          <dd>{terms.unit ?? "Not recorded"}</dd>
          <dt>Manager</dt>
          <dd>{terms.manager ?? "Campus supervisors"}</dd>
          <dt>Appointment</dt>
          <dd>{terms.appointment_type ?? "Not recorded"}</dd>
          <dt>From</dt>
          <dd>
            {dmy(terms.start_date) || "Not recorded"}
            {terms.end_date && ` to ${dmy(terms.end_date)}`}
          </dd>
          {terms.probation_end && (
            <>
              <dt>Probation ends</dt>
              <dd>{dmy(terms.probation_end)}</dd>
            </>
          )}
        </dl>
      </section>

      <section className="card-block">
        <h2>Terms</h2>
        {contract ? (
          <dl className="terms">
            <dt>Contract</dt>
            <dd>
              {contract.contract_type}
              {contract.term_months ? `, ${contract.term_months} months` : ""}
            </dd>
            <dt>Signed</dt>
            <dd>{dmy(contract.signed_on) || "Not recorded"}</dd>
            <dt>Hours a week</dt>
            <dd>{contract.hours_per_week ?? "Not recorded"}</dd>
            <dt>Hourly rate</dt>
            <dd>
              {contract.hourly_rate === null ? (
                "Not recorded"
              ) : (
                <>
                  {gyd(contract.hourly_rate)}{" "}
                  {!contract.hourly_rate_is_set && <span className="muted small">worked out from your grade and hours</span>}
                </>
              )}
            </dd>
            <dt>Notice</dt>
            <dd>{contract.notice_period_days ? inDays(contract.notice_period_days) : "Not recorded"}</dd>
            {contract.other_terms && (
              <>
                <dt>Other terms</dt>
                <dd>{contract.other_terms}</dd>
              </>
            )}
          </dl>
        ) : (
          <p className="muted">No contract is on file for your current appointment. Ask Human Resources.</p>
        )}
      </section>

      <section className="card-block">
        <h2>Leave each year</h2>
        {terms.entitlements.length === 0 ? (
          <p className="muted">No entitlement is recorded.</p>
        ) : (
          <dl className="terms">
            {terms.entitlements.map((e) => (
              <div key={e.code}>
                <dt>{e.name}</dt>
                <dd>
                  {inDays(e.annual_days)} {e.from_contract && <span className="muted small">set in your contract</span>}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <MyLetters />
    </>
  );
}
