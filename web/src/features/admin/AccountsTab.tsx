import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage, get, plainMessage, post } from "../../api/client";
import {
  ACCOUNT_WRITE_ROLES,
  hasAnyRole,
  type Account,
  type Campus,
  type Grant,
  type LinkSent,
  type Me,
  type Paginated,
  type RoleChoice,
} from "../../api/types";
import { dmyTime } from "../../app/format";

const STATE_LABEL: Record<Account["state"], string> = {
  invited: "Invited",
  active: "In use",
  switched_off: "Switched off",
};

interface Props {
  me: Me;
  campusId: number | null;
}

/** Every account the person may see, with what they may do to each. The server checks every action again. */
export function AccountsTab({ me, campusId }: Props) {
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [roles, setRoles] = useState<RoleChoice[]>([]);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [error, setError] = useState<string | null>(null);

  const params = new URLSearchParams();
  if (search) params.set("q", search);
  if (state) params.set("state", state);
  if (campusId) params.set("campus", String(campusId));
  const query = params.toString();

  useEffect(() => {
    let current = true;
    get<Paginated<Account>>(`/accounts/${query ? `?${query}` : ""}`)
      .then((page) => {
        if (!current) return;
        setAccounts(page.results);
        setNext(page.next);
        setCount(page.count);
        setError(null);
      })
      .catch((err) => current && setError(errorMessage(err, "Could not load the accounts.")));
    return () => {
      current = false;
    };
  }, [query]);

  useEffect(() => {
    get<RoleChoice[]>("/accounts/roles/").then(setRoles).catch(() => setRoles([]));
    get<Paginated<Campus>>("/org/campuses/").then((page) => setCampuses(page.results)).catch(() => setCampuses([]));
  }, []);

  async function showMore() {
    if (!next) return;
    try {
      const page = await get<Paginated<Account>>(`/accounts/${new URL(next, window.location.origin).search}`);
      setAccounts((shown) => [...(shown ?? []), ...page.results]);
      setNext(page.next);
    } catch (err) {
      setError(errorMessage(err, "Could not load more accounts."));
    }
  }

  function searchFor(e: FormEvent) {
    e.preventDefault();
    setSearch(text.trim());
  }

  const replace = (updated: Account) =>
    setAccounts((shown) => (shown ?? []).map((account) => (account.id === updated.id ? updated : account)));

  return (
    <section aria-labelledby="accounts-heading">
      <h2 id="accounts-heading" className="sr-only">
        Accounts
      </h2>
      <form className="filters" role="search" onSubmit={searchFor}>
        <label className="grow">
          <span className="sr-only">Find an account</span>
          <input
            type="search"
            placeholder="Name, username, email or employee number"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <label>
          <span className="sr-only">Show</span>
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">Every account</option>
            <option value="invited">Invited, no password yet</option>
            <option value="active">In use</option>
            <option value="switched_off">Switched off</option>
          </select>
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
      {accounts === null && !error && <p className="loading">Loading…</p>}
      {accounts !== null && (
        <p className="muted small" aria-live="polite">
          {count === 1 ? "1 account" : `${count} accounts`}
        </p>
      )}
      {accounts !== null && accounts.length > 0 && (
        <ul className="plain accounts" aria-label="Accounts">
          {accounts.map((account) => (
            <AccountCard
              key={account.id}
              account={account}
              me={me}
              roles={roles}
              campuses={campuses}
              onChanged={replace}
            />
          ))}
        </ul>
      )}
      {next && (
        <div className="actions">
          <button className="secondary" onClick={showMore}>
            Show more
          </button>
        </div>
      )}
    </section>
  );
}

type Opened = "" | "role" | "off" | "on" | "authenticator";

interface CardProps {
  account: Account;
  me: Me;
  roles: RoleChoice[];
  campuses: Campus[];
  onChanged: (account: Account) => void;
}

