import type { ReactNode } from "react";
import type { Me } from "../api/types";
import { initials } from "./format";
import { jobTitle } from "./people";
import { Popover } from "./Popover";

interface Props {
  me: Me;
  open: boolean;
  phone: boolean;
  onToggle: () => void;
  onClose: () => void;
  onNavigate: (to: string) => void;
  onSignOut: () => void;
  /** On a phone the campus switch lives here, as the header has no room for it. */
  campusSwitch?: ReactNode;
}

const MINE = [
  { path: "/leave", label: "My leave", desc: "Days left and your requests", staff: true },
  { path: "/me", label: "My contract", desc: "Your appointment and its terms", staff: false },
  { path: "/my-record", label: "My record", desc: "What the School holds about you", staff: false },
  { path: "/account", label: "My account", desc: "Password, sign-in email and devices", staff: false },
];

/** The person's own pages and Sign out, behind their initials. */
export function AccountMenu({ me, open, phone, onToggle, onClose, onNavigate, onSignOut, campusSwitch }: Props) {
  const title = jobTitle(me);
  return (
    <div className="account">
      <button className="avatar-button" aria-expanded={open} aria-label={`Signed in as ${me.name}`} onClick={onToggle}>
        <span className="avatar">{initials(me.name)}</span>
      </button>
      {open && (
        <Popover label="Your account" phone={phone} onClose={onClose}>
          <div className="popover-head stacked">
            <strong>{me.name}</strong>
            <span className="muted small">{title}</span>
          </div>
          {campusSwitch}
          <ul className="menu-list">
            {MINE.filter((item) => !item.staff || me.employee_id !== null).map((item) => (
              <li key={item.path}>
                <a
                  href={`#${item.path}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onClose();
                    onNavigate(item.path);
                  }}
                >
                  <span className="menu-label">{item.label}</span>
                  <span className="muted small">{item.desc}</span>
                </a>
              </li>
            ))}
          </ul>
          <div className="popover-foot">
            <button className="secondary" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </Popover>
      )}
    </div>
  );
}
