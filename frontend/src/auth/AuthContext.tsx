import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/endpoints";
import { ApiError, isAbort, setUnauthorizedHandler } from "../api/client";
import type { User } from "../api/types";
import { clearServed } from "../served";
import { clearToken, getToken, msUntilExpiry, saveToken } from "./tokenStore";

type Status = "loading" | "anonymous" | "authenticated";

interface Auth {
  status: Status;
  user: User | null;
  /** One-time message shown on the login page, e.g. "session expired". */
  notice: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => void;
  setUser: (user: User) => void;
  /** Called after the account was deleted: forget everything. */
  forget: () => void;
  clearNotice: () => void;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>(getToken() ? "loading" : "anonymous");
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const expire = useCallback((message: string | null) => {
    clearToken();
    clearServed(); // nothing cached for this person survives logging out
    setUser(null);
    setStatus("anonymous");
    setNotice(message);
  }, []);

  // A 401 on any logged-in request means the token expired or is invalid.
  useEffect(() => {
    setUnauthorizedHandler(() => expire("Your session ended. Please log in again."));
    return () => setUnauthorizedHandler(null);
  }, [expire]);

  // Restore the session after a refresh: ask the API who the token belongs to.
  useEffect(() => {
    if (!getToken()) return;
    const controller = new AbortController();
    api
      .me(controller.signal)
      .then((me) => {
        setUser(me);
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (isAbort(error)) return;
        // A 401 is already handled (and keeps its message); any other failure
        // means we cannot confirm the session, so treat it as signed out.
        if (!(error instanceof ApiError && error.status === 401)) expire(null);
      });
    return () => controller.abort();
  }, [expire]);

  // Log out at the moment the token would expire, with a message.
  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(
      () => expire("Your session expired after 60 minutes. Please log in again."),
      Math.min(msUntilExpiry(), 2_147_000_000),
    );
    return () => window.clearTimeout(timer);
  }, [status, expire]);

  const login = useCallback(async (email: string, password: string) => {
    const token = await api.login(email, password);
    saveToken(token.access_token, token.expires_in);
    setNotice(null);
    setUser(await api.me());
    setStatus("authenticated");
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      await api.register(email, password, displayName);
      await login(email, password);
    },
    [login],
  );

  const forget = useCallback(() => expire(null), [expire]);

  const value = useMemo<Auth>(
    () => ({
      status,
      user,
      notice,
      login,
      register,
      logout: () => expire(null),
      setUser,
      forget,
      clearNotice: () => setNotice(null),
    }),
    [status, user, notice, login, register, expire, forget],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
