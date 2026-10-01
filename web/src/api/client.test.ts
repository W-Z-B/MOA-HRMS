import { describe, expect, it } from "vitest";
import { fakeServer } from "../test/fetch";
import { ApiError, errorMessage, get, patch, plainMessage, post, remove } from "./client";

describe("API client", () => {
  it("calls the versioned API with the session cookie and asks for JSON", async () => {
    const server = fakeServer({ "GET /auth/me/": { body: { id: 7 } } });
    await expect(get("/auth/me/")).resolves.toEqual({ id: 7 });
    expect(server.fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/me/",
      expect.objectContaining({ credentials: "same-origin", method: "GET" }),
    );
    expect(server.calls[0].headers.get("Accept")).toBe("application/json");
    expect(server.calls[0].headers.has("X-CSRFToken")).toBe(false);
  });

  it("sends the CSRF token with every change, never with a read", async () => {
    document.cookie = "csrftoken=abc123";
    const server = fakeServer({
      "POST /leave/requests/": { status: 201, body: { id: 1 } },
      "PATCH /employees/4/": { body: { id: 4 } },
      "DELETE /documents/9/": { status: 204 },
    });
    await post("/leave/requests/", { days: 2 });
    await patch("/employees/4/", { phone: "600-0000" });
    await remove("/documents/9/");
    expect(server.calls.map((c) => c.headers.get("X-CSRFToken"))).toEqual(["abc123", "abc123", "abc123"]);
    expect(server.calls[0].headers.get("Content-Type")).toBe("application/json");
    expect(server.calls[0].body).toEqual({ days: 2 });
  });

  it("lets the browser set the content type for a file upload", async () => {
    const server = fakeServer({ "POST /leave/requests/3/evidence/": { body: {} } });
    const form = new FormData();
    form.set("file", new Blob(["x"]), "note.pdf");
    await post("/leave/requests/3/evidence/", form);
    expect(server.calls[0].headers.has("Content-Type")).toBe(false);
    expect(server.calls[0].body).toBeInstanceOf(FormData);
  });

  it("answers nothing for 204 No Content", async () => {
    fakeServer({ "POST /auth/logout/": { status: 204 } });
    await expect(post("/auth/logout/")).resolves.toBeUndefined();
  });

  it("turns a refusal into an ApiError with its code and sentence", async () => {
    fakeServer({ "POST /auth/login/": { status: 423, body: { code: "locked_out", detail: "Too many failed attempts." } } });
    const err = await post("/auth/login/", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 423, code: "locked_out", detail: "Too many failed attempts." });
    expect(errorMessage(err)).toBe("Too many failed attempts.");
  });

  it("keeps field errors so forms can show them", async () => {
    fakeServer({ "POST /employees/": { status: 400, body: { date_of_birth: ["Enter a valid date."] } } });
    const err = await post("/employees/", {}).catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "error", fields: { date_of_birth: ["Enter a valid date."] } });
    expect(errorMessage(err)).toBe("date of birth: Enter a valid date.");
    expect(plainMessage(err, "fallback")).toBe("Enter a valid date.");
  });

  it("falls back to a plain sentence for errors that are not from the API", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe("Something went wrong.");
    expect(plainMessage(new TypeError("Failed to fetch"), "Could not load.")).toBe("Could not load.");
    expect(plainMessage(new ApiError(403, "forbidden", "Not yours."), "x")).toBe("Not yours.");
  });

  it("copes with an error page that is not JSON, such as a proxy timeout", async () => {
    fakeServer({ "GET /reports/": { status: 502, raw: "<html>Bad Gateway</html>" } });
    const err = await get("/reports/").catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 502, code: "error", detail: "Request failed" });
  });

  it("lets a dropped connection through as a network error, for the offline queue", async () => {
    fakeServer({
      "GET /reports/": () => {
        throw new TypeError("Failed to fetch");
      },
    });
    await expect(get("/reports/")).rejects.toBeInstanceOf(TypeError);
  });
});
