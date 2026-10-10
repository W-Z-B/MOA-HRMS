import { useCallback, useEffect, useState, type ReactNode } from "react";
import { get, plainMessage, post } from "../../api/client";
import {
  ADMIN_ROLES,
  CASE_ROLES,
  LETTER_ROLES,
  PAYROLL_READ_ROLES,
  hasAnyRole,
  type HomeSummary,
  type LeaveBalance,
  type LeaveRequest,
  type Me,
  type MyTerms,
  type Paginated,
} from "../../api/types";
import { dmy, inDays, longDate, num } from "../../app/format";
import { useFrame } from "../../app/frame";
import { shortCampus, usesCampusSwitch } from "../../app/people";
import { pagesFor } from "../../app/router";
import { DecisionRow } from "./decisions";
import { dates, useLeaveToDecide } from "./leave";

interface Props {
  me: Me;
  campusId: number | null;
  onNavigate: (to: string) => void;
}

interface Shortcut {
  title: string;
  sub: string;
  to: string;
}

interface Figure {
  label: string;
  value: string | number;
  note: string;
}

interface Item {
  key: string;
  tag: string;
  alert?: boolean;
  who: string;
  detail: string;
  action?: { label: string; run: () => void };
  done?: string;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const first = (name: string) => name.split(" ")[0];
const OWN = new Set(["/", "/to-do", "/me", "/my-record", "/account", "/leave", "/incidents", "/attendance", "/payroll"]);

function Shortcuts({ items, onNavigate }: { items: Shortcut[]; onNavigate: (to: string) => void }) {
  return (
    <nav className="shortcuts" aria-label="Shortcuts">
      {items.map((s) => (
        <a
          key={s.title}
          href={`#${s.to}`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(s.to);
          }}
        >
          <span className="shortcut-title">{s.title}</span>
          <span className="shortcut-sub">{s.sub}</span>
        </a>
      ))}
    </nav>
  );
}

function Figures({ items }: { items: Figure[] }) {
  if (items.length === 0) return null;
  return (
    <section className="figures" aria-label="Figures">
      {items.map((f) => (
        <div className="figure" key={f.label}>
          <span className="figure-label">{f.label}</span>
          <span className="figure-value">{f.value}</span>
          <span className="figure-note">{f.note}</span>
        </div>
      ))}
    </section>
  );
}

function Panel({
  title,
  more,
  children,
}: {
  title: string;
  more?: { label: string; to: string; go: (to: string) => void };
  children: ReactNode;
}) {
  const id = `panel-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section className="panel-card" aria-labelledby={id}>
      <div className="panel-card-head">
        <h2 id={id}>{title}</h2>
        {more && (
          <a
            href={`#${more.to}`}
            onClick={(e) => {
              e.preventDefault();
              more.go(more.to);
            }}
          >
            {more.label}
          </a>
        )}
      </div>
      {children}
    </section>
  );
}

function Items({ items, empty }: { items: Item[]; empty: string }) {
  if (items.length === 0) return <p className="panel-empty">{empty}</p>;
  return (
    <ul className="rows">
      {items.map((it) => (
        <li key={it.key} className="item-row">
          <span className="stacked grow">
            {it.tag && <span className={it.alert ? "item-tag alert" : "item-tag"}>{it.tag}</span>}
            <span className="strong">{it.who}</span>
            <span className="muted small">{it.detail}</span>
          </span>
          {it.done ? (
            <span role="status" className="chip chip-approved">
              {it.done}
            </span>
          ) : (
            it.action && (
              <button className="secondary small-button" onClick={it.action.run} aria-label={`${it.action.label}: ${it.who}`}>
                {it.action.label}
              </button>
            )
          )}
        </li>
      ))}
    </ul>
  );
}

function Bars({ rows }: { rows: { key: string; name: string; sub: string; share: number; summary: string }[] }) {
  return (
    <ul className="rows">
      {rows.map((r) => (
        <li key={r.key} className="bar-row">
          <span className="stacked bar-name">
            <span className="strong">{r.name}</span>
            <span className="muted small">{r.sub}</span>
          </span>
          <span className="bar" aria-hidden="true">
            <span style={{ width: `${Math.min(100, Math.round(r.share * 100))}%` }} />
          </span>
          <span className="muted small num bar-summary">{r.summary}</span>
        </li>
      ))}
    </ul>
  );
}

