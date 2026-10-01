import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, plainMessage, post, remove } from "../../api/client";
import { SETUP_WRITE_ROLES, hasAnyRole, type HolidayCalendar, type Me } from "../../api/types";
import { dmy } from "../../app/format";

/**
 * Public holidays (item 1.25): the year checked against Guyana's holidays. Days that follow a rule are
 * offered with their date; Phagwah, Eid ul-Adha, Youman Nabi and Deepavali are entered from the gazette.
 */
export function HolidaysTab({ me }: { me: Me }) {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [calendar, setCalendar] = useState<HolidayCalendar | null>(null);
  const [dates, setDates] = useState<Record<string, string>>({});
  const [other, setOther] = useState({ date: "", name: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mayWrite = hasAnyRole(me, SETUP_WRITE_ROLES);

  const load = useCallback(() => {
    get<HolidayCalendar>(`/holidays/calendar/?year=${year}`)
      .then(setCalendar)
      .catch((err) => setError(errorMessage(err, "Could not load the holidays.")));
  }, [year]);

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

  const add = (date: string, name: string) =>
    run(async () => {
      await post("/holidays/", { date, name });
      return `${name} added for ${dmy(date)}.`;
    });
  const drop = (id: number, name: string) =>
    run(async () => {
      await remove(`/holidays/${id}/`);
      return `${name} removed.`;
    });

  function addOther(e: FormEvent) {
    e.preventDefault();
    void add(other.date, other.name).then(() => setOther({ date: "", name: "" }));
  }

  const missing = calendar?.expected.filter((row) => !row.on_file).length ?? 0;

  return (
    <section aria-labelledby="holidays-heading">
      <h2 id="holidays-heading" className="sr-only">
        Public holidays
      </h2>
      <div className="filters">
        <label>
          <span className="sr-only">Year</span>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {[thisYear - 1, thisYear, thisYear + 1].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        {calendar && (
          <span className={missing ? "small overdue" : "muted small"} aria-live="polite">
            {missing ? `${missing} of Guyana's holidays not yet on file for ${year}` : `Every holiday for ${year} is on file`}
          </span>
        )}
      </div>
      <p className="muted small">
        Leave does not count public holidays. Changing one does not change leave already approved.
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
      {calendar?.sundays.map((holiday) => (
        <p key={holiday.id} className="notice">
          {holiday.name} falls on Sunday {dmy(holiday.date)}. If the gazette names a substitute day, add it below.
        </p>
      ))}
      {calendar && (
        <table className="cards">
          <caption className="sr-only">Guyana's public holidays in {year}</caption>
          <thead>
            <tr>
              <th scope="col">Holiday</th>
              <th scope="col">How the date is set</th>
              <th scope="col">On file</th>
              {mayWrite && <th scope="col">Change</th>}
            </tr>
          </thead>
          <tbody>
            {calendar.expected.map((row) => (
              <tr key={row.name}>
                <td data-label="Holiday">{row.name}</td>
                <td data-label="How the date is set">{row.rule}</td>
                <td data-label="On file">
                  {row.on_file ? `${row.on_file.weekday} ${dmy(row.on_file.date)}` : <span className="overdue">Missing</span>}
                </td>
                {mayWrite && (
                  <td data-label="Change" className="actions">
                    {row.on_file && (
                      <button
                        className="link"
                        disabled={busy}
                        onClick={() => drop(row.on_file!.id, row.name)}
                        aria-label={`Remove ${row.name}`}
                      >
                        Remove
                      </button>
                    )}
                    {!row.on_file && row.date && (
                      <button className="secondary" disabled={busy} onClick={() => add(row.date!, row.name)}>
                        Add {dmy(row.date)}
                      </button>
                    )}
                    {!row.on_file && !row.date && (
                      <>
                        <label>
                          <span className="sr-only">Date of {row.name} in the gazette</span>
                          <input
                            type="date"
                            min={`${year}-01-01`}
                            max={`${year}-12-31`}
                            value={dates[row.name] ?? ""}
                            onChange={(e) => setDates({ ...dates, [row.name]: e.target.value })}
                          />
                        </label>
                        <button
                          className="secondary"
                          disabled={busy || !dates[row.name]}
                          onClick={() => add(dates[row.name], row.name)}
                          aria-label={`Add ${row.name}`}
                        >
                          Add
                        </button>
                      </>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {calendar && calendar.others.length > 0 && (
        <>
          <h3>Other holidays on file</h3>
          <ul className="plain grants" aria-label="Other holidays on file">
            {calendar.others.map((holiday) => (
              <li key={holiday.id}>
                <span>
                  {holiday.name}, {holiday.weekday} {dmy(holiday.date)}
                </span>
                {mayWrite && (
                  <button
                    className="link"
                    disabled={busy}
                    onClick={() => drop(holiday.id, holiday.name)}
                    aria-label={`Remove ${holiday.name}`}
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {mayWrite && (
        <form className="sub-form stack" onSubmit={addOther} aria-label="Add another holiday">
          <h3>Add another holiday</h3>
          <p className="muted small">A substitute day the gazette names, or a holiday declared for one year only.</p>
          <div className="grid2">
            <label>
              Date
              <input type="date" value={other.date} onChange={(e) => setOther({ ...other, date: e.target.value })} required />
            </label>
            <label>
              Name
              <input value={other.name} onChange={(e) => setOther({ ...other, name: e.target.value })} maxLength={120} required />
            </label>
          </div>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Add the holiday
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
