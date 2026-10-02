/**
 * Offline queue for writes made without a connection (Essequibo campus).
 * Items live in localStorage (per device, per browser) and are replayed in order when the
 * connection returns. Only leave requests are queued in Release 1.
 *
 * A file cannot be kept here, so a request that turns out to need a doctor's note is saved on the
 * server as a draft and waits for the employee to attach the note and submit it.
 */

import { post } from "../api/client";

export interface QueuedLeaveRequest {
  id: string;
  kind: "leave.create";
  payload: Record<string, unknown>;
  submit: boolean;
  createdAt: string;
}

export interface FlushResult {
  sent: number;
  drafts: number;
  rejected: number;
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

/**
 * Replay queued items in order. Stops at the first network failure; drops items the server rejects.
 * An item the server saved but would not submit is counted as a draft.
 */
export async function flush(): Promise<FlushResult> {
  const result: FlushResult = { sent: 0, drafts: 0, rejected: 0 };
  if (flushing || !navigator.onLine) return result;
  flushing = true;
  try {
    let items = read();
    while (items.length > 0) {
      const item = items[0];
      let created: { id: number } | null = null;
      try {
        created = await post<{ id: number }>("/leave/requests/", item.payload);
        if (item.submit) await post(`/leave/requests/${created.id}/transition/`, { action: "submit" });
        result.sent += 1;
      } catch (err) {
        if (isNetworkError(err) && created === null) break; // still offline; keep the item
        if (created === null) result.rejected += 1; // validation or permission error: do not retry forever
        else result.drafts += 1;
      }
      items = items.slice(1);
      write(items);
    }
  } finally {
    flushing = false;
  }
  return result;
}

export function startAutoFlush() {
  window.addEventListener("online", () => void flush());
  void flush();
}
