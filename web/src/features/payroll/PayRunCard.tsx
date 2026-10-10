import { useState } from "react";
import { get } from "../../api/client";
import type { Paginated, PayRun, Payslip } from "../../api/types";
import { gyd } from "../../app/format";

interface Props {
  run: PayRun;
  stateClass: string;
  onAction: (run: PayRun, action: string) => Promise<void>;
  onOpenEmployee: (employeeId: number) => void;
}

const ACTION_LABEL: Record<string, string> = {
  calculate: "Calculate",
  recalculate: "Recalculate",
  approve: "Approve",
  reopen: "Back to draft",
  disburse: "Disburse",
};
const STATE_LABEL: Record<string, string> = {
  draft: "Draft",
  calculated: "Calculated",
  approved: "Approved",
  disbursed: "Disbursed",
};

/** One pay run: its totals, the actions this person may take next, and its payslips once calculated. */
export function PayRunCard({ run, stateClass, onAction, onOpenEmployee }: Props) {
  const [open, setOpen] = useState(false);
  const [payslips, setPayslips] = useState<Payslip[] | null>(null);
  const [busy, setBusy] = useState(false);

  function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (payslips === null && run.state !== "draft") {
      get<Paginated<Payslip>>(`/payroll/payslips/?pay_run=${run.id}`)
        .then((r) => setPayslips(r.results))
        .catch(() => setPayslips([]));
    }
  }

  async function run_(action: string) {
    setBusy(true);
    try {
      await onAction(run, action);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card-block stack" aria-label={`Pay run ${run.period}`}>
      <header className="spread">
        <h3>{run.period}</h3>
        <span className={`chip ${stateClass}`}>{STATE_LABEL[run.state] ?? run.state}</span>
      </header>
      {run.state !== "draft" && (
        <p className="muted small">
          Gross {gyd(run.total_gross)} · NIS (employee) {gyd(run.total_nis_employee)} · PAYE {gyd(run.total_paye)} ·
          Net <strong>{gyd(run.total_net)}</strong>
        </p>
      )}
      <div className="actions">
        {run.allowed_actions.map((action) => (
          <button
            key={action}
            className={action === "reopen" ? "secondary" : ""}
            disabled={busy}
            onClick={() => run_(action)}
          >
            {ACTION_LABEL[action] ?? action}
          </button>
        ))}
        {run.state !== "draft" && (
          <button type="button" className="secondary small-button" onClick={toggle}>
            {open ? "Hide payslips" : "Show payslips"}
          </button>
        )}
      </div>
      {open && payslips !== null && (
        <ul className="rows">
          {payslips.length === 0 ? (
            <li className="panel-empty">No payslips yet.</li>
          ) : (
            payslips.map((p) => (
              <li key={p.id} className="item-row">
                <span className="stacked grow">
                  <button type="button" className="link accent" onClick={() => onOpenEmployee(p.employee)}>
                    {p.employee_name}
                  </button>
                  <span className="muted small">
                    {p.employee_no} · gross {gyd(p.gross)}
                    {Number(p.unpaid_days) > 0 ? ` · ${p.unpaid_days} unpaid day(s)` : ""}
                  </span>
                </span>
                <span className="figure-value">{gyd(p.net)}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </article>
  );
}
