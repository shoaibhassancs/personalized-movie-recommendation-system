import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ErrorNotice } from "../components/Notice";
import { PASSWORD_MAX, PASSWORD_MIN } from "../constants";

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The password is sent exactly as typed: never trimmed, never stored in the browser.
  const lengthOk = password.length >= PASSWORD_MIN && password.length <= PASSWORD_MAX;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!lengthOk) return;
    setBusy(true);
    setError(null);
    try {
      await register(email, password, name);
      navigate("/onboarding/genres", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="narrow">
      <h1>Create an account</h1>
      <form onSubmit={submit}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="username"
          />
        </label>
        <label>
          Display name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            aria-describedby="pw-help"
          />
        </label>
        <p
          id="pw-help"
          className={lengthOk || password === "" ? "muted" : "notice-text-error"}
        >
          {PASSWORD_MIN}–{PASSWORD_MAX} characters. A passphrase of several words works
          well. {password.length} / {PASSWORD_MAX} characters.
        </p>
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <button type="submit" disabled={busy || !lengthOk}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p>
        Already registered? <Link to="/login">Log in</Link>
      </p>
    </section>
  );
}
