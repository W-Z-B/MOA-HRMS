import type { AttendanceRecord } from "../../api/types";
import { hm } from "../../app/format";
import { StatusChip } from "./AttendanceScreen";

interface Props {
  today: AttendanceRecord | null;
  busy: boolean;
  onCheckIn: () => void;
  onCheckOut: () => void;
}

/** Today's card: one big button for whichever of check-in or check-out comes next. */
export function CheckInCard({ today, busy, onCheckIn, onCheckOut }: Props) {
  const checkedIn = today?.time_in != null;
  const checkedOut = today?.time_out != null;

  return (
    <section className="card-block stack" aria-label="Today">
      <h2>Today</h2>
      {today ? (
        <p>
          {checkedIn ? (
            <>
              Checked in at <strong>{hm(today.time_in)}</strong>
              {checkedOut && (
                <>
                  , checked out at <strong>{hm(today.time_out)}</strong>
                </>
              )}
              .
            </>
          ) : (
            "You have not checked in today."
          )}
          {today.status !== "present" && (
            <>
              {" "}
              <StatusChip record={today} />
            </>
          )}
        </p>
      ) : (
        <p>You have not checked in today.</p>
      )}
      <div className="actions">
        {!checkedIn && (
          <button disabled={busy} onClick={onCheckIn}>
            Check in
          </button>
        )}
        {checkedIn && !checkedOut && (
          <button disabled={busy} onClick={onCheckOut}>
            Check out
          </button>
        )}
        {checkedIn && checkedOut && <p className="muted small">That is everything for today. See you tomorrow.</p>}
      </div>
    </section>
  );
}