/** The steps a request goes through, and where this one is. */
function Progress({ r }: { r: LeaveRequest }) {
  const step = (s: "manager" | "hr") => r.decisions.find((d) => d.step === s);
  const mark = (s: "manager" | "hr", waitingIn: string) => {
    const decision = step(s);
    if (decision) return decision.outcome === "approved" ? "done" : "stopped";
    return r.state === waitingIn ? "current" : "todo";
  };
  const items = [
    { label: "Sent", mark: r.state === "draft" ? "todo" : "done", detail: "" },
    { label: "Manager", mark: mark("manager", "submitted"), detail: step("manager")?.actor_name ?? r.manager_name ?? "" },
    { label: "Human Resources", mark: mark("hr", "supervisor_approved"), detail: step("hr")?.actor_name ?? "" },
  ];
  return (
    <ol className="steps" aria-label="Progress">
      {items.map((s) => (
        <li key={s.label} className={s.mark}>
          <span className="label">{s.label}</span>
          {s.detail && <span className="muted small">{s.detail}</span>}
        </li>
      ))}
    </ol>
  );
}

const STATE: Record<string, [string, string]> = {
  draft: ["Draft, not sent", "chip-draft"],
  submitted: ["With the manager", "chip-waiting"],
  supervisor_approved: ["With Human Resources", "chip-waiting"],
};

