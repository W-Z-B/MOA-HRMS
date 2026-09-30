import { useEffect, useState, type ReactNode } from "react";
import { get, post } from "../api/client";
import { isOfficeUser, type Campus, type Me, type Paginated } from "../api/types";
import { NotificationsBell } from "./NotificationsBell";
import { navFor } from "./router";

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
  onLogout: () => void;
  campusId: number | null;
  onCampusChange: (id: number | null) => void;
  children: ReactNode;
}

/** Common frame from the wireframes: side navigation, campus switch, search, user menu; bottom bar on phones. */
export function Shell({ me, path, onNavigate, onLogout, campusId, onCampusChange, children }: Props) {
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const office = isOfficeUser(me);

  useEffect(() => {
    if (!office) return; // the campus switch filters lists an employee does not have
    get<Paginated<Campus>>("/org/campuses/").then((r) => setCampuses(r.results)).catch(() => setCampuses([]));
  }, [office]);

  async function logout() {
    await post("/auth/logout/");
    onLogout();
  }

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">GSA HRMS</span>
        {office && (
          <label className="campus">
            <span className="sr-only">Campus</span>
            <select
              id="campus-switch"
              value={campusId ?? ""}
              onChange={(e) => onCampusChange(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">All campuses</option>
              {campuses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <span className="spacer" />
        <NotificationsBell onNavigate={onNavigate} />
        <span className="user">
          {me.name} <small>{me.roles.join(", ") || "no role"}</small>
        </span>
        <button className="link" onClick={logout}>
          Sign out
        </button>
      </header>
      <nav className="sidenav" aria-label="Main">
        {navFor(me).map((item) => (
          <a
            key={item.path}
            href={`#${item.path}`}
            aria-current={path === item.path || (item.path !== "/" && path.startsWith(item.path)) ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(item.path);
            }}
          >
            {item.label}
          </a>
        ))}
      </nav>
      <main className="content">{children}</main>
    </div>
  );
}
