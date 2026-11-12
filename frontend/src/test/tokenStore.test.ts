import { describe, expect, it, vi } from "vitest";
import { clearToken, getToken, msUntilExpiry, saveToken } from "../auth/tokenStore";

describe("token store", () => {
  it("stores only the token and its expiry in sessionStorage", () => {
    saveToken("tok", 3600, 1_000);
    const stored = JSON.parse(sessionStorage.getItem("pmrs.session") ?? "{}");
    expect(Object.keys(stored).sort()).toEqual(["expiresAt", "token"]);
    expect(stored.expiresAt).toBe(1_000 + 3_600_000);
    expect(localStorage.length).toBe(0);
    clearToken();
  });

  it("returns the token before expiry and erases it after", () => {
    saveToken("tok", 60, 0);
    expect(getToken(59_000)).toBe("tok");
    expect(msUntilExpiry(50_000)).toBe(10_000);
    expect(getToken(60_000)).toBeNull();
    expect(sessionStorage.getItem("pmrs.session")).toBeNull();
  });

  it("ignores corrupt stored data", () => {
    clearToken();
    sessionStorage.setItem("pmrs.session", "{not json");
    expect(getToken()).toBeNull();
  });

  it("falls back to memory when storage refuses writes", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    saveToken("mem", 60);
    expect(getToken()).toBe("mem");
    spy.mockRestore();
    clearToken();
    expect(getToken()).toBeNull();
  });
});
