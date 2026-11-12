import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  messageFromBody,
  request,
  setUnauthorizedHandler,
} from "../api/client";
import { clearToken, getToken, saveToken } from "../auth/tokenStore";
import { mockApi } from "./helpers";

describe("API client", () => {
  it("sends the bearer token when logged in and none when not", async () => {
    const calls = mockApi({ "GET /x": { body: {} } });
    clearToken();
    await request("/x");
    saveToken("secret-token", 60);
    await request("/x");
    expect(calls[0]?.headers.Authorization).toBeUndefined();
    expect(calls[1]?.headers.Authorization).toBe("Bearer secret-token");
  });

  it("maps a string detail and a 422 list to one readable message", async () => {
    expect(messageFromBody({ detail: "movie not found" }, 404)).toBe("movie not found");
    expect(
      messageFromBody(
        { detail: [{ loc: ["body", "password"], msg: "too short", type: "x" }] },
        422,
      ),
    ).toBe("password: too short");
    expect(messageFromBody(null, 500)).toBe("The server returned an error (500).");
  });

  it("on 401 with a token: clears it and calls the handler", async () => {
    mockApi({ "GET /me": { status: 401, body: { detail: "invalid token" } } });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    saveToken("old", 60);
    await expect(request("/me")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledOnce();
    expect(getToken()).toBeNull();
    setUnauthorizedHandler(null);
  });

  it("on 401 without a token (a wrong password): no logout handling", async () => {
    mockApi({
      "POST /auth/login": {
        status: 401,
        body: { detail: "incorrect email or password" },
      },
    });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    clearToken();
    await expect(request("/auth/login", { method: "POST", body: {} })).rejects.toThrow(
      "incorrect email or password",
    );
    expect(handler).not.toHaveBeenCalled();
    setUnauthorizedHandler(null);
  });

  it("reports an unreachable API as status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await request("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
  });

  it("returns undefined for 204", async () => {
    mockApi({ "DELETE /me": { status: 204 } });
    await expect(request("/me", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
