import { useCallback, useEffect, useState } from "react";
import { get, plainMessage, post } from "../../api/client";
import { PAYROLL_READ_ROLES, PAYROLL_WRITE_ROLES, hasAnyRole, type Me, type PayRun, type Paginated, type Payslip } from "../../api/types";
import { gyd } from "../../app/format";
import { NewRunForm } from "./NewRunForm";
import { PayRunCard } from "./PayRunCard";

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
}

type Tab = "mine" | "runs";

const STATE_CLASS: Record<string, string> = {
  draft: "chip-draft",
  calculated: "chip-waiting",
  approved: "chip-waiting",
  disbursed: "chip-approved",
};

/** Payroll (item H-M01), phone first: my payslips once a run is disbursed, and, for Finance and
 * administrators, the pay runs themselves: calculate, approve (never the person who calculated it),
 * then disburse, which issues each payslip's PDF. */
export function PayrollScreen({ me, path, onNavigate }: Props) {
  const query = path.includes("?") ? new URLSearchParams(path.split("?")[1]) : null;
  const canRead = hasAnyRole(me, PAYROLL_READ_ROLES);
  const canWrite = hasAnyRole(me, PAYROLL_WRITE_ROLES);
  const [tab, setTab] = useState<Tab>(query?.get("tab") === "runs" && canRead ? "runs" : "mine");
  const [mine, setMine] = useState<Payslip[]>([]);
  const [runs, setRuns] = useState<PayRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadMine = useCallback(() => {
    if (me.employee_id === null) return;
    get<Paginated<Payslip>>("/payroll/payslips/")
      .then((r) => {
        setMine(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load your payslips.")));
  }, [me.employee_id]);

  const loadRuns = useCallback(() => {
    if (!canRead) return;
    get<Paginated<PayRun>>("/payroll/runs/")
      .then((r) => {
        setRuns(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load pay runs.")));
  }, [canRead]);

  useEffect(() => {
    if (tab === "mine") loadMine();
    else loadRuns();
  }, [tab, loadMine, loadRuns]);

  async function createRun(period: string) {
    try {
      await post<PayRun>("/payroll/runs/", { period });
      setNotice(`Pay run for ${period} created, in draft.`);
      setError(null);
      loadRuns();
    } catch (err) {
      setError(plainMessage(err, "Could not create that pay run."));
    }
  }

  async function act(run: PayRun, action: string) {
    setNotice(null);
    try {
      const moved = await post<PayRun>(`/payroll/runs/${run.id}/transition/`, { action });
      if (action === "calculate" || action === "recalculate")
        setNotice(`Calculated: net pay ${gyd(moved.total_net)}. Someone else must approve it.`);
      if (action === "approve") setNotice("Approved. It can now be disbursed.");
      if (action === "disburse") setNotice("Disbursed. Payslips have been issued.");
      if (action === "reopen") setNotice("Back in draft.");
      setError(null);
      loadRuns();
    } catch (err) {
      setError(plainMessage(err, "That did not go through."));
    }
  }

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Payroll</h1>
          <p className="muted lead">
            {canRead ? "Your payslips, and the School's pay runs." : "Your payslips, once a pay run is disbursed."}
          </p>
        </div>
      </div>

      {canRead && (
        <div className="tabs" role="tablist" aria-label="Payroll">
          <button role="tab" aria-selected={tab === "mine"} className={tab === "mine" ? "tab active" : "tab"} onClick={() => setTab("mine")}>
            My payslips
          </button>
          <button role="tab" aria-selected={tab === "runs"} className={tab === "runs" ? "tab active" : "tab"} onClick={() => setTab("runs")}>
            Pay runs
          </button>
        </div>
      )}

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

      {tab === "mine" &&
        (me.employee_id === null ? (
          <p className="panel-card padded muted">Your account is not linked to an employee record.</p>
        ) : mine.length === 0 ? (
          <p className="panel-card padded">Nothing has been disbursed to you yet.</p>
        ) : (
          <ul className="rows">
            {mine.map((p) => (
              <li key={p.id} className="item-row">
                <span className="stacked grow">
                  <span className="strong">{p.period}</span>
                  <span className="muted small">
                    Gross {gyd(p.gross)} · NIS {gyd(p.nis_employee)} · PAYE {gyd(p.paye)}
                  </span>
                </span>
                <span className="stacked" style={{ alignItems: "flex-end" }}>
                  <span className="figure-value">{gyd(p.net)}</span>
                  {p.has_document && (
                    <a className="small" href={`/api/v1/payroll/payslips/${p.id}/download/`}>
                      Download PDF
                    </a>
                  )}
                </span>
              </li>
            ))}
          </ul>
        ))}

      {tab === "runs" && canRead && (
        <>
          {canWrite && <NewRunForm onCreate={createRun} />}
          {runs.length === 0 ? (
            <p className="panel-card padded">No pay runs yet.</p>
          ) : (
            runs.map((run) => (
              <PayRunCard
                key={run.id}
                run={run}
                stateClass={STATE_CLASS[run.state] ?? ""}
                onAction={act}
                onOpenEmployee={(id) => onNavigate(`/people/${id}`)}
              />
            ))
          )}
        </>
      )}
    </>
  );
}