function AccountCard({ account, me, roles, campuses, onChanged }: CardProps) {
  const [opened, setOpened] = useState<Opened>("");
  const [reason, setReason] = useState("");
  const [role, setRole] = useState("");
  const [campus, setCampus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const giveable = roles.filter((r) => r.may_give);
  const mayGive = new Set(giveable.map((r) => r.code));
  // Only someone who could give every role the account holds may change it, and nobody changes their own.
  const mayChange =
    hasAnyRole(me, ACCOUNT_WRITE_ROLES) && account.id !== me.id && account.roles.every((g) => mayGive.has(g.role));
  const isAdministrator = hasAnyRole(me, ["administrator"]);
  const chosen = roles.find((r) => r.code === role);
  const who = account.name;
  const sendLabel = account.state === "invited" ? "Send the invitation again" : "Send a password link";

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
      setOpened("");
      setReason("");
      setRole("");
      setCampus("");
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
    } finally {
      setBusy(false);
    }
  }

  const sendLink = () =>
    run(async () => {
      const sent = await post<LinkSent>(`/accounts/${account.id}/send-link/`);
      const what = sent.kind === "invitation" ? "The invitation" : "A link to choose a new password";
      return sent.emailed ? `${what} was sent to ${sent.email}.` : `${what} could not be sent to ${sent.email}.`;
    });

  const takeAway = (grant: Grant) =>
    run(async () => {
      onChanged(await api<Account>(`/accounts/${account.id}/roles/${grant.id}/`, { method: "DELETE" }));
      return `${grant.role_name} (${grant.where}) taken away. ${who} is signed out, so it applies at once.`;
    });

  function give(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      const body = { role, campus: campus ? Number(campus) : null };
      onChanged(await post<Account>(`/accounts/${account.id}/roles/`, body));
      return `${chosen?.name ?? "Role"} given. ${who} is signed out, so it applies from their next sign-in.`;
    });
  }

  function withReason(e: FormEvent) {
    e.preventDefault();
    const action = opened === "off" ? "deactivate" : opened === "on" ? "reactivate" : "reset-authenticator";
    const done =
      opened === "off"
        ? `Switched off. ${who} cannot sign in, and every session has ended.`
        : opened === "on"
          ? `Switched on. ${who} can sign in again.`
          : `Authenticator removed. ${who} sets up a new one at their next sign-in.`;
    void run(async () => {
      onChanged(await post<Account>(`/accounts/${account.id}/${action}/`, { reason }));
      return done;
    });
  }

  const reasonLabel =
    opened === "off" ? "Why switch it off?" : opened === "on" ? "Why switch it on?" : "Why reset the authenticator?";
  const formLabel =
    opened === "off"
      ? `Switch off the account of ${who}`
      : opened === "on"
        ? `Switch on the account of ${who}`
        : `Reset authenticator for ${who}`;

  return (
    <li className={`account state-${account.state}`}>
      <div>
        <strong>{who}</strong> <span className={`chip chip-account-${account.state}`}>{STATE_LABEL[account.state]}</span>
        <br />
        <span className="muted small">
          {account.username} · {account.email || "no email address"}
          {account.employee ? ` · ${account.employee.employee_no}, ${account.employee.campus_name}` : " · not on the staff"}
        </span>
        <br />
        <span className="muted small">
          {account.last_login ? `Last signed in ${dmyTime(account.last_login)}` : "Never signed in"}
          {account.authenticator ? " · authenticator set up" : ""}
        </span>
      </div>
      <ul className="plain grants" aria-label={`Roles of ${who}`}>
        {account.roles.length === 0 && <li className="muted small">No role</li>}
        {account.roles.map((grant) => (
          <li key={grant.id}>
            <span>
              {grant.role_name}, {grant.where}
            </span>
            {mayChange && account.is_active && (
              <button
                className="link"
                disabled={busy}
                aria-label={`Take away ${grant.role_name}, ${grant.where}, from ${who}`}
                onClick={() => takeAway(grant)}
              >
                Take away
              </button>
            )}
          </li>
        ))}
      </ul>
      {mayChange && opened === "" && (
        <div className="actions">
          {account.is_active && (
            <button className="secondary" disabled={busy} onClick={sendLink} aria-label={`${sendLabel} to ${who}`}>
              {sendLabel}
            </button>
          )}
          {account.is_active && giveable.length > 0 && (
            <button className="secondary" disabled={busy} onClick={() => setOpened("role")} aria-label={`Give a role to ${who}`}>
              Give a role
            </button>
          )}
          <button
            className="secondary"
            disabled={busy}
            onClick={() => setOpened(account.is_active ? "off" : "on")}
            aria-label={`${account.is_active ? "Switch off" : "Switch on"} the account of ${who}`}
          >
            {account.is_active ? "Switch off" : "Switch on"}
          </button>
          {isAdministrator && account.authenticator && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => setOpened("authenticator")}
              aria-label={`Reset authenticator for ${who}`}
            >
              Reset authenticator
            </button>
          )}
        </div>
      )}
      {opened === "role" && (
        <form className="sub-form stack" onSubmit={give} aria-label={`Give a role to ${who}`}>
          <div className="grid2">
            <label>
              Role
              <select value={role} onChange={(e) => setRole(e.target.value)} required>
                <option value="">Choose</option>
                {giveable.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Campus
              <select value={campus} onChange={(e) => setCampus(e.target.value)} required={chosen?.needs_campus ?? true}>
                <option value="">{chosen && !chosen.needs_campus ? "All campuses" : "Choose"}</option>
                {campuses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted small">{who} is signed out when the role is given, so it applies from their next sign-in.</p>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setOpened("")}>
              Cancel
            </button>
            <button type="submit" disabled={busy}>
              Give the role
            </button>
          </div>
        </form>
      )}
      {(opened === "off" || opened === "on" || opened === "authenticator") && (
        <form className="sub-form stack" onSubmit={withReason} aria-label={formLabel}>
          <label>
            {reasonLabel}
            <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} required />
          </label>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setOpened("")}>
              Cancel
            </button>
            <button type="submit" disabled={busy || !reason.trim()}>
              {opened === "off" ? "Switch off" : opened === "on" ? "Switch on" : "Reset authenticator"}
            </button>
          </div>
        </form>
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
    </li>
  );
}
