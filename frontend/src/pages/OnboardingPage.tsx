import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { GenrePicker } from "../components/GenrePicker";
import { ErrorNotice } from "../components/Notice";

export function OnboardingPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string[]>(user?.genres ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      setUser(await api.setGenres(selected));
      navigate("/movies", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save your genres.");
      setBusy(false);
    }
  }

  return (
    <section className="narrow">
      <h1>Welcome{user ? `, ${user.display_name}` : ""}</h1>
      <p>
        Pick the genres you like. They will shape your recommendations once those pages
        exist. You can skip this and change it later in your account.
      </p>
      <GenrePicker selected={selected} onChange={setSelected} disabled={busy} />
      {error && <ErrorNotice>{error}</ErrorNotice>}
      <div className="row">
        <button type="button" onClick={save} disabled={busy}>
          {selected.length ? "Save and continue" : "Continue without genres"}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => navigate("/movies")}
          disabled={busy}
        >
          Skip
        </button>
      </div>
    </section>
  );
}
