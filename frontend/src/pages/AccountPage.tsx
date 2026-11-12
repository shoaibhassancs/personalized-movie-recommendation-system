import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { clearToken } from "../auth/tokenStore";
import { GenrePicker } from "../components/GenrePicker";
import { ErrorNotice, InfoNotice } from "../components/Notice";
import { DELETE_PHRASE } from "../constants";

export function AccountPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.display_name ?? "");
  const [genres, setGenres] = useState<string[]>(user?.genres ?? []);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      await api.updateName(name);
      setUser(await api.setGenres(genres));
      setSaved("Saved.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount();
      // The token is useless now. Leave the guarded page first (navigation is
      // deferred), and let the next page reset the in-memory login state.
      clearToken();
      navigate("/account-deleted", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete the account.");
      setBusy(false);
    }
  }

  if (!user) return null;
  return (
    <section className="narrow">
      <h1>Your account</h1>
      <p className="muted">{user.email}</p>
      <form onSubmit={save}>
        <label>
          Display name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
          />
        </label>
        <GenrePicker selected={genres} onChange={setGenres} disabled={busy} />
        <button type="submit" disabled={busy}>
          Save changes
        </button>
        {saved && <InfoNotice>{saved}</InfoNotice>}
      </form>

      <section className="danger-zone" aria-labelledby="danger-title">
        <h2 id="danger-title">Delete your account</h2>
        <p>
          This permanently erases your account, your ratings, likes, dislikes, watchlist,
          watched list, genres and recommendation records. It cannot be undone. The
          MovieLens data stays.
        </p>
        <InfoNotice>
          The API does not ask for your password again, so anyone holding your login token
          could delete the account. Keep this app local until that is addressed.
        </InfoNotice>
        <label>
          Type <strong>{DELETE_PHRASE}</strong> to confirm
          <input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="off"
          />
        </label>
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <button
          type="button"
          className="danger"
          disabled={busy || confirm.trim() !== DELETE_PHRASE}
          onClick={remove}
        >
          Delete my account
        </button>
      </section>
    </section>
  );
}

export function AccountDeletedPage() {
  const { forget } = useAuth();
  useEffect(() => forget(), [forget]);
  return (
    <section className="narrow">
      <h1>Your account was deleted</h1>
      <p>
        Your account and everything you added in this app were erased. You are logged out.
      </p>
    </section>
  );
}

export function NotFoundPage() {
  return (
    <section>
      <h1>Page not found</h1>
    </section>
  );
}