/** The employee's own: days left, their open requests, their post. */
function useOwn(me: Me, active: boolean) {
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [terms, setTerms] = useState<MyTerms | null>(null);
  useEffect(() => {
    if (!active || me.employee_id === null) return;
    let current = true;
    get<{ balances: LeaveBalance[] }>("/leave/ledger/balances/")
      .then((r) => current && setBalances(r.balances))
      .catch(() => undefined);
    get<Paginated<LeaveRequest>>(`/leave/requests/?employee=${me.employee_id}`)
      .then((r) => current && setRequests(r.results))
      .catch(() => undefined);
    get<MyTerms>("/contracts/mine/")
      .then((t) => current && setTerms(t))
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [active, me.employee_id]);
  return { balances, requests, terms };
}

/**
 * Home (item 2.30), in place of one fixed dashboard: each role sees its own work first. HR and heads of unit
 * decide leave on the spot; the Principal sees the establishment; an employee sees their days left, their
 * requests and their post. Shortcuts lead to the pages the role uses; search finds the rest.
 */
export function HomeScreen({ me, campusId, onNavigate }: Props) {
  const frame = useFrame();
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [invited, setInvited] = useState<Record<number, string>>({});
  const [inviteError, setInviteError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<HomeSummary>(`/home/${campusId ? `?campus=${campusId}` : ""}`)
      .then((s) => {
        setSummary(s);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load your Home. Try again in a moment.")));
  }, [campusId]);
  useEffect(load, [load]);

  const persona = summary?.persona;
  const decides = persona === "hr" || persona === "manager" || (summary?.leave.mine ?? 0) > 0;
  const leave = useLeaveToDecide(decides);
  const own = useOwn(me, persona === "employee");

  function decided() {
    frame.decided();
    load();
  }

  async function invite(employee: number, name: string) {
    setInviteError(null);
    try {
      const account = await post<{ email: string; emailed: boolean }>("/accounts/", { employee });
      setInvited((done) => ({
        ...done,
        [employee]: account.emailed ? `Invited. The link went to ${account.email}` : "Account opened; send the link from Admin",
      }));
    } catch (err) {
      setInviteError(plainMessage(err, `${name} was not invited. Try again from Admin.`));
    }
  }

  if (!summary)
    return (
      <>
        <h1>Home</h1>
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : (
          <p className="loading">Loading…</p>
        )}
      </>
    );

  const staff = summary.staff;
  const go = onNavigate;
  const chosen = me.campuses?.find((c) => c.id === campusId);
  const scope = chosen
    ? chosen.name
    : usesCampusSwitch(me)
      ? "All campuses"
      : (me.campuses?.[0]?.name ?? me.campus ?? "");
  const day = longDate(summary.as_at);
  const eyebrow =
    persona === "manager"
      ? [day, me.heads?.[0] ?? me.unit].filter(Boolean).join(" · ")
      : persona === "employee"
        ? day
        : [day, scope].filter(Boolean).join(" · ");

  // Figures shared by several Homes.
  const contracts = (summary.ending ?? []).filter((e) => e.what === "contract");
  const probations = (summary.ending ?? []).filter((e) => e.what === "probation");
  const soonest = (list: typeof contracts, none: string) =>
    list.length > 0 ? `${list[0].name}, ${dmy(list[0].on)}` : none;
  const horizon = `in ${summary.ending_days} days`;
  const activeStaff: Figure | null = staff && {
    label: "Active staff",
    value: staff.active,
    note:
      staff.campuses.length > 1
        ? staff.campuses.map((c) => `${shortCampus(c.name)} ${c.active}`).join(" · ")
        : (staff.campuses[0]?.name ?? ""),
  };
  const postsFilled: Figure | null = staff && {
    label: "Posts filled",
    value: `${staff.filled} of ${staff.posts}`,
    note:
      staff.vacant + staff.frozen === 0
        ? "Every post filled"
        : [staff.vacant && `${staff.vacant} vacant`, staff.frozen && `${staff.frozen} frozen`].filter(Boolean).join(" · "),
  };
  const ending: Figure = {
    label: `Contracts ending ${horizon}`,
    value: contracts.length,
    note: soonest(contracts, `None ${horizon}`),
  };
  const waitingAll = summary.leave.waiting ?? 0;
  const mine = summary.leave.mine;

  let shortcuts: Shortcut[] = [];
  let figures: (Figure | null)[] = [];
  if (persona === "hr") {
    shortcuts = [
      { title: "People", sub: staff ? plural(staff.active, "staff file", "staff files") : "Staff files", to: "/people" },
      { title: "Leave requests", sub: `${waitingAll} waiting for a decision`, to: "/leave/decide" },
      ...(hasAnyRole(me, LETTER_ROLES) ? [{ title: "Letters", sub: "Write and issue letters", to: "/letters" }] : []),
      { title: "Organisation", sub: "Units, posts and grades", to: "/organisation" },
      { title: "Reports", sub: "Headcount and establishment", to: "/reports" },
      ...(hasAnyRole(me, PAYROLL_READ_ROLES) ? [{ title: "Payroll", sub: "Pay runs and statutory rates", to: "/payroll" }] : []),
      ...(hasAnyRole(me, ADMIN_ROLES) ? [{ title: "Admin", sub: "Accounts, audit and setup", to: "/admin" }] : []),
    ];
    figures = [
      activeStaff,
      {
        label: "Leave awaiting a decision",
        value: waitingAll,
        note: mine > 0 ? `${mine} ${mine === 1 ? "is" : "are"} yours to decide` : "Nothing is yours to decide",
      },
      postsFilled,
      ending,
    ];
  } else if (persona === "manager") {
    const team = summary.team ?? [];
    shortcuts = [
      { title: "Leave requests", sub: mine > 0 ? `${mine} waiting for you` : "Nothing waiting for you", to: "/leave/decide" },
      { title: "People", sub: "Your unit and the directory", to: "/people" },
      ...(hasAnyRole(me, CASE_ROLES) ? [{ title: "Cases", sub: "Disciplinary cases and grievances", to: "/cases" }] : []),
      { title: "Reports", sub: "Headcount and establishment", to: "/reports" },
    ];
    figures = [
      { label: "Staff in your unit", value: team.length, note: me.heads?.join(", ") || (me.unit ?? "") },
      {
        label: "Waiting for your decision",
        value: mine,
        note: leave.toDecide?.length ? leave.toDecide.map((r) => first(r.employee_name)).join(", ") : "Nothing waiting",
      },
      { label: "Probation ending", value: probations.length, note: soonest(probations, `None ${horizon}`) },
    ];
  } else if (persona === "principal") {
    shortcuts = [
      { title: "Reports", sub: "Headcount and establishment", to: "/reports" },
      { title: "People", sub: staff ? plural(staff.active, "staff file", "staff files") : "Staff files", to: "/people" },
      { title: "Organisation", sub: "Units, posts and grades", to: "/organisation" },
      ...(hasAnyRole(me, LETTER_ROLES) ? [{ title: "Letters", sub: "Letters issued", to: "/letters" }] : []),
      ...(hasAnyRole(me, CASE_ROLES) ? [{ title: "Cases", sub: "Disciplinary cases and grievances", to: "/cases" }] : []),
    ];
    figures = [
      activeStaff,
      postsFilled,
      ending,
      { label: "Leave awaiting a decision", value: waitingAll, note: waitingAll ? "With managers and HR" : "Nothing waiting" },
    ];
  } else if (persona === "employee") {
    const annual = own.balances.find((b) => b.code === "ANN");
    shortcuts = [
      ...(me.employee_id !== null
        ? [
            { title: "My leave", sub: annual ? `${inDays(Math.max(num(annual.available), 0))} of annual leave left` : "Days left and your requests", to: "/leave" },
            { title: "Attendance", sub: "Check in and out", to: "/attendance" },
            { title: "My payslips", sub: "Payslips once a pay run is disbursed", to: "/payroll" },
          ]
        : []),
      { title: "My contract", sub: "Your appointment and its terms", to: "/me" },
      { title: "My record", sub: "What the School holds about you", to: "/my-record" },
      { title: "Report an incident", sub: "Accidents and dangerous occurrences", to: "/incidents/new" },
    ];
    figures = own.balances
      .filter((b) => b.limited)
      .map((b) => ({
        label: `${b.name} left`,
        value: inDays(Math.max(num(b.available), 0)),
        note: num(b.pending) > 0 ? `${inDays(b.pending)} awaiting a decision` : "Nothing awaiting a decision",
      }));
  } else {
    // Other office roles: the pages their roles open, and the staff figures if they read the staff list.
    shortcuts = pagesFor(me)
      .filter((page) => !page.later && !OWN.has(page.path))
      .map((page) => ({ title: page.label, sub: page.desc, to: page.path }));
    figures = staff ? [activeStaff, postsFilled, ending] : [];
  }

  const attention: Item[] = [
    ...(summary.ending ?? []).map((e) => ({
      key: `${e.what}-${e.employee}`,
      tag: `${e.what === "contract" ? "Contract ends" : "Probation ends"} ${dmy(e.on)}`,
      alert: true,
      who: e.name,
      detail: `${e.position} · ${e.campus}`,
      action: { label: "Open file", run: () => go(`/people/${e.employee}`) },
    })),
    ...(summary.no_account?.latest ?? []).map((p) => ({
      key: `account-${p.employee}`,
      tag: "No account yet",
      alert: true,
      who: p.name,
      detail: [p.started && `Started ${dmy(p.started)}`, p.campus].filter(Boolean).join(" · "),
      action: { label: "Invite", run: () => invite(p.employee, p.name) },
      done: invited[p.employee],
    })),
  ];
  const more = (summary.no_account?.count ?? 0) - (summary.no_account?.latest.length ?? 0);

  return (
    <div className="home">
      <div className="page-head">
        <div className="stacked">
          <span className="eyebrow">{eyebrow}</span>
          <h1>Home</h1>
        </div>
        {persona === "employee" && me.employee_id !== null && <button onClick={() => go("/leave")}>Request leave</button>}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {shortcuts.length > 0 && <Shortcuts items={shortcuts} onNavigate={go} />}
      <Figures items={figures.filter((f): f is Figure => f !== null)} />

      <div className="home-columns">
        <div className="home-main">
          {decides && (
            <Panel
              title={persona === "manager" ? "Waiting for your decision" : "Waiting for a decision"}
              more={{ label: "All leave requests", to: "/leave/decide", go }}
            >
              {leave.error && (
                <p role="alert" className="error panel-empty">
                  {leave.error}
                </p>
              )}
              {leave.toDecide === null && !leave.error && <p className="loading">Loading…</p>}
              {leave.toDecide !== null && (
                <>
                  {leave.toDecide.length + leave.elsewhere.length === 0 ? (
                    <p className="panel-empty">Nothing waiting for you.</p>
                  ) : (
                    <ul className="rows decisions">
                      {leave.toDecide.map((r) => (
                        <DecisionRow key={r.id} request={r} mode="decide" onDecided={decided} />
                      ))}
                      {leave.elsewhere.map((r) => (
                        <DecisionRow key={r.id} request={r} mode="watch" onDecided={decided} />
                      ))}
                    </ul>
                  )}
                </>
              )}
            </Panel>
          )}

          {persona === "employee" && me.employee_id !== null && (
            <Panel title="Your requests" more={{ label: "My leave", to: "/leave", go }}>
              {own.requests.filter((r) => STATE[r.state]).length === 0 ? (
                <p className="panel-empty">Nothing is waiting for a decision.</p>
              ) : (
                <ul className="rows">
                  {own.requests
                    .filter((r) => STATE[r.state])
                    .map((r) => (
                      <li key={r.id} className="own-request">
                        <div className="spread">
                          <span className="stacked">
                            <span className="strong">{r.leave_type_name}</span>
                            <span className="muted num">
                              {dates(r)} · <strong className="ink">{inDays(r.days)}</strong>
                            </span>
                          </span>
                          <span className={`chip ${STATE[r.state][1]}`}>{STATE[r.state][0]}</span>
                        </div>
                        <Progress r={r} />
                      </li>
                    ))}
                </ul>
              )}
            </Panel>
          )}

          {persona === "hr" && staff && (
            <Panel title="Headcount by campus" more={{ label: "Reports", to: "/reports", go }}>
              <Bars
                rows={staff.campuses.map((c) => ({
                  key: c.code,
                  name: c.name,
                  sub: plural(c.posts, "approved post", "approved posts"),
                  share: c.posts ? c.active / c.posts : 0,
                  summary: plural(c.active, "member of staff", "staff"),
                }))}
              />
            </Panel>
          )}

          {persona === "principal" && summary.units && (
            <Panel title="Establishment by unit" more={{ label: "Reports", to: "/reports", go }}>
              <Bars
                rows={summary.units.map((u) => ({
                  key: String(u.id),
                  name: u.name,
                  sub: u.campus,
                  share: u.posts ? u.filled / u.posts : 0,
                  summary: [
                    `${u.filled} of ${u.posts} filled`,
                    u.vacant ? `${u.vacant} vacant` : "",
                    u.frozen ? `${u.frozen} frozen` : "",
                  ]
                    .filter(Boolean)
                    .join(" · "),
                }))}
              />
            </Panel>
          )}
        </div>

        <div className="home-side">
          {persona === "hr" && (
            <Panel title="Needs attention">
              {inviteError && (
                <p role="alert" className="error panel-empty">
                  {inviteError}
                </p>
              )}
              <Items items={attention} empty="Nothing needs attention on these campuses." />
              {more > 0 && (
                <p className="panel-more">
                  <a
                    href="#/admin/staff"
                    onClick={(e) => {
                      e.preventDefault();
                      go("/admin/staff");
                    }}
                  >
                    {plural(more, "more member of staff has", "more members of staff have")} no account
                  </a>
                </p>
              )}
            </Panel>
          )}

          {persona === "manager" && (
            <Panel title="Your team">
              <Items
                empty="Nobody is recorded in the units you head."
                items={(summary.team ?? []).map((m) => ({
                  key: String(m.employee),
                  tag: m.is_me
                    ? "You, head of unit"
                    : m.probation_end
                      ? `Probation ends ${dmy(m.probation_end)}`
                      : m.ends
                        ? `Contract ends ${dmy(m.ends)}`
                        : `Started ${dmy(m.started)}`,
                  alert: !m.is_me && Boolean(m.probation_end || m.ends),
                  who: m.name,
                  detail: `${m.position} · ${m.appointment}`,
                  action: m.is_me ? undefined : { label: "Open file", run: () => go(`/people/${m.employee}`) },
                }))}
              />
            </Panel>
          )}

          {persona === "employee" && (
            <Panel title="Your employment">
              <Items
                empty="Your account is not linked to a staff record yet. Ask Human Resources."
                items={
                  own.terms
                    ? [
                        {
                          key: "position",
                          tag: "Position",
                          who: own.terms.position ?? "Not recorded",
                          detail: [own.terms.unit, own.terms.campus].filter(Boolean).join(" · "),
                        },
                        {
                          key: "appointment",
                          tag: "Appointment",
                          who: own.terms.appointment_type ?? "Not recorded",
                          detail: own.terms.start_date ? `Since ${dmy(own.terms.start_date)}` : "",
                          action: { label: "My contract", run: () => go("/me") },
                        },
                        ...(own.terms.manager
                          ? [{ key: "manager", tag: "Manager", who: own.terms.manager, detail: "Decides your leave first" }]
                          : []),
                      ]
                    : []
                }
              />
            </Panel>
          )}

          {(persona === "principal" || (persona === "office" && staff)) && (
            <Panel title="Ending soon">
              <Items items={attention} empty={`No contract or probation ends ${horizon}.`} />
            </Panel>
          )}

          {persona === "principal" && (
            <Panel title="Reports">
              <Items
                empty=""
                items={[
                  {
                    key: "headcount",
                    tag: "",
                    who: "Headcount by campus",
                    detail: "Active staff on each campus today",
                    action: { label: "Open", run: () => go("/reports") },
                  },
                  {
                    key: "establishment",
                    tag: "",
                    who: "Establishment against actual",
                    detail: "Approved posts against the people in them",
                    action: { label: "Open", run: () => go("/reports") },
                  },
                ]}
              />
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
