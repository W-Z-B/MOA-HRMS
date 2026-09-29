import { useEffect, useState } from "react";
import { get } from "../../api/client";
import type { LeaveRequest, Paginated, ReportResult } from "../../api/types";

interface Props {
  campusId: number | null;
}

/** Wireframe 1: tiles for on-leave, pending approvals, headcount; approvals list beneath. */
export function DashboardScreen({ campusId }: Props) {
  const [pending, setPending] = useState<LeaveRequest[]>([]);
  const [headcount, setHeadcount] = useState<ReportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      get<Paginated<LeaveRequest>>("/leave/requests/?state=submitted"),
      get<ReportResult>("/reports/headcount-by-campus/"),
    ])
      .then(([requests, report]) => {
        setPending(requests.results);
        setHeadcount(report);
      })
      .catch((err) => setError(err.detail ?? "Could not load the dashboard."));
  }, [campusId]);

  const total = headcount?.rows.reduce((sum, r) => sum + Number(r.active), 0) ?? 0;

  return (
    <>
      <h1>Dashboard</h1>
      {error && <p className="error">{error}</p>}
      <section className="tiles">
        <div className="tile">
          <span className="num">{total}</span>
          <span>Active staff</span>
        </div>
        <div className="tile">
          <span className="num">{pending.length}</span>
          <span>Leave awaiting approval</span>
        </div>
        {headcount?.rows.map((r) => (
          <div className="tile" key={String(r.campus)}>
            <span className="num">{r.active}</span>
            <span>{r.campus}</span>
          </div>
        ))}
      </section>
      <section>
        <h2>Pending approvals</h2>
        {pending.length === 0 ? (
          <p className="muted">Nothing waiting for you.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Type</th>
                <th>From</th>
                <th>To</th>
                <th>Days</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((r) => (
                <tr key={r.id}>
                  <td>{r.employee_name}</td>
                  <td>{r.leave_type_code}</td>
                  <td>{r.from_date}</td>
                  <td>{r.to_date}</td>
                  <td className="num">{r.days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
