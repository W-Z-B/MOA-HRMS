import { afterEach, describe, expect, it, vi } from "vitest";
import { fakeServer, offline } from "../test/fetch";
import { enqueueLeave, flush, isNetworkError, pendingCount, startAutoFlush, subscribe } from "./offlineQueue";

const annual = (from: string) => ({ employee: 1, leave_type: 2, from_date: from, to_date: from, reason: "" });

describe("offline queue for leave requests", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps a request on the device and tells listeners", () => {
    const heard = vi.fn();
    const stop = subscribe(heard);
    enqueueLeave(annual("2026-11-02"), true);
    expect(pendingCount()).toBe(1);
    expect(heard).toHaveBeenCalledTimes(1);
    stop();
    enqueueLeave(annual("2026-11-03"), true);
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it("sends queued requests in order when the connection returns, and submits them", async () => {
    enqueueLeave(annual("2026-11-02"), true);
    enqueueLeave(annual("2026-11-09"), false);
    const server = fakeServer({
      "POST /leave/requests/": [
        { status: 201, body: { id: 11 } },
        { status: 201, body: { id: 12 } },
      ],
      "POST /leave/requests/11/transition/": { body: { id: 11, state: "submitted" } },
    });
    await expect(flush()).resolves.toEqual({ sent: 2, drafts: 0, rejected: 0 });
    expect(server.calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "POST /leave/requests/",
      "POST /leave/requests/11/transition/",
      "POST /leave/requests/",
    ]);
    expect((server.calls[0].body as { from_date: string }).from_date).toBe("2026-11-02");
    expect(pendingCount()).toBe(0);
  });

  it("stops at the first network failure and keeps the request for later", async () => {
    enqueueLeave(annual("2026-11-02"), true);
    fakeServer({ "POST /leave/requests/": offline });
    await expect(flush()).resolves.toEqual({ sent: 0, drafts: 0, rejected: 0 });
    expect(pendingCount()).toBe(1);
  });

  it("drops a request the server refuses, so it is not retried for ever", async () => {
    enqueueLeave(annual("2026-11-02"), true);
    fakeServer({ "POST /leave/requests/": { status: 400, body: { detail: "Overlaps another request." } } });
    await expect(flush()).resolves.toEqual({ sent: 0, drafts: 0, rejected: 1 });
    expect(pendingCount()).toBe(0);
  });

  it("counts a request that was saved but could not be sent as a draft", async () => {
    enqueueLeave(annual("2026-11-02"), true);
    fakeServer({
      "POST /leave/requests/": { status: 201, body: { id: 21 } },
      "POST /leave/requests/21/transition/": { status: 409, body: { code: "evidence", detail: "Attach a note." } },
    });
    await expect(flush()).resolves.toEqual({ sent: 0, drafts: 1, rejected: 0 });
    expect(pendingCount()).toBe(0);
  });

  it("does not try while the device reports no connection", async () => {
    enqueueLeave(annual("2026-11-02"), true);
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const server = fakeServer({});
    await expect(flush()).resolves.toEqual({ sent: 0, drafts: 0, rejected: 0 });
    expect(server.fetchMock).not.toHaveBeenCalled();
    expect(pendingCount()).toBe(1);
  });

  it("flushes on start and again whenever the connection comes back", async () => {
    const server = fakeServer({ "POST /leave/requests/": { status: 201, body: { id: 31 } } });
    startAutoFlush();
    enqueueLeave(annual("2026-11-02"), false);
    window.dispatchEvent(new Event("online"));
    await vi.waitFor(() => expect(pendingCount()).toBe(0));
    expect(server.calls).toHaveLength(1);
  });

  it("recognises a dropped connection", () => {
    expect(isNetworkError(new TypeError("Failed to fetch"))).toBe(true);
    expect(isNetworkError(new Error("400"))).toBe(false);
  });
});
