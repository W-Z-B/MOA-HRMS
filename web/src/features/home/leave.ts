import { useCallback, useEffect, useState } from "react";
import { get, plainMessage } from "../../api/client";
import type { LeaveRequest, Paginated } from "../../api/types";
import { dmy, inDays, num } from "../../app/format";

/** Leave waiting for a decision: what this person decides now, and (for HR) what is still with a manager. */
export function useLeaveToDecide(active = true) {
  const [toDecide, setToDecide] = useState<LeaveRequest[] | null>(null);
  const [elsewhere, setElsewhere] = useState<LeaveRequest[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!active) return;
    Promise.all([
      get<Paginated<LeaveRequest>>("/leave/requests/?state=submitted"),
      get<Paginated<LeaveRequest>>("/leave/requests/?state=supervisor_approved"),
    ])
      .then(([submitted, withHr]) => {
        // The leave that starts soonest is the one to decide first.
        const open = [...submitted.results, ...withHr.results]
          .filter((r) => !r.is_mine)
          .sort((a, b) => a.from_date.localeCompare(b.from_date));
        setToDecide(open.filter((r) => r.allowed_actions.includes("approve")));
        // Not this person's turn, but theirs to stop: HR sees what is still with a manager.
        setElsewhere(open.filter((r) => !r.allowed_actions.includes("approve") && r.allowed_actions.includes("reject")));
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load the leave waiting for a decision.")));
  }, [active]);

  useEffect(load, [load]);
  return { toDecide, elsewhere, error, reload: load };
}

export const dates = (r: LeaveRequest) => (r.to_date !== r.from_date ? `${dmy(r.from_date)} to ${dmy(r.to_date)}` : dmy(r.from_date));

/** What is left of the balance once this request is approved, when the balance covers it. */
export function after(r: LeaveRequest): string {
  if (r.balance_after === null || num(r.days_beyond) > 0) return "";
  return `leaves ${inDays(r.balance_after)} of ${r.leave_type_name.toLowerCase()}`;
}
