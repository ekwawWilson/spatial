import { useState, type FormEvent } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useSession } from "../session";

export function AccountPage() {
  const { api, me } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await api.changePassword(current, next);
      setSaved(true);
      setCurrent("");
      setNext("");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page">
      <h1>Your account</h1>
      <p>
        {me?.first_name} {me?.last_name} · {me?.email}
      </p>
      <form className="card narrow" onSubmit={submit}>
        <h2>Change password</h2>
        <label>
          Current password
          <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label>
          New password
          <input type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
        <ErrorMessage error={error} />
        {saved && <p role="status">Password changed. Other devices have been signed out.</p>}
        <button type="submit">Change password</button>
      </form>
    </section>
  );
}
