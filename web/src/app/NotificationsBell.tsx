import { useCallback, useEffect, useState } from "react";
import { get, post } from "../api/client";
import type { Notification } from "../api/types";

interface Props {
  onNavigate: (to: string) => void;
}

const POLL_MS = 60_000;

/** Unread badge in the top bar; opens the inbox, marks items read and follows their links. */
export function NotificationsBell({ onNavigate }: Props) {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);

  const load = useCallback(() => {
    get<{ unread: number; results: Notification[] }>("/notifications/")
      .then((r) => {
        setUnread(r.unread);
        setItems(r.results);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const handle = setInterval(load, POLL_MS);
    return () => clearInterval(handle);
  }, [load]);

  async function openItem(item: Notification) {
    if (!item.read_at) await post(`/notifications/${item.id}/read/`).catch(() => undefined);
    setOpen(false);
    load();
    if (item.link) onNavigate(item.link);
  }

  async function readAll() {
    await post("/notifications/read-all/").catch(() => undefined);
    load();
  }

  return (
    <div className="bell">
      <button className="link" aria-expanded={open} aria-label={`Notifications, ${unread} unread`} onClick={() => setOpen(!open)}>
        <span className="bell-text">Notifications</span>
        {/* Phones show the bell alone; the button's label still says "Notifications". */}
        <svg className="bell-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
          <path
            fill="currentColor"
            d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6V11a7 7 0 0 0-5.5-6.84V3a1.5 1.5 0 0 0-3 0v1.16A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2Z"
          />
        </svg>
        {unread > 0 && <span className="badge">{unread}</span>}
      </button>
      {open && (
        <div className="dropdown" role="dialog" aria-label="Notifications">
          <div className="dropdown-head">
            <strong>Notifications</strong>
            {unread > 0 && (
              <button className="link" onClick={readAll}>
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="muted">Nothing yet.</p>
          ) : (
            <ul>
              {items.slice(0, 15).map((item) => (
                <li key={item.id} className={item.read_at ? "read" : "unread"}>
                  <button className="item" onClick={() => openItem(item)}>
                    <span className={`kind kind-${item.kind}`} aria-hidden="true" />
                    <span>
                      <span className="title">{item.title}</span>
                      <span className="muted small">{new Date(item.created_at).toLocaleString("en-GB")}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
