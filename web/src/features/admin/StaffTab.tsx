import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, plainMessage, post } from "../../api/client";
import type { Account, Employee, Paginated } from "../../api/types";

interface Props {
  campusId: number | null;
  onNavigate: (to: string) => void;
}

/**
 * Staff on file who cannot sign in yet. Opening an account emails them an invitation to choose their own
 * password: nobody in HR ever knows it.
 */
export function StaffTab({ campusId, onNavigate }: Props) {
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  const [staff, setStaff] = useState<Employee[] | null>(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const params = new URLSearchParams({ has_account: "0", status: "active" });
  if (search) params.set("q", search);
  if (campusId) params.set("campus", String(campusId));
  const query = params.toString();

  useEffect(() => {
    let current = true;
    get<Paginated<Employee>>(`/employees/?${query}`)
      .then((page) => current && setStaff(page.results))
      .catch((err) => current && setError(errorMessage(err, "Could not load the staff list.")));
    return () => {
      current = false;
    };
  }, [query, version]);

  async function open(employee: Employee) {
    setBusy(employee.id);
    setError(null);
    setNotice(null);
    try {
      const account = await post<Account>("/accounts/", { employee: employee.id });
      setNotice(
        account.emailed
          ? `Account opened for ${employee.full_name}, username ${account.username}. The invitation to choose a password was sent to ${account.email}.`
          : `Account opened for ${employee.full_name}, username ${account.username}, but the invitation could not be sent. Send it again from Accounts, in Admin.`,
      );
      setVersion((v) => v + 1);
    } catch (err) {
      setError(plainMessage(err, "The account was not opened. Try again."));
    } finally {
      setBusy(null);
    }
  }

  function searchFor(e: FormEvent) {
    e.preventDefault();
    setSearch(text.trim());
  }

  return (
    <section aria-labelledby="staff-heading">
      <h2 id="staff-heading" className="sr-only">
        Staff without an account
      </h2>
      <p className="muted">
        Opening an account emails the person a link to choose their own password. They sign in with the employee role
        on their campus; give any other role from Accounts.
      </p>
      <form className="filters" role="search" onSubmit={searchFor}>
        <label className="grow">
          <span className="sr-only">Find a member of staff</span>
          <input
            type="search"
            placeholder="Name or employee number"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <button type="submit" className="secondary">
          Find
        </button>
      </form>
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
      {staff === null && !error && <p className="loading">Loading…</p>}
      {staff !== null && staff.length === 0 && <p className="muted">Every member of staff here has an account.</p>}
      {staff !== null && staff.length > 0 && (
        <ul className="plain accounts" aria-label="Staff without an account">
          {staff.map((employee) => (
            <li key={employee.id}>
              <div>
                <strong>{employee.full_name}</strong>
                <br />
                <span className="muted small">
                  {employee.employee_no} · {employee.campus_name}
                  {employee.position_title ? ` · ${employee.position_title}` : ""}
                </span>
                <br />
                <span className="small">{employee.email || "No email address on file"}</span>
              </div>
              <div className="actions">
                {employee.email ? (
                  <button
                    disabled={busy !== null}
                    onClick={() => open(employee)}
                    aria-label={`Open an account for ${employee.full_name}`}
                  >
                    Open an account
                  </button>
                ) : (
                  <a
                    href={`#/people/${employee.id}`}
                    onClick={(e) => {
                      e.preventDefault();
                      onNavigate(`/people/${employee.id}`);
                    }}
                  >
                    Add an email address first
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
