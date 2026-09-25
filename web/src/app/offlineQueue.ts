/**
 * Offline queue for writes made without a connection (Essequibo campus).
 * Items live in localStorage (per device, per browser) and are replayed in order when the
 * connection returns. Only leave requests are queued in Release 1.
 */

import { post } from "../api/client";

export interface QueuedLeaveRequest {
  id: string;
  kind: "leave.create";
  payload: Record<string, unknown>;
  submit: boolean;
  createdAt: string;
}

const KEY = "gsa-hrms.offline-queue";
const listeners = new Set<() => void>();

function read(): QueuedLeaveRequest[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function write(items: QueuedLeaveRequest[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable: the item is lost and the caller shows the error */
  }
  listeners.forEach((fn) => fn());
}

export const isNetworkError = (err: unknown) => err instanceof TypeError;

export function enqueueLeave(payload: Record<string, unknown>, submit: boolean): QueuedLeaveRequest {
  const item: QueuedLeaveRequest = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    kind: "leave.create",
    payload,
    submit,
    createdAt: new Date().toISOString(),
  };
  write([...read(), item]);
  return item;
}

export const pendingCount = () => read().length;

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let flushing = false;

/** Replay queued items in order. Stops at the first network failure; drops items the server rejects. */
export async function flush(): Promise<{ sent: number; rejected: number }> {
  if (flushing || !navigator.onLine) return { sent: 0, rejected: 0 };
  flushing = true;
  let sent = 0;
  let rejected = 0;
  try {
    let items = read();
    while (items.length > 0) {
      const item = items[0];
      try {
        const created = await post<{ id: number }>("/leave/requests/", item.payload);
        if (item.submit) await post(`/leave/requests/${created.id}/transition/`, { action: "submit" });
        sent += 1;
      } catch (err) {
        if (isNetworkError(err)) break; // still offline; keep the item
        rejected += 1; // validation or permission error: do not retry forever
      }
      items = items.slice(1);
      write(items);
    }
  } finally {
    flushing = false;
  }
  return { sent, rejected };
}

export function startAutoFlush() {
  window.addEventListener("online", () => void flush());
  void flush();
}
