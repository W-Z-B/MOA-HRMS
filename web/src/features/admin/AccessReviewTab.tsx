import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, plainMessage, post } from "../../api/client";
import {
  REVIEW_SIGN_ROLES,
  hasAnyRole,
  type AccessReview,
  type Me,
  type Paginated,
  type ReportResult,
  type ReportRow,
} from "../../api/types";
import { dmyTime } from "../../app/format";

/** The review falls due three months after the last sign-off; the server reminds HR when it does. */
export const REVIEW_EVERY_DAYS = 92;
const DAY_MS = 24 * 60 * 60 * 1000;

interface Props {
  me: Me;
  campusId: number | null;
  onNavigate: (to: string) => void;
}

const dateOnly = (date: Date) =>
  date.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" });

/** Who can see what, every role of every account, read and signed off every three months (item 1.27). */
export function AccessReviewTab({ me, campusId, onNavigate }: Props) {
  const [rows, setRows] = useState<ReportRow[] | null>(null);
  const [reviews, setReviews] = useState<AccessReview[] | null>(null);
  const [onlyToCheck, setOnlyToCheck] = useState(false);
  const [notes, setNotes] = useState("");
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [now] = useState(() => Date.now()); // read once, so the page does not change as it re-renders
  const maySign = hasAnyRole(me, REVIEW_SIGN_ROLES);

  useEffect(() => {
    let current = true;
    get<ReportResult>(`/reports/access-review/${campusId ? `?campus=${campusId}` : ""}`)
      .then((result) => current && setRows(result.rows))
      .catch((err) => current && setError(errorMessage(err, "Could not load who can see what.")));
    return () => {
      current = false;
    };
  }, [campusId]);

  useEffect(() => {
    let current = true;
    get<Paginated<AccessReview>>("/access-reviews/")
      .then((page) => current && setReviews(page.results))
      .catch((err) => current && setError(errorMessage(err, "Could not load the sign-offs.")));
    return () => {
      current = false;
    };
  }, [version]);

  async function signOff(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const review = await post<AccessReview>("/access-reviews/", { notes });
      setNotice(`Signed off: ${review.accounts} accounts reviewed. The next review is due in three months.`);
      setNotes("");
      setVersion((v) => v + 1);
    } catch (err) {
      setError(plainMessage(err, "The sign-off was not saved. Try again."));
    } finally {
      setBusy(false);
    }
  }

  const last = reviews?.[0];
  const due = last ? new Date(new Date(last.reviewed_at).getTime() + REVIEW_EVERY_DAYS * DAY_MS) : null;
  const overdue = due !== null && due.getTime() < now;
  const shown = rows?.filter((row) => !onlyToCheck || row.to_check) ?? [];
  const toCheck = rows?.filter((row) => row.to_check).length ?? 0;

  return (
    <section aria-labelledby="review-heading">
      <h2 id="review-heading" className="sr-only">
        Access review
      </h2>
      {reviews !== null && (
        <p className={last && !overdue ? "notice good" : "notice"}>
          {last
            ? `Last signed off on ${dmyTime(last.reviewed_at)} by ${last.reviewed_by_name}, with ${last.accounts} accounts. `
            : "The access review has not been signed off yet. "}
          {due ? `${overdue ? "It was due by" : "Next due by"} ${dateOnly(due)}.` : "Read the list below and sign it off."}
        </p>
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
      {rows === null && !error && <p className="loading">Loading…</p>}
      {rows !== null && (
        <>
          <div className="filters">
            <label className="inline">
              <input type="checkbox" checked={onlyToCheck} onChange={(e) => setOnlyToCheck(e.target.checked)} /> Only
              what needs a look ({toCheck})
            </label>
          </div>
          {shown.length === 0 ? (
            <p className="muted">Nothing to show.</p>
          ) : (
            <table className="cards">
              <caption className="sr-only">Every role every account holds</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Username</th>
                  <th scope="col">Role</th>
                  <th scope="col">Where</th>
                  <th scope="col">Given</th>
                  <th scope="col">Last signed in</th>
                  <th scope="col">Authenticator</th>
                  <th scope="col">To check</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((row, index) => (
                  <tr key={`${row.username}-${row.role}-${row.where}-${index}`}>
                    <td data-label="Name">
                      {row.employee_id ? (
                        <a
                          href={`#/people/${row.employee_id}`}
                          onClick={(e) => {
                            e.preventDefault();
                            onNavigate(`/people/${row.employee_id}`);
                          }}
                        >
                          {row.name}
                        </a>
                      ) : (
                        row.name
                      )}
                    </td>
                    <td data-label="Username">{row.username}</td>
                    <td data-label="Role">{row.role}</td>
                    <td data-label="Where">{row.where}</td>
                    <td data-label="Given">{row.given ? `${row.given}${row.given_by ? ` by ${row.given_by}` : ""}` : ""}</td>
                    <td data-label="Last signed in">{row.last_signed_in}</td>
                    <td data-label="Authenticator">{row.authenticator}</td>
                    <td data-label="To check" className={row.to_check ? "to-check" : undefined}>
                      {row.to_check}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {maySign && rows !== null && (
        <form className="card-block stack sign-off" onSubmit={signOff} aria-labelledby="sign-off-heading">
          <h3 id="sign-off-heading">Sign off the review</h3>
          <p className="muted small">
            Signing off records that you read the whole list and took away access no longer needed. It is kept for the
            auditor.
          </p>
          <label>
            What you changed or asked about (optional)
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={2000} />
          </label>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Sign off the review
            </button>
          </div>
        </form>
      )}
      {reviews !== null && reviews.length > 0 && (
        <section aria-labelledby="sign-offs-heading">
          <h3 id="sign-offs-heading">Sign-offs</h3>
          <ul className="plain history">
            {reviews.map((review) => (
              <li key={review.id}>
                <p>
                  <strong>{dmyTime(review.reviewed_at)}</strong>{" "}
                  <span className="muted small">
                    by {review.reviewed_by_name}, {review.accounts} accounts
                  </span>
                </p>
                {review.notes && <p className="small">{review.notes}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
