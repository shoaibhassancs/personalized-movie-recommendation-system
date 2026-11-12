/** Where the 60-minute bearer token lives: sessionStorage (owner decision, D-041).
 *
 * It survives a refresh in this tab and ends when the tab closes. Known limit: any
 * script running on the page (XSS) could read it, so the app never uses
 * dangerouslySetInnerHTML and loads no third-party scripts, fonts or analytics.
 * Only the token and its expiry time are stored. Never a password. If the browser
 * refuses storage, the token is kept in memory for this page load only. */
const KEY = "pmrs.session";

interface Stored {
  token: string;
  expiresAt: number; // ms since epoch
}

let memory: Stored | null = null;

function read(): Stored | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        typeof (parsed as Stored).token === "string" &&
        typeof (parsed as Stored).expiresAt === "number"
      ) {
        return parsed as Stored;
      }
    }
  } catch {
    // unreadable storage or bad JSON: fall through to memory
  }
  return memory;
}

export function saveToken(
  token: string,
  expiresInSeconds: number,
  now = Date.now(),
): void {
  const stored: Stored = { token, expiresAt: now + expiresInSeconds * 1000 };
  memory = stored;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    // memory copy only
  }
}

export function clearToken(): void {
  memory = null;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing to do
  }
}

/** The token if it exists and has not expired; an expired one is erased. */
export function getToken(now = Date.now()): string | null {
  const stored = read();
  if (!stored) return null;
  if (stored.expiresAt <= now) {
    clearToken();
    return null;
  }
  return stored.token;
}

/** Milliseconds until the stored token expires (0 if none). */
export function msUntilExpiry(now = Date.now()): number {
  const stored = read();
  return stored ? Math.max(0, stored.expiresAt - now) : 0;
}
