import { useEffect, useState } from "react";
import { ApiError } from "../api/client";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

interface Settled<T> {
  key: string;
  data: T | null;
  error: string | null;
}

/** Fetch once per change of `key` (a string that fully describes the request). A result
 *  belongs to the key it was fetched for, so a stale one is never shown; an older
 *  request is cancelled when the key changes. */
export function useLoad<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
): Loaded<T> & { setData: (data: T) => void } {
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetcher(controller.signal)
      .then((data) => setSettled({ key, data, error: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const error_ =
          error instanceof ApiError
            ? error.message
            : "Something went wrong. Please try again.";
        setSettled({ key, data: null, error: error_ });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const current = settled && settled.key === key ? settled : null;
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: current === null,
    setData: (data) => setSettled({ key, data, error: null }),
  };
}
