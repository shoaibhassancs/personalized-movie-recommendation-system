import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router";
import { ApiError } from "./api/client";

/** One request per page visit, whatever React does.
 *
 *  Every recommendations or dashboard call makes the API log "served" events. React's
 *  development mode runs effects twice, and a cancelled request is still served and
 *  logged by the API, so this keeps one promise per (page visit, request) and shares it.
 *  A "visit" is one navigation (react-router's `location.key`); opening the page again
 *  is a new visit and fetches again. A failed request is forgotten so it can be retried.
 *  Nothing here is persisted: a reload, a logout or an expired session clears it. */
const requests = new Map<string, Promise<unknown>>();
const MAX_ENTRIES = 60;

export function servedOnce<T>(
  key: string,
  fetcher: () => Promise<T>,
  force = false,
): Promise<T> {
  const existing = requests.get(key);
  if (existing && !force) return existing as Promise<T>;
  const promise = fetcher();
  requests.set(key, promise);
  promise.catch(() => {
    if (requests.get(key) === promise) requests.delete(key);
  });
  while (requests.size > MAX_ENTRIES) {
    const oldest = requests.keys().next().value;
    if (oldest === undefined) break;
    requests.delete(oldest);
  }
  return promise;
}

export function clearServed(): void {
  requests.clear();
}

interface Settled<T> {
  key: string;
  data: T | null;
  error: string | null;
}

/** Load once when the page is opened, again only on `refresh()`. `scope` must fully
 *  describe the request (user, method, ...). Changing `scope` is an explicit choice by
 *  the person (e.g. picking another method) and fetches that scope once per visit. */
export function useServed<T>(scope: string, fetcher: () => Promise<T>) {
  const visit = useLocation().key;
  const key = `${visit}|${scope}`;
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let live = true;
    servedOnce(key, fetcher).then(
      (data) => live && setSettled({ key, data, error: null }),
      (e: unknown) => live && setSettled({ key, data: null, error: describe(e) }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await servedOnce(key, fetcher, true);
      setSettled({ key, data, error: null });
    } catch (e) {
      setSettled({ key, data: null, error: describe(e) });
    } finally {
      setRefreshing(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const current = settled && settled.key === key ? settled : null;
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: current === null,
    refreshing,
    refresh,
  };
}

function describe(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Something went wrong. Please try again.";
}
