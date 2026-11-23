import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  ApiError,
  describe as describeError,
  setSessionEndedHandler,
  waitWords,
} from "../src/api/client";
import { mockApi } from "./helpers";

afterEach(() => {
  setSessionEndedHandler(undefined);
});

describe("api", () => {
  it("sends and receives JSON", async () => {
    const { fetchMock } = mockApi({ "POST /api/x": (body) => ({ json: { got: body } }) });
    const answer = await api<unknown>("POST", "/api/x", { a: 1 });
    expect(answer).toEqual({ got: { a: 1 } });
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin" });
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("sends no body or content type on a read", async () => {
    const { fetchMock } = mockApi({ "GET /api/x": { json: { ok: true } } });
    await api("GET", "/api/x");
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(init?.body).toBeUndefined();
    expect(init?.headers).toEqual({ Accept: "application/json" });
  });

  it("returns nothing for 204", async () => {
    mockApi({ "DELETE /api/x": { status: 204 } });
    const answer = await api<unknown>("DELETE", "/api/x");
    expect(answer).toBeUndefined();
  });

  it("turns a problem document into an ApiError", async () => {
    mockApi({
      "GET /api/x": {
        status: 403,
        json: { code: "read_only", title: "Read only", detail: "Ask an admin", request_id: "r-1" },
      },
    });
    const error = await api("GET", "/api/x").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 403,
      code: "read_only",
      message: "Read only",
      detail: "Ask an admin",
      requestId: "r-1",
      retryAfter: undefined,
    });
  });

  it("reads Retry-After", async () => {
    mockApi({
      "GET /api/x": {
        status: 429,
        json: { code: "too_many_attempts" },
        headers: { "Retry-After": "90" },
      },
    });
    await expect(api("GET", "/api/x")).rejects.toMatchObject({ retryAfter: 90 });
  });

  it("copes with an answer that is not a problem document", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(new Response("<html>bad gateway</html>", { status: 502 })),
    );
    await expect(api("GET", "/api/x")).rejects.toMatchObject({
      status: 502,
      code: "error",
      message: "The request failed (502)",
    });
    vi.stubGlobal("fetch", () =>
      Promise.resolve(new Response(JSON.stringify({ title: 5 }), { status: 500 })),
    );
    await expect(api("GET", "/api/x")).rejects.toMatchObject({
      message: "The request failed (500)",
    });
  });

  it("says so when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("failed")));
    await expect(api("GET", "/api/x")).rejects.toMatchObject({ status: 0, code: "network" });
  });

  it("tells the handler when a signed-in session has ended, and only then", async () => {
    const handler = vi.fn();
    setSessionEndedHandler(handler);
    mockApi({
      "GET /api/a": { status: 401, json: { code: "not_signed_in", title: "Sign in" } },
      "GET /api/b": { status: 401, json: { code: "invalid_credentials", title: "No" } },
      "GET /api/c": { status: 500, json: {} },
    });
    await api("GET", "/api/a").catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(1);
    await api("GET", "/api/b").catch(() => undefined);
    await api("GET", "/api/c").catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("copes with a 401 when nothing is listening", async () => {
    mockApi({ "GET /api/a": { status: 401, json: { code: "not_signed_in" } } });
    await expect(api("GET", "/api/a")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("describe", () => {
  it("quotes the request id when there is one", () => {
    expect(describeError(new ApiError(500, "x", "Broke", { requestId: "abc" }))).toBe(
      "Broke (reference abc)",
    );
    expect(describeError(new ApiError(500, "x", "Broke"))).toBe("Broke");
  });

  it("says how long to wait after a 429", () => {
    expect(describeError(new ApiError(429, "t", "Slow down", { retryAfter: 30 }))).toBe(
      "Too many attempts. Try again in 30 seconds.",
    );
    expect(describeError(new ApiError(429, "t", "Slow down"))).toBe("Slow down");
  });

  it("does not show what it does not understand", () => {
    expect(describeError(new Error("secret internals"))).toBe("Something went wrong. Try again.");
  });
});

describe("describe, for refusals that explain themselves", () => {
  it("adds what is missing, and the reference when there is one", () => {
    const refused = new ApiError(409, "cannot_launch", "This pentest cannot start yet", {
      detail: "The signed letter is missing.",
    });
    expect(describeError(refused)).toBe(
      "This pentest cannot start yet. The signed letter is missing.",
    );
    const traced = new ApiError(403, "terms_not_accepted", "Accept the terms first", {
      detail: "Open them.",
      requestId: "r-1",
    });
    expect(describeError(traced)).toBe("Accept the terms first. Open them. (reference r-1)");
  });

  it("is just the title when there is no detail, and ignores detail on other errors", () => {
    expect(describeError(new ApiError(409, "cannot_launch", "Cannot start"))).toBe("Cannot start");
    expect(describeError(new ApiError(400, "other", "Bad", { detail: "Internal note" }))).toBe(
      "Bad",
    );
  });
});

describe("waitWords", () => {
  it.each([
    [0.2, "1 seconds"],
    [30, "30 seconds"],
    [60, "1 minute"],
    [119, "1 minute"],
    [120, "2 minutes"],
    [301, "6 minutes"],
  ])("%s seconds is %s", (seconds, words) => {
    expect(waitWords(seconds)).toBe(words);
  });
});
